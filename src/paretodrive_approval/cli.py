"""Command-line export for a non-executable Stage 0.8 approval receipt."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from typing import Sequence

from .receipt import export_approval_receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paretodrive-approve")
    parser.add_argument("--plans", required=True)
    parser.add_argument("--declaration", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--maximum-candidates", type=int, default=10_000)
    args = parser.parse_args(argv)
    try:
        result = export_approval_receipt(
            args.plans,
            args.declaration,
            args.receipt,
            maximum_candidates=args.maximum_candidates,
        )
    except (OSError, RuntimeError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
