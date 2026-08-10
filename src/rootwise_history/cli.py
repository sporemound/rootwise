"""CLI for Stage 0.13 multi-snapshot temporal analytics."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from typing import Sequence

from .pipeline import run_history_analysis


def main(argv: Sequence[str] | None = None, *, prog: str = "rootwise-history") -> int:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--chain-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_history_analysis(args.chain_manifest, args.output)
    except (OSError, RuntimeError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
