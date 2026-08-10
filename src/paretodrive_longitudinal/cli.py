"""CLI for Stage 0.11 repeated-snapshot and project-graph analytics."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from typing import Sequence

from .pipeline import run_longitudinal


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paretodrive-longitudinal")
    parser.add_argument("--baseline-analysis", required=True)
    parser.add_argument("--current-analysis", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline-run")
    parser.add_argument("--current-run")
    parser.add_argument("--shared-extension-threshold", type=float, default=0.5)
    args = parser.parse_args(argv)
    try:
        result = run_longitudinal(
            args.baseline_analysis,
            args.current_analysis,
            args.output,
            baseline_analysis_run_id=args.baseline_run,
            current_analysis_run_id=args.current_run,
            shared_extension_threshold=args.shared_extension_threshold,
        )
    except (OSError, RuntimeError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
