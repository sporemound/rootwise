"""Opt-in Stage 0.22 scale-gate evidence runner.

The tool never creates a source corpus and never deletes or overwrites a path. Scanner execution
requires an operator-supplied source on a volume distinct from the new inventory destination.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

from rootwise.database import InventoryDatabase
from rootwise.models import ScanConfig, SessionState
from rootwise.resources import MIB, process_rss_bytes
from rootwise.scanner import MetadataScanner
from rootwise.volume import resolve_volume
from rootwise.write_guard import WriteGuard
from rootwise_analytics.pipeline import run_analysis
from rootwise_view.inventory import InventoryReader

ROOT = Path(__file__).parents[1]
CODE_VERSION = "0.22.0-alpha"
EVIDENCE_SCHEMA = "rootwise-scale-evidence-v1"
MINIMUM_SCALE_ENTRIES = 1_000_000
MAX_QUERY_FILE_BYTES = 1_048_576
MAX_QUERY_COUNT = 10_000


@dataclass(frozen=True)
class Budgets:
    maximum_duration_seconds: float
    maximum_peak_rss_bytes: int
    maximum_temporary_bytes: int
    minimum_entry_count: int = MINIMUM_SCALE_ENTRIES

    def validate(self) -> None:
        if not math.isfinite(self.maximum_duration_seconds) or self.maximum_duration_seconds <= 0:
            raise ValueError("maximum duration must be finite and positive")
        if self.maximum_peak_rss_bytes < 32 * MIB:
            raise ValueError("maximum peak RSS must be at least 32 MiB")
        if self.maximum_temporary_bytes < 0:
            raise ValueError("maximum temporary bytes must be nonnegative")
        if self.minimum_entry_count < MINIMUM_SCALE_ENTRIES:
            raise ValueError("minimum entry count must be at least 1000000")


@dataclass(frozen=True)
class Profile:
    duration_seconds: float
    peak_rss_bytes: int
    temporary_bytes: int


class ResourceMonitor:
    """Sample current-process RSS and explicit output artifacts during one operation."""

    def __init__(self, tracked_paths: Sequence[Path], interval_seconds: float = 0.05) -> None:
        self.tracked_paths = tuple(tracked_paths)
        self.interval_seconds = interval_seconds
        self.peak_rss_bytes = 0
        self.peak_output_bytes = 0
        self.started = 0.0
        self._stopped = threading.Event()
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._sample_until_stopped, daemon=True)

    @staticmethod
    def _related_size(path: Path) -> int:
        total = 0
        for candidate in (path, Path(str(path) + "-journal"), Path(str(path) + "-wal"),
                          Path(str(path) + "-shm"), Path(str(path) + "-scanlock")):
            try:
                total += candidate.stat().st_size
            except FileNotFoundError:
                continue
        return total

    def _sample(self) -> None:
        rss = process_rss_bytes()
        if rss is None:
            raise RuntimeError("process RSS could not be resolved")
        self.peak_rss_bytes = max(self.peak_rss_bytes, rss)
        output_bytes = sum(self._related_size(path) for path in self.tracked_paths)
        self.peak_output_bytes = max(self.peak_output_bytes, output_bytes)

    def _sample_until_stopped(self) -> None:
        try:
            while not self._stopped.wait(self.interval_seconds):
                self._sample()
        except BaseException as exc:
            self._error = exc
            self._stopped.set()

    def __enter__(self) -> "ResourceMonitor":
        self.started = time.perf_counter()
        self._sample()
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, *_: object) -> None:
        self._stopped.set()
        self._thread.join()
        self._sample()
        if exc_type is None and self._error is not None:
            raise RuntimeError("resource monitor failed") from self._error

    def profile(self) -> Profile:
        return Profile(
            time.perf_counter() - self.started,
            self.peak_rss_bytes,
            self.peak_output_bytes,
        )


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def _source_metadata_digest(root: Path) -> tuple[str, int]:
    """Hash names and fresh non-following metadata without reading file contents."""
    digest = hashlib.sha256()
    count = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
        for entry in entries:
            metadata = os.stat(entry.path, follow_symlinks=False)
            relative = Path(entry.path).relative_to(root).as_posix()
            kind = "directory" if entry.is_dir(follow_symlinks=False) else (
                "symlink" if entry.is_symlink() else "file"
            )
            digest.update(_canonical({
                "kind": kind,
                "modified_ns": metadata.st_mtime_ns,
                "path": relative,
                "size": metadata.st_size,
            }))
            count += 1
            if kind == "directory":
                pending.append(Path(entry.path))
    return digest.hexdigest(), count


def _revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
        timeout=15, check=False,
    )
    revision = completed.stdout.strip()
    if completed.returncode != 0 or len(revision) != 40:
        raise ValueError("current Git revision could not be resolved")
    dirty = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=ROOT, capture_output=True, text=True,
        timeout=15, check=False,
    )
    if dirty.returncode != 0 or dirty.stdout:
        raise ValueError("scale evidence requires a clean Git worktree")
    return revision


def _validate_revision(subject_revision: str, *, current: str | None = None) -> str:
    if len(subject_revision) != 40 or any(character not in "0123456789abcdef" for character in subject_revision):
        raise ValueError("subject revision must be a lowercase full Git commit ID")
    actual = _revision() if current is None else current
    if subject_revision != actual:
        raise ValueError("subject revision does not match the clean current checkout")
    return actual


def _output_pair(evidence: str | Path, measurements: str | Path) -> tuple[Path, Path]:
    evidence_path = Path(evidence).expanduser().resolve(strict=False)
    measurements_path = Path(measurements).expanduser().resolve(strict=False)
    if evidence_path == measurements_path or evidence_path.parent != measurements_path.parent:
        raise ValueError("evidence and measurements must be distinct siblings")
    evidence_path.parent.resolve(strict=True)
    if evidence_path.exists() or measurements_path.exists():
        raise ValueError("evidence and measurements outputs must be new files")
    return evidence_path, measurements_path


def _require_outside(root: Path, *paths: Path) -> None:
    for path in paths:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        raise ValueError("scale outputs must remain outside the measured source tree")


def _write_pair(
    evidence_path: Path,
    measurements_path: Path,
    evidence: dict[str, object],
    measurements: dict[str, object],
) -> None:
    with evidence_path.open("xb") as evidence_stream, measurements_path.open(
        "xb"
    ) as measurements_stream:
        evidence_stream.write(_canonical(evidence))
        measurements_stream.write(_canonical(measurements))


def _base_measurements(
    *, completed: bool, inputs_unchanged: bool, observed_entry_count: int,
    profile: Profile, budgets: Budgets,
) -> dict[str, object]:
    return {
        "completed": completed,
        "duration_seconds": profile.duration_seconds,
        "inputs_unchanged": inputs_unchanged,
        "maximum_duration_seconds": budgets.maximum_duration_seconds,
        "maximum_peak_rss_bytes": budgets.maximum_peak_rss_bytes,
        "maximum_temporary_bytes": budgets.maximum_temporary_bytes,
        "minimum_entry_count": budgets.minimum_entry_count,
        "observed_entry_count": observed_entry_count,
        "peak_rss_bytes": profile.peak_rss_bytes,
        "temporary_bytes": profile.temporary_bytes,
    }


def _measurements_pass(measurements: dict[str, object]) -> bool:
    def number(name: str) -> float | None:
        value = measurements.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    observed = number("observed_entry_count")
    minimum = number("minimum_entry_count")
    duration = number("duration_seconds")
    maximum_duration = number("maximum_duration_seconds")
    rss = number("peak_rss_bytes")
    maximum_rss = number("maximum_peak_rss_bytes")
    temporary = number("temporary_bytes")
    maximum_temporary = number("maximum_temporary_bytes")
    required = [
        measurements["completed"] is True,
        measurements["inputs_unchanged"] is True,
        observed is not None and minimum is not None and observed >= minimum,
        duration is not None and maximum_duration is not None and duration <= maximum_duration,
        rss is not None and maximum_rss is not None and rss <= maximum_rss,
        temporary is not None and maximum_temporary is not None
        and temporary <= maximum_temporary,
    ]
    if "query_count" in measurements:
        query_count = number("query_count")
        p95 = number("p95_query_seconds")
        maximum_p95 = number("maximum_p95_query_seconds")
        required.extend([
            query_count is not None and query_count >= 100,
            measurements["query_only"] is True,
            p95 is not None and maximum_p95 is not None and p95 <= maximum_p95,
        ])
    return all(required)


def run_viewer_scale(
    inventory: str | Path,
    query_file: str | Path,
    evidence: str | Path,
    measurements: str | Path,
    *,
    subject_revision: str,
    budgets: Budgets,
    maximum_p95_query_seconds: float,
) -> dict[str, object]:
    budgets.validate()
    if not math.isfinite(maximum_p95_query_seconds) or maximum_p95_query_seconds <= 0:
        raise ValueError("maximum p95 query seconds must be finite and positive")
    inventory_path = Path(inventory).expanduser().resolve(strict=True)
    queries_path = Path(query_file).expanduser().resolve(strict=True)
    evidence_path, measurements_path = _output_pair(evidence, measurements)
    if len({inventory_path, queries_path, evidence_path, measurements_path}) != 4:
        raise ValueError("viewer scale inputs and outputs must be distinct")
    raw_queries = queries_path.read_bytes()
    if len(raw_queries) > MAX_QUERY_FILE_BYTES:
        raise ValueError("query file exceeds the size limit")
    queries = json.loads(raw_queries)
    if (
        not isinstance(queries, list) or not 100 <= len(queries) <= MAX_QUERY_COUNT
        or any(not isinstance(query, str) or len(query) > 500 or "\x00" in query for query in queries)
        or raw_queries != _canonical(queries)
    ):
        raise ValueError("query file must be a canonical array of 100 to 10000 bounded strings")
    inventory_before = _sha256_file(inventory_path)
    query_sha256_before = _sha256_file(queries_path)
    durations: list[float] = []
    result_rows = 0
    with ResourceMonitor(()) as monitor:
        with InventoryReader(inventory_path) as reader:
            session_id = reader.latest_complete_session()
            summary = next(item for item in reader.sessions() if item.scan_session_id == session_id)
            for query in queries:
                started = time.perf_counter()
                result_rows += len(reader.search(session_id, query, limit=200))
                durations.append(time.perf_counter() - started)
            query_only = reader.query_only
    profile = monitor.profile()
    inventory_after = _sha256_file(inventory_path)
    query_sha256_after = _sha256_file(queries_path)
    p95 = sorted(durations)[math.ceil(len(durations) * 0.95) - 1]
    values = _base_measurements(
        completed=True,
        inputs_unchanged=(
            inventory_before == inventory_after and query_sha256_before == query_sha256_after
        ),
        observed_entry_count=summary.observed_count,
        profile=profile,
        budgets=budgets,
    )
    values.update({
        "maximum_p95_query_seconds": maximum_p95_query_seconds,
        "p95_query_seconds": p95,
        "query_count": len(queries),
        "query_only": query_only,
    })
    evidence_value: dict[str, object] = {
        "code_version": CODE_VERSION,
        "gate_id": "viewer_search_scale",
        "input_inventory_sha256_after": inventory_after,
        "input_inventory_sha256_before": inventory_before,
        "measurements": values,
        "query_file_sha256_after": query_sha256_after,
        "query_file_sha256_before": query_sha256_before,
        "result_rows_returned": result_rows,
        "schema": EVIDENCE_SCHEMA,
        "session_id": session_id,
        "status": "PASS" if _measurements_pass(values) else "FAIL",
        "subject_revision": subject_revision,
    }
    _write_pair(evidence_path, measurements_path, evidence_value, values)
    return evidence_value


def run_snapshot_scale(
    inventory: str | Path,
    analysis: str | Path,
    evidence: str | Path,
    measurements: str | Path,
    *,
    subject_revision: str,
    budgets: Budgets,
) -> dict[str, object]:
    budgets.validate()
    inventory_path = Path(inventory).expanduser().resolve(strict=True)
    analysis_path = Path(analysis).expanduser().resolve(strict=False)
    evidence_path, measurements_path = _output_pair(evidence, measurements)
    if len({inventory_path, analysis_path, evidence_path, measurements_path}) != 4:
        raise ValueError("snapshot scale inputs and outputs must be distinct")
    if analysis_path.parent != inventory_path.parent or analysis_path.exists():
        raise ValueError("analysis must be a new sibling of the inventory")
    inventory_before = _sha256_file(inventory_path)
    with InventoryReader(inventory_path) as reader:
        session_id = reader.latest_complete_session()
        summary = next(item for item in reader.sessions() if item.scan_session_id == session_id)
    with ResourceMonitor((analysis_path,)) as monitor:
        result = run_analysis(inventory_path, analysis_path, session_id=session_id)
    profile = monitor.profile()
    inventory_after = _sha256_file(inventory_path)
    values = _base_measurements(
        completed=result.state == "COMPLETE",
        inputs_unchanged=inventory_before == inventory_after,
        observed_entry_count=summary.observed_count,
        profile=profile,
        budgets=budgets,
    )
    evidence_value: dict[str, object] = {
        "analysis_output_sha256": _sha256_file(analysis_path),
        "analysis_result": asdict(result),
        "code_version": CODE_VERSION,
        "gate_id": "snapshot_pipeline_scale",
        "input_inventory_sha256_after": inventory_after,
        "input_inventory_sha256_before": inventory_before,
        "measurements": values,
        "schema": EVIDENCE_SCHEMA,
        "session_id": session_id,
        "status": "PASS" if _measurements_pass(values) else "FAIL",
        "subject_revision": subject_revision,
    }
    _write_pair(evidence_path, measurements_path, evidence_value, values)
    return evidence_value


def run_scanner_scale(
    source: str | Path,
    inventory: str | Path,
    evidence: str | Path,
    measurements: str | Path,
    *,
    subject_revision: str,
    budgets: Budgets,
    max_files_per_second: float,
    batch_size: int,
    sleep_ms_per_batch: int,
) -> dict[str, object]:
    budgets.validate()
    source_path = Path(source).expanduser().resolve(strict=True)
    inventory_path = Path(inventory).expanduser().resolve(strict=False)
    evidence_path, measurements_path = _output_pair(evidence, measurements)
    if not source_path.is_dir():
        raise ValueError("scanner scale source must be a directory")
    if len({source_path, inventory_path, evidence_path, measurements_path}) != 4:
        raise ValueError("scanner scale inputs and outputs must be distinct")
    if inventory_path.exists():
        raise ValueError("scanner inventory must be a new file")
    inventory_path.parent.resolve(strict=True)
    _require_outside(source_path, evidence_path, measurements_path)
    source_before, pre_count = _source_metadata_digest(source_path)
    source_volume = resolve_volume(source_path)
    guard = WriteGuard(source_volume, inventory_path.parent)
    max_rss_mib = math.ceil(budgets.maximum_peak_rss_bytes / MIB)
    minimum_free_mib = max(1, math.ceil(budgets.maximum_temporary_bytes / MIB))
    config = ScanConfig(
        str(source_path), str(inventory_path), max_files_per_second, batch_size,
        sleep_ms_per_batch, max_rss_mib=max_rss_mib,
        min_free_destination_mib=minimum_free_mib,
    )
    with ResourceMonitor((inventory_path,)) as monitor:
        with InventoryDatabase(inventory_path, guard) as database:
            session_id, state = MetadataScanner(
                source_path, source_volume, database, config
            ).run()
    profile = monitor.profile()
    source_after, post_count = _source_metadata_digest(source_path)
    with InventoryReader(inventory_path) as reader:
        summary = next(item for item in reader.sessions() if item.scan_session_id == session_id)
    values = _base_measurements(
        completed=state is SessionState.COMPLETE,
        inputs_unchanged=source_before == source_after and pre_count == post_count,
        observed_entry_count=summary.observed_count,
        profile=profile,
        budgets=budgets,
    )
    evidence_value: dict[str, object] = {
        "code_version": CODE_VERSION,
        "gate_id": "scanner_scale",
        "inventory_sha256": _sha256_file(inventory_path),
        "measurements": values,
        "preflight_entry_count": pre_count,
        "schema": EVIDENCE_SCHEMA,
        "session_id": session_id,
        "source_metadata_sha256_after": source_after,
        "source_metadata_sha256_before": source_before,
        "status": "PASS" if _measurements_pass(values) else "FAIL",
        "subject_revision": subject_revision,
    }
    _write_pair(evidence_path, measurements_path, evidence_value, values)
    return evidence_value


def _budgets(args: argparse.Namespace) -> Budgets:
    return Budgets(
        args.maximum_duration_seconds,
        args.maximum_peak_rss_bytes,
        args.maximum_temporary_bytes,
        args.minimum_entry_count,
    )


def _common(command: argparse.ArgumentParser) -> None:
    command.add_argument("--subject-revision", required=True)
    command.add_argument("--evidence", required=True)
    command.add_argument("--measurements", required=True)
    command.add_argument("--maximum-duration-seconds", type=float, required=True)
    command.add_argument("--maximum-peak-rss-bytes", type=int, required=True)
    command.add_argument("--maximum-temporary-bytes", type=int, required=True)
    command.add_argument("--minimum-entry-count", type=int, default=MINIMUM_SCALE_ENTRIES)
    command.add_argument("--execute", action="store_true")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="run_scale_acceptance.py")
    commands = root.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="print the Stage 0.22 execution contract")
    plan.add_argument("--subject-revision", required=True)
    scanner = commands.add_parser("scanner", help="run the million-entry scanner gate")
    _common(scanner)
    scanner.add_argument("--source", required=True)
    scanner.add_argument("--inventory", required=True)
    scanner.add_argument("--max-files-per-second", type=float, default=100_000.0)
    scanner.add_argument("--batch-size", type=int, default=1_000)
    scanner.add_argument("--sleep-ms-per-batch", type=int, default=0)
    viewer = commands.add_parser("viewer", help="run at least 100 query-only searches")
    _common(viewer)
    viewer.add_argument("--inventory", required=True)
    viewer.add_argument("--query-file", required=True)
    viewer.add_argument("--maximum-p95-query-seconds", type=float, required=True)
    snapshot = commands.add_parser("snapshot", help="run structural snapshot analytics at scale")
    _common(snapshot)
    snapshot.add_argument("--inventory", required=True)
    snapshot.add_argument("--analysis", required=True)
    return root


def _plan(revision: str) -> dict[str, object]:
    return {
        "code_version": CODE_VERSION,
        "execution_authorized": False,
        "gates": ["scanner_scale", "snapshot_pipeline_scale", "viewer_search_scale"],
        "minimum_entry_count": MINIMUM_SCALE_ENTRIES,
        "requirements": [
            "exact clean subject revision",
            "operator-supplied corpus and budgets",
            "new explicit output paths",
            "--execute for every measured operation",
        ],
        "source_corpus_created": False,
        "subject_revision": revision,
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        revision = _validate_revision(args.subject_revision)
        if args.command == "plan":
            print(json.dumps(_plan(revision), sort_keys=True))
            return 0
        if not args.execute:
            raise ValueError("scale execution requires the explicit --execute switch")
        budgets = _budgets(args)
        runners: dict[str, Callable[[], dict[str, object]]] = {
            "scanner": lambda: run_scanner_scale(
                args.source, args.inventory, args.evidence, args.measurements,
                subject_revision=revision, budgets=budgets,
                max_files_per_second=args.max_files_per_second,
                batch_size=args.batch_size, sleep_ms_per_batch=args.sleep_ms_per_batch,
            ),
            "viewer": lambda: run_viewer_scale(
                args.inventory, args.query_file, args.evidence, args.measurements,
                subject_revision=revision, budgets=budgets,
                maximum_p95_query_seconds=args.maximum_p95_query_seconds,
            ),
            "snapshot": lambda: run_snapshot_scale(
                args.inventory, args.analysis, args.evidence, args.measurements,
                subject_revision=revision, budgets=budgets,
            ),
        }
        result = runners[args.command]()
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "PASS" else 2
    except (OSError, RuntimeError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
