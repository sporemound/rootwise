from __future__ import annotations

import ast
from pathlib import Path


def test_inventory_reader_is_query_only_and_core_modules_do_not_import_viewer() -> None:
    root = Path(__file__).parents[1]
    inventory = (root / "src" / "rootwise" / "viewer" / "inventory.py").read_text(
        encoding="utf-8"
    )
    upper = inventory.upper()
    for keyword in ("INSERT ", "UPDATE ", "DELETE ", "REPLACE ", "CREATE TABLE"):
        assert keyword not in upper
    assert "?mode=ro" in inventory
    assert "PRAGMA query_only=ON" in inventory

    violations: list[str] = []
    command_facades = {"cli.py", "legacy_cli.py"}
    core_modules = [
        path
        for path in (root / "src" / "rootwise").glob("*.py")
        if path.name not in command_facades
    ]
    for path in core_modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                violations.extend(
                    alias.name for alias in node.names if alias.name.startswith("rootwise_view")
                )
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("rootwise_view"):
                violations.append(node.module or "")
    assert violations == []
