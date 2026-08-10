"""CLI for snapshot-only structural analytics."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from typing import Sequence

from .pipeline import run_analysis


def main(argv: Sequence[str] | None = None, *, prog: str = "rootwise-analyze") -> int:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--session")
    args = parser.parse_args(argv)
    try:
        result = run_analysis(args.inventory, args.analysis, session_id=args.session)
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
