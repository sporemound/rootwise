"""CLI for Stage 0.21 acceptance and admission-verification workflows."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Sequence

from .admission import admit_release_candidate
from .admission_verification import verify_admission
from .evaluator import evaluate_acceptance
from .recording import record_gate
from .workflow import gate_guide, initialize_manifest, inspect_report


def _legacy(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="rootwise-acceptance")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    result = evaluate_acceptance(args.manifest, args.report)
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.status == "PASS" else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rootwise-acceptance")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="create a canonical empty evidence manifest")
    initialize.add_argument("--output", required=True)
    initialize.add_argument("--subject-revision", required=True)
    initialize.add_argument("--producer", required=True)
    initialize.add_argument("--created-at", required=True)
    initialize.add_argument("--host-id", required=True)
    initialize.add_argument("--os", dest="os_name", required=True)
    initialize.add_argument("--python", dest="python_version", required=True)
    record = commands.add_parser("record", help="immutably add one externally evidenced gate")
    record.add_argument("--manifest", required=True)
    record.add_argument("--evidence", required=True)
    record.add_argument("--measurements", required=True)
    record.add_argument("--output", required=True)
    record.add_argument("--gate", required=True)
    record.add_argument("--notes", required=True)
    evaluate = commands.add_parser("evaluate", help="evaluate a completed evidence manifest")
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--report", required=True)
    inspect = commands.add_parser("inspect", help="validate and summarize a canonical report")
    inspect.add_argument("--report", required=True)
    admit = commands.add_parser("admit", help="admit a fully verified release candidate")
    admit.add_argument("--report", required=True)
    admit.add_argument("--archive", required=True)
    admit.add_argument("--provenance", required=True)
    admit.add_argument("--verification", required=True)
    admit.add_argument("--output", required=True)
    verify = commands.add_parser("verify-admission", help="verify a bound admission chain")
    verify.add_argument("--receipt", required=True)
    verify.add_argument("--report", required=True)
    verify.add_argument("--archive", required=True)
    verify.add_argument("--provenance", required=True)
    verify.add_argument("--verification", required=True)
    commands.add_parser("guide", help="print required gates and measurement fields as JSON")
    return parser


def _run(argv: list[str]) -> int:
    if argv and argv[0].startswith("--"):
        return _legacy(argv)
    args = _parser().parse_args(argv)
    if args.command == "init":
        initialization = initialize_manifest(
            args.output,
            subject_revision=args.subject_revision,
            producer=args.producer,
            created_at=args.created_at,
            host_id=args.host_id,
            os_name=args.os_name,
            python_version=args.python_version,
        )
        print(json.dumps(asdict(initialization), sort_keys=True))
        return 0
    if args.command == "record":
        recording = record_gate(
            args.manifest,
            args.evidence,
            args.measurements,
            args.output,
            gate_id=args.gate,
            notes=args.notes,
        )
        print(json.dumps(asdict(recording), sort_keys=True))
        return 0
    if args.command == "evaluate":
        evaluation = evaluate_acceptance(args.manifest, args.report)
        print(json.dumps(asdict(evaluation), sort_keys=True))
        return 0 if evaluation.status == "PASS" else 2
    if args.command == "inspect":
        inspection = inspect_report(args.report)
        print(json.dumps(asdict(inspection), sort_keys=True))
        return 0 if inspection.status == "PASS" else 2
    if args.command == "admit":
        admission = admit_release_candidate(
            args.report, args.archive, args.provenance, args.verification, args.output
        )
        print(json.dumps(asdict(admission), sort_keys=True))
        return 0
    if args.command == "verify-admission":
        verification = verify_admission(
            args.receipt, args.report, args.archive, args.provenance, args.verification
        )
        print(json.dumps(asdict(verification), sort_keys=True))
        return 0
    if args.command == "guide":
        print(json.dumps(gate_guide(), sort_keys=True))
        return 0
    raise AssertionError("unreachable acceptance command")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _run(list(sys.argv[1:] if argv is None else argv))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
