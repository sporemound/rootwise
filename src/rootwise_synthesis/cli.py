"""CLI for Stage 0.14 multi-evidence review synthesis."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from typing import Sequence

from .pipeline import run_synthesis


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rootwise-synthesize-evidence")
    parser.add_argument("--ranking", required=True)
    parser.add_argument("--fusion", required=True)
    parser.add_argument("--dependency", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_synthesis(
            args.ranking, args.fusion, args.dependency, args.history, args.output
        )
    except (OSError, RuntimeError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

