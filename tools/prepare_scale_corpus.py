"""Prepare deterministic disposable inputs for the Rootwise scale campaign.

The command is plan-only unless ``--execute`` is supplied. It creates only zero-byte synthetic
files beneath a newly owned corpus root, never deletes or overwrites paths, and can resume only
when the immutable ownership marker and every existing entry match the requested specification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

CODE_VERSION = "0.23.0-alpha"
CORPUS_SCHEMA = "rootwise-scale-corpus-v1"
MANIFEST_SCHEMA = "rootwise-scale-corpus-manifest-v1"
MINIMUM_SCALE_ENTRIES = 1_000_000
MINIMUM_QUERY_COUNT = 100
MAXIMUM_QUERY_COUNT = 10_000
MARKER_NAME = ".rootwise-scale-corpus.json"
FILE_PATTERN = re.compile(r"item-(\d{12})\.dat\Z")
SHARD_PATTERN = re.compile(r"shard-(\d{4})\Z")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _inside(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_link_or_junction(path: Path) -> bool:
    junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (junction is not None and junction())


@dataclass(frozen=True)
class CorpusSpec:
    entry_count: int
    shard_count: int

    def validate(self, minimum_entry_count: int = MINIMUM_SCALE_ENTRIES) -> None:
        if self.entry_count < minimum_entry_count:
            raise ValueError(f"entry count must be at least {minimum_entry_count}")
        if not 1 <= self.shard_count <= 10_000:
            raise ValueError("shard count must be between 1 and 10000")
        if self.shard_count > self.entry_count:
            raise ValueError("shard count cannot exceed entry count")

    @property
    def entries_per_shard(self) -> int:
        return math.ceil(self.entry_count / self.shard_count)

    def shard_for(self, index: int) -> int:
        return index // self.entries_per_shard

    def relative_path(self, index: int) -> str:
        return f"shard-{self.shard_for(index):04d}/item-{index:012d}.dat"

    def marker(self) -> dict[str, object]:
        return {
            "code_version": CODE_VERSION,
            "content_bytes_per_file": 0,
            "entry_count": self.entry_count,
            "filename_pattern": "shard-NNNN/item-NNNNNNNNNNNN.dat",
            "schema": CORPUS_SCHEMA,
            "shard_count": self.shard_count,
        }


def _validate_controls(
    *, query_count: int, maximum_files_per_second: float, batch_size: int,
    sleep_ms_per_batch: int, stop_after: int | None,
) -> None:
    if not MINIMUM_QUERY_COUNT <= query_count <= MAXIMUM_QUERY_COUNT:
        raise ValueError("query count must be between 100 and 10000")
    if not math.isfinite(maximum_files_per_second) or maximum_files_per_second <= 0:
        raise ValueError("maximum files per second must be finite and positive")
    if not 1 <= batch_size <= 10_000:
        raise ValueError("batch size must be between 1 and 10000")
    if not 0 <= sleep_ms_per_batch <= 60_000:
        raise ValueError("sleep per batch must be between 0 and 60000 milliseconds")
    if stop_after is not None and stop_after < 1:
        raise ValueError("stop-after must be positive")


def _validate_outputs(root: Path, manifest: Path, queries: Path) -> None:
    if manifest == queries or manifest.parent != queries.parent:
        raise ValueError("manifest and query outputs must be distinct siblings")
    if _inside(root, manifest) or _inside(root, queries):
        raise ValueError("manifest and query outputs must remain outside the corpus root")
    manifest.parent.resolve(strict=True)
    if manifest.exists() or queries.exists():
        raise ValueError("manifest and query outputs must be new files")


def _initialize_or_validate_root(root: Path, spec: CorpusSpec) -> int:
    marker_bytes = _canonical(spec.marker())
    marker_path = root / MARKER_NAME
    if not root.exists():
        root.parent.resolve(strict=True)
        root.mkdir()
        with marker_path.open("xb") as stream:
            stream.write(marker_bytes)
        return 0
    if not root.is_dir() or _is_link_or_junction(root):
        raise ValueError("corpus root must be a real directory, not a link or junction")
    if not marker_path.is_file() or _is_link_or_junction(marker_path):
        raise ValueError("existing corpus root has no valid ownership marker")
    if marker_path.read_bytes() != marker_bytes:
        raise ValueError("existing corpus ownership marker does not match the requested specification")
    return _verify_existing_prefix(root, spec)


def _verify_existing_prefix(root: Path, spec: CorpusSpec) -> int:
    root_entries = sorted(os.scandir(root), key=lambda entry: entry.name)
    shard_numbers: list[int] = []
    for entry in root_entries:
        if entry.name == MARKER_NAME:
            continue
        match = SHARD_PATTERN.fullmatch(entry.name)
        if match is None or not entry.is_dir(follow_symlinks=False):
            raise ValueError(f"unexpected corpus entry: {entry.name}")
        shard = int(match.group(1))
        if shard >= spec.shard_count:
            raise ValueError(f"unexpected corpus entry: {entry.name}")
        shard_numbers.append(shard)
    if shard_numbers != list(range(len(shard_numbers))):
        raise ValueError("existing corpus shards are not a contiguous generated prefix")

    expected_index = 0
    found_partial = False
    per_shard = spec.entries_per_shard
    for shard in shard_numbers:
        directory = root / f"shard-{shard:04d}"
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        shard_start = shard * per_shard
        shard_end = min(spec.entry_count, shard_start + per_shard)
        if expected_index != shard_start:
            raise ValueError("existing corpus contains entries after an incomplete shard")
        for entry in entries:
            match = FILE_PATTERN.fullmatch(entry.name)
            if (
                match is None or int(match.group(1)) != expected_index
                or not entry.is_file(follow_symlinks=False)
                or entry.stat(follow_symlinks=False).st_size != 0
            ):
                raise ValueError(f"unexpected corpus entry: {directory.name}/{entry.name}")
            expected_index += 1
        if expected_index < shard_end:
            found_partial = True
        elif expected_index != shard_end:
            raise ValueError(f"too many entries in corpus shard: {directory.name}")
        if found_partial and shard != shard_numbers[-1]:
            raise ValueError("existing corpus contains entries after an incomplete shard")
    return expected_index


def _query_values(spec: CorpusSpec, count: int) -> list[str]:
    values: list[str] = []
    for index in range(count):
        mode = index % 4
        item_index = (index * 7919) % spec.entry_count
        if mode == 0:
            values.append(f"item-{item_index:012d}")
        elif mode == 1:
            values.append(f"shard-{spec.shard_for(item_index):04d}")
        elif mode == 2:
            values.append(".dat")
        else:
            values.append(f"not-present-{index:05d}")
    return values


def _path_digest(spec: CorpusSpec) -> str:
    digest = hashlib.sha256()
    for index in range(spec.entry_count):
        digest.update(_canonical({"path": spec.relative_path(index), "size": 0}))
    return digest.hexdigest()


def _write_completed_outputs(
    root: Path, manifest: Path, queries: Path, spec: CorpusSpec, query_count: int,
) -> None:
    query_bytes = _canonical(_query_values(spec, query_count))
    manifest_value = {
        "code_version": CODE_VERSION,
        "corpus_root": str(root),
        "entry_count": spec.entry_count,
        "marker_sha256": _sha256(_canonical(spec.marker())),
        "path_manifest_sha256": _path_digest(spec),
        "query_count": query_count,
        "query_file_sha256": _sha256(query_bytes),
        "schema": MANIFEST_SCHEMA,
        "shard_count": spec.shard_count,
        "status": "COMPLETE",
        "zero_content_files": True,
    }
    with queries.open("xb") as query_stream, manifest.open("xb") as manifest_stream:
        query_stream.write(query_bytes)
        manifest_stream.write(_canonical(manifest_value))


def prepare_corpus(
    corpus_root: str | Path,
    manifest_output: str | Path,
    query_output: str | Path,
    *,
    spec: CorpusSpec,
    query_count: int,
    maximum_files_per_second: float,
    batch_size: int,
    sleep_ms_per_batch: int,
    stop_after: int | None,
    minimum_entry_count: int = MINIMUM_SCALE_ENTRIES,
) -> dict[str, object]:
    spec.validate(minimum_entry_count)
    _validate_controls(
        query_count=query_count,
        maximum_files_per_second=maximum_files_per_second,
        batch_size=batch_size,
        sleep_ms_per_batch=sleep_ms_per_batch,
        stop_after=stop_after,
    )
    root = Path(corpus_root).expanduser().resolve(strict=False)
    manifest = Path(manifest_output).expanduser().resolve(strict=False)
    queries = Path(query_output).expanduser().resolve(strict=False)
    _validate_outputs(root, manifest, queries)
    existing_count = _initialize_or_validate_root(root, spec)
    if existing_count > spec.entry_count:
        raise ValueError("existing corpus exceeds the requested entry count")

    created = 0
    started = time.monotonic()
    for index in range(existing_count, spec.entry_count):
        shard = root / f"shard-{spec.shard_for(index):04d}"
        if not shard.exists():
            shard.mkdir()
        elif not shard.is_dir() or _is_link_or_junction(shard):
            raise ValueError(f"corpus shard is not a real directory: {shard.name}")
        path = root / spec.relative_path(index)
        with path.open("xb"):
            pass
        created += 1
        expected_elapsed = created / maximum_files_per_second
        remaining = expected_elapsed - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(min(remaining, 0.25))
        if created % batch_size == 0 and sleep_ms_per_batch:
            time.sleep(sleep_ms_per_batch / 1000)
        if stop_after is not None and created >= stop_after:
            return {
                "code_version": CODE_VERSION,
                "created_this_run": created,
                "entry_count": spec.entry_count,
                "existing_verified_count": existing_count,
                "status": "STOPPED",
            }

    verified_count = _verify_existing_prefix(root, spec)
    if verified_count != spec.entry_count:
        raise RuntimeError("completed corpus did not verify at the requested entry count")
    _write_completed_outputs(root, manifest, queries, spec, query_count)
    return {
        "code_version": CODE_VERSION,
        "created_this_run": created,
        "entry_count": spec.entry_count,
        "existing_verified_count": existing_count,
        "manifest": str(manifest),
        "queries": str(queries),
        "status": "COMPLETE",
        "verified_file_count": verified_count,
    }


def _plan(root: Path, spec: CorpusSpec, query_count: int) -> dict[str, object]:
    spec.validate()
    _validate_controls(
        query_count=query_count,
        maximum_files_per_second=1,
        batch_size=1,
        sleep_ms_per_batch=0,
        stop_after=None,
    )
    return {
        "automatic_cleanup": False,
        "code_version": CODE_VERSION,
        "content_bytes_per_file": 0,
        "corpus_root": str(root.expanduser().resolve(strict=False)),
        "entry_count": spec.entry_count,
        "execution_authorized": False,
        "query_count": query_count,
        "resume_requires_immutable_ownership_marker": True,
        "shard_count": spec.shard_count,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="prepare_scale_corpus.py")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("plan", "prepare"):
        command = commands.add_parser(name)
        command.add_argument("--corpus-root", required=True)
        command.add_argument("--entry-count", type=int, default=MINIMUM_SCALE_ENTRIES)
        command.add_argument("--shard-count", type=int, default=256)
        command.add_argument("--query-count", type=int, default=256)
        if name == "prepare":
            command.add_argument("--manifest", required=True)
            command.add_argument("--queries", required=True)
            command.add_argument("--maximum-files-per-second", type=float, default=20_000)
            command.add_argument("--batch-size", type=int, default=1_000)
            command.add_argument("--sleep-ms-per-batch", type=int, default=0)
            command.add_argument("--stop-after", type=int)
            command.add_argument("--execute", action="store_true")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        spec = CorpusSpec(args.entry_count, args.shard_count)
        if args.command == "plan":
            print(json.dumps(_plan(Path(args.corpus_root), spec, args.query_count), sort_keys=True))
            return 0
        if not args.execute:
            raise ValueError("corpus preparation requires the explicit --execute switch")
        result = prepare_corpus(
            args.corpus_root,
            args.manifest,
            args.queries,
            spec=spec,
            query_count=args.query_count,
            maximum_files_per_second=args.maximum_files_per_second,
            batch_size=args.batch_size,
            sleep_ms_per_batch=args.sleep_ms_per_batch,
            stop_after=args.stop_after,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "COMPLETE" else 2
    except KeyboardInterrupt:
        print(json.dumps({"code_version": CODE_VERSION, "status": "STOPPED"}, sort_keys=True))
        return 2
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
