"""Explicitly acknowledged CLI for content-reading enrichment."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from typing import Sequence

from rootwise.errors import RootwiseError

from .pipeline import run_enrichment
from .reader import ReadPolicy


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rootwise-enrich")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--allow-content-read", action="store_true", required=True)
    parser.add_argument("--chunk-bytes", type=int, default=1_048_576)
    parser.add_argument("--sample-bytes", type=int, default=65_536)
    parser.add_argument("--maximum-bytes-per-second", type=int, default=16_777_216)
    parser.add_argument("--maximum-files", type=int, default=10_000)
    parser.add_argument("--stop-after", type=int)
    args = parser.parse_args(argv)
    try:
        result = run_enrichment(
            args.inventory, args.source, args.selection, args.evidence,
            allow_content_read=args.allow_content_read,
            read_policy=ReadPolicy(
                args.chunk_bytes, args.sample_bytes, args.maximum_bytes_per_second
            ),
            maximum_files=args.maximum_files,
            stop_after=args.stop_after,
        )
    except (OSError, RootwiseError, PermissionError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
