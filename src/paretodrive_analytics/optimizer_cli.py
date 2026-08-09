"""CLI for proposal-only Stage 0.6 optimization."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from typing import Sequence

from .optimizer_pipeline import run_optimization


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paretodrive-optimize")
    parser.add_argument("--ranking", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--plans", required=True)
    parser.add_argument("--maximum-archive-bytes", type=int, required=True)
    parser.add_argument("--destination-available-bytes", type=int, required=True)
    parser.add_argument("--destination-safety-margin", type=float, default=0.15)
    parser.add_argument("--generations", type=int, default=20)
    parser.add_argument("--max-frontier-states", type=int, default=5_000)
    args = parser.parse_args(argv)
    try:
        result = run_optimization(
            args.ranking,
            args.decisions,
            args.plans,
            maximum_archive_bytes=args.maximum_archive_bytes,
            destination_available_bytes=args.destination_available_bytes,
            destination_safety_margin=args.destination_safety_margin,
            generations=args.generations,
            max_frontier_states=args.max_frontier_states,
        )
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
