"""Minimal command-line interface for scanning, export, and read-only reports."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path
from typing import Sequence

from .canonicalize import export_canonical
from .capabilities import detect_capabilities
from .database import InventoryDatabase
from .models import ScanConfig, VolumeInfo
from .reporting import session_report
from .scanner import CancellationToken, MetadataScanner
from .volume import resolve_volume
from .write_guard import WriteGuard


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="paretodrive")
    commands = root.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("--source", required=True)
    scan.add_argument("--database", required=True)
    scan.add_argument("--max-files-per-second", type=float, default=250.0)
    scan.add_argument("--batch-size", type=int, default=256)
    scan.add_argument("--sleep-ms-per-batch", type=int, default=25)
    scan.add_argument("--stop-after", type=int)
    scan.add_argument("--resume", action="store_true")
    scan.add_argument("--dry-run", action="store_true")
    scan.add_argument("--canonical-export")
    scan.add_argument("--error-log")
    scan.add_argument("--max-rss-mib", type=int, default=512, help="0 disables the RSS ceiling")
    scan.add_argument(
        "--min-free-destination-mib", type=int, default=1024,
        help="0 disables the destination free-space floor",
    )
    scan.add_argument("--active-window-seconds", type=float, default=30.0)
    scan.add_argument("--cooldown-seconds", type=float, default=2.0)
    export = commands.add_parser("export")
    export.add_argument("--source", required=True, help="source root used for volume boundary")
    export.add_argument("--database", required=True)
    export.add_argument("--session", required=True)
    export.add_argument("--output", required=True)
    report = commands.add_parser("report")
    report.add_argument("--database", required=True)
    capabilities = commands.add_parser("capabilities")
    capabilities.add_argument("--path", required=True)
    return root


def _boundaries(source: Path, database_path: Path) -> tuple[WriteGuard, VolumeInfo]:
    if not source.is_dir():
        raise ValueError(f"source is not a directory: {source}")
    database_path.parent.resolve(strict=True)
    source_volume = resolve_volume(source)
    guard = WriteGuard(source_volume, database_path.parent)
    guard.authorize(database_path)
    return guard, source_volume


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "capabilities":
        print(json.dumps(detect_capabilities(args.path).to_dict(), indent=2, sort_keys=True))
        return 0
    if args.command == "report":
        print(json.dumps(session_report(args.database), indent=2, sort_keys=True))
        return 0
    source = Path(args.source).expanduser().resolve(strict=True)
    database_path = Path(args.database).expanduser().resolve(strict=False)
    guard, source_volume = _boundaries(source, database_path)
    if args.command == "export":
        with InventoryDatabase(database_path, guard) as database:
            digest, records = export_canonical(database, guard, args.session, args.output)
        print(json.dumps({"sha256": digest, "records": records}, sort_keys=True))
        return 0
    if args.dry_run:
        print(json.dumps({"boundary": "validated", "source_volume": source_volume.identity}))
        return 0
    config = ScanConfig(
        source=str(source), database=str(database_path),
        max_files_per_second=args.max_files_per_second, batch_size=args.batch_size,
        sleep_ms_per_batch=args.sleep_ms_per_batch, stop_after=args.stop_after,
        max_rss_mib=None if args.max_rss_mib == 0 else args.max_rss_mib,
        min_free_destination_mib=(
            None if args.min_free_destination_mib == 0 else args.min_free_destination_mib
        ),
        active_window_seconds=args.active_window_seconds,
        cooldown_seconds=args.cooldown_seconds,
    )
    cancellation = CancellationToken()
    error_log = guard.authorize(args.error_log) if args.error_log else None
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda *_: cancellation.cancel())
    try:
        with InventoryDatabase(database_path, guard) as database:
            scanner = MetadataScanner(source, source_volume, database, config, cancellation)
            session_id, state = scanner.run(resume=args.resume)
            result: dict[str, object] = {"session": session_id, "state": state.value}
            if args.canonical_export and state.value == "COMPLETE":
                digest, records = export_canonical(
                    database, guard, session_id, args.canonical_export
                )
                result.update({"sha256": digest, "records": records})
        print(json.dumps(result, sort_keys=True))
        return 0 if state.value == "COMPLETE" else 2
    except Exception as exc:
        if error_log is not None:
            payload = (json.dumps(
                {"error_type": type(exc).__name__, "message": str(exc), "operation": "scan"},
                sort_keys=True,
            ) + "\n").encode("utf-8")
            with guard.open_new_binary(error_log) as (_, stream):
                stream.write(payload)
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGINT, previous)


if __name__ == "__main__":
    raise SystemExit(main())
