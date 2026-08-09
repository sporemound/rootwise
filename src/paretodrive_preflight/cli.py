"""CLI for Stage 0.9 metadata-only executor-preflight compilation."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from typing import Sequence

from .compiler import compile_preflight_manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paretodrive-preflight")
    parser.add_argument("--plans", required=True)
    parser.add_argument("--approval-receipt", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--maximum-inventory-rows", type=int, default=10_000_000)
    parser.add_argument("--maximum-members", type=int, default=1_000_000)
    args = parser.parse_args(argv)
    try:
        result = compile_preflight_manifest(
            args.plans,
            args.approval_receipt,
            args.inventory,
            args.manifest,
            maximum_inventory_rows=args.maximum_inventory_rows,
            maximum_members=args.maximum_members,
        )
    except (OSError, RuntimeError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
