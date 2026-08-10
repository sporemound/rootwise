"""CLI for Stage 0.16 acceptance and scale evidence evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Sequence

from .evaluator import evaluate_acceptance


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rootwise-acceptance")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    try:
        result = evaluate_acceptance(args.manifest, args.report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
