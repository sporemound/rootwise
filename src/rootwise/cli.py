"""Lazy command facade for the six public Rootwise domains."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence


GROUPS = (
    ("scan", "inventory source metadata and inspect Core artifacts"),
    ("view", "browse a completed inventory and record decisions"),
    ("analyze", "derive structural, ranking, temporal, and fused evidence"),
    ("plan", "create and review non-executable proposals"),
    ("evidence", "run explicitly bounded evidence workflows"),
    ("verify", "evaluate acceptance and release evidence"),
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="rootwise",
        description="Audit-first filesystem inventory and evidence-based planning.",
    )
    commands = root.add_subparsers(dest="command", metavar="COMMAND")
    for name, help_text in GROUPS:
        commands.add_parser(name, add_help=False, help=help_text)
    return root


def _operation_parser(
    group: str, description: str, operations: tuple[tuple[str, str], ...]
) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog=f"rootwise {group}", description=description)
    commands = result.add_subparsers(dest="operation", metavar="OPERATION")
    for name, help_text in operations:
        commands.add_parser(name, add_help=False, help=help_text)
    return result


def _operation(
    group: str,
    values: list[str],
    description: str,
    operations: tuple[tuple[str, str], ...],
) -> tuple[str, list[str]] | None:
    operation_parser = _operation_parser(group, description, operations)
    if not values or values[0] in {"-h", "--help"}:
        operation_parser.print_help()
        return None
    allowed = {name for name, _ in operations}
    if values[0] not in allowed:
        operation_parser.error(f"unknown {group} operation: {values[0]}")
    return values[0], values[1:]


def _deprecation(old: str, new: str) -> None:
    print(
        f"DEPRECATION: '{old}' is a compatibility alias; use '{new}'.",
        file=sys.stderr,
    )


def _run_core(argv: list[str], *, prog: str = "rootwise") -> int:
    from .core_cli import main as core_main

    return core_main(argv, prog=prog)


def _scan(values: list[str]) -> int:
    auxiliary = {"export", "report", "capabilities"}
    if values and values[0] in auxiliary:
        return _run_core(values, prog="rootwise scan")
    return _run_core(["scan", *values])


def _view(values: list[str]) -> int:
    from rootwise_view.cli import main as view_main

    return view_main(values, prog="rootwise view")


def _analyze(values: list[str]) -> int:
    selected = _operation(
        "analyze",
        values,
        "Derive new query-only analysis artifacts from completed snapshots.",
        (
            ("structural", "derive structural roles and relationships"),
            ("rank", "derive objectives, Pareto fronts, and a review queue"),
            ("fuse", "combine structural and content evidence"),
            ("temporal", "compare two completed analysis snapshots"),
            ("synthesize", "join validated evidence into review signals"),
        ),
    )
    if selected is None:
        return 0
    operation, remaining = selected
    if operation == "structural":
        from rootwise_analytics.cli import main as command
    elif operation == "rank":
        from rootwise_analytics.ranking_cli import main as command
    elif operation == "fuse":
        from rootwise_fusion.cli import main as command
    elif operation == "temporal":
        from rootwise_longitudinal.cli import main as command
    else:
        from rootwise_synthesis.cli import main as command
    return command(remaining, prog=f"rootwise analyze {operation}")


def _plan(values: list[str]) -> int:
    selected = _operation(
        "plan",
        values,
        "Create and review proposals that carry no filesystem execution authority.",
        (
            ("optimize", "create validated unapproved proposals"),
            ("approve", "record selection of one independently validated proposal"),
            ("preflight", "compile a metadata-only proposal-member manifest"),
        ),
    )
    if selected is None:
        return 0
    operation, remaining = selected
    if operation == "optimize":
        from rootwise_analytics.optimizer_cli import main as command
    elif operation == "approve":
        from rootwise_approval.cli import main as command
    else:
        from rootwise_preflight.cli import main as command
    return command(remaining, prog=f"rootwise plan {operation}")


def _evidence(values: list[str]) -> int:
    selected = _operation(
        "evidence",
        values,
        "Create explicitly scoped evidence without granting action authority.",
        (
            ("enrich", "read an explicitly selected bounded set of source contents"),
            ("dependency", "import explicit project-dependency evidence"),
            ("history", "derive evidence from a contiguous snapshot chain"),
        ),
    )
    if selected is None:
        return 0
    operation, remaining = selected
    if operation == "enrich":
        from rootwise_enrich.cli import main as command
    elif operation == "dependency":
        from rootwise_dependency.cli import main as command
    else:
        from rootwise_history.cli import main as command
    return command(remaining, prog=f"rootwise evidence {operation}")


def _verify(values: list[str]) -> int:
    selected = _operation(
        "verify",
        values,
        "Evaluate canonical acceptance and release-admission evidence.",
        (("acceptance", "guide, record, evaluate, inspect, admit, or verify evidence"),),
    )
    if selected is None:
        return 0
    _, remaining = selected
    from rootwise_acceptance.cli import main as acceptance_main

    return acceptance_main(remaining, prog="rootwise verify acceptance")


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] in {"-h", "--help"}:
        parser().print_help()
        return 0
    group = values[0]
    remaining = values[1:]
    if group in {"export", "report", "capabilities"}:
        _deprecation(f"rootwise {group}", f"rootwise scan {group}")
        return _run_core(values)
    if group == "scan":
        return _scan(remaining)
    if group == "view":
        return _view(remaining)
    if group == "analyze":
        return _analyze(remaining)
    if group == "plan":
        return _plan(remaining)
    if group == "evidence":
        return _evidence(remaining)
    if group == "verify":
        return _verify(remaining)
    parser().error(f"unknown command: {group}")


if __name__ == "__main__":
    raise SystemExit(main())
