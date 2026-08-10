"""CLI for Stage 0.12 project-dependency evidence analytics."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from typing import Sequence

from .pipeline import run_dependency_analysis


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rootwise-dependency-graph")
    parser.add_argument("--longitudinal", required=True)
    parser.add_argument("--evidence-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--longitudinal-run")
    args = parser.parse_args(argv)
    try:
        result = run_dependency_analysis(
            args.longitudinal,
            args.evidence_manifest,
            args.output,
            longitudinal_run_id=args.longitudinal_run,
        )
    except (OSError, RuntimeError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

