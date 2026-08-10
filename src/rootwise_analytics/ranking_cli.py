"""CLI for 0.5 objective intervals, Pareto fronts, and review batches."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Sequence

from .ranking_pipeline import run_ranking


def main(argv: Sequence[str] | None = None, *, prog: str = "rootwise-rank") -> int:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--ranking", required=True)
    parser.add_argument("--analysis-run")
    parser.add_argument("--review-limit", type=int, default=100)
    args = parser.parse_args(argv)
    try:
        result = run_ranking(args.analysis, args.ranking,
            analysis_run_id=args.analysis_run, review_limit=args.review_limit)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
