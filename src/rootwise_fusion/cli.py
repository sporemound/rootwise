"""CLI for Stage 0.10 snapshot-only enrichment-evidence fusion."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from typing import Sequence

from .pipeline import run_fusion


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rootwise-fuse-evidence")
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--fusion", required=True)
    parser.add_argument("--analysis-run")
    parser.add_argument("--evidence-run")
    args = parser.parse_args(argv)
    try:
        result = run_fusion(
            args.analysis,
            args.evidence,
            args.fusion,
            analysis_run_id=args.analysis_run,
            evidence_run_id=args.evidence_run,
        )
    except (OSError, RuntimeError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
