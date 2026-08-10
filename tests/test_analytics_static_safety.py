from __future__ import annotations

import ast
from pathlib import Path


def test_analytics_does_not_import_scanner_or_access_observed_source_paths() -> None:
    package = Path(__file__).parents[1] / "src" / "rootwise_analytics"
    violations: list[str] = []
    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("rootwise"):
                violations.append(f"{path.name}:{node.lineno}:{node.module}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"open", "read_bytes", "read_text", "rglob", "stat"}:
                    violations.append(f"{path.name}:{node.lineno}:{node.func.attr}")
    assert violations == []
