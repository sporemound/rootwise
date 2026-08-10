"""Command-line entry points for the read-only viewer and separate decisions store."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .decisions import DECISIONS, DecisionConflictError, DecisionStore
from .inventory import InventoryReadError, InventoryReader


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="rootwise-view")
    commands = root.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search", help="query one completed inventory session")
    _inventory_arguments(search)
    search.add_argument("--query", default="")
    search.add_argument("--kind", choices=("file", "directory"))
    search.add_argument("--limit", type=int, default=200)
    search.add_argument("--offset", type=int, default=0)

    decide = commands.add_parser("decide", help="record a revision-checked user decision")
    _inventory_arguments(decide)
    decide.add_argument("--decisions", required=True)
    decide.add_argument("--path", required=True)
    decide.add_argument("--decision", choices=DECISIONS, required=True)
    decide.add_argument("--note", default="")
    decide.add_argument("--expected-revision", type=int)

    history = commands.add_parser("history", help="show append-only decision history")
    _inventory_arguments(history)
    history.add_argument("--decisions", required=True)
    history.add_argument("--path", required=True)

    gui = commands.add_parser("gui", help="launch the optional PySide6 viewer")
    _inventory_arguments(gui)
    gui.add_argument("--decisions", required=True)
    return root


def _inventory_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--inventory", required=True)
    command.add_argument("--session", help="defaults to the latest COMPLETE session")


def _session(reader: InventoryReader, supplied: str | None) -> str:
    return supplied if supplied is not None else reader.latest_complete_session()


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "search":
            with InventoryReader(args.inventory) as reader:
                session_id = _session(reader, args.session)
                items = reader.search(
                    session_id, args.query, kind=args.kind, limit=args.limit, offset=args.offset
                )
            print(json.dumps([asdict(item) for item in items], ensure_ascii=False, sort_keys=True))
            return 0

        if args.command in {"decide", "history"}:
            inventory_path = Path(args.inventory)
            with InventoryReader(inventory_path) as reader:
                session_id = _session(reader, args.session)
                if reader.item(session_id, args.path) is None:
                    raise ValueError("decision subject does not exist in the selected inventory")
            with DecisionStore(args.decisions, inventory_path=inventory_path) as store:
                result: object
                if args.command == "history":
                    result = [asdict(item) for item in store.history(session_id, args.path)]
                else:
                    result = asdict(store.set_decision(
                        session_id,
                        args.path,
                        args.decision,
                        note=args.note,
                        expected_revision=args.expected_revision,
                    ))
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0

        try:
            from .gui import run_gui
        except ImportError as exc:
            raise RuntimeError(
                "PySide6 is required for the GUI; install Rootwise with the viewer extra"
            ) from exc
        return run_gui(args.inventory, args.decisions, session_id=args.session)
    except (DecisionConflictError, InventoryReadError, OSError, RuntimeError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
