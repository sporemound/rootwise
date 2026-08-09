from __future__ import annotations

import ast
from pathlib import Path


def test_inventory_reader_contains_no_mutating_sql_and_scanner_does_not_import_viewer() -> None:
    root = Path(__file__).parents[1]
    inventory = (root / "src" / "paretodrive_view" / "inventory.py").read_text(encoding="utf-8")
    upper = inventory.upper()
    for keyword in ("INSERT ", "UPDATE ", "DELETE ", "REPLACE ", "CREATE TABLE"):
        assert keyword not in upper
    assert "?mode=ro" in inventory
    assert "PRAGMA query_only=ON" in inventory

    violations: list[str] = []
    for path in (root / "src" / "paretodrive").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                violations.extend(
                    alias.name for alias in node.names if alias.name.startswith("paretodrive_view")
                )
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("paretodrive_view"):
                violations.append(node.module or "")
    assert violations == []
