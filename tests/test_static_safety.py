from __future__ import annotations

import ast
from pathlib import Path


PRODUCTION = Path(__file__).parents[1] / "src" / "rootwise"
FORBIDDEN_IMPORT_ROOTS = {
    "socket", "subprocess", "zipfile", "tarfile", "shutil", "send2trash",
    "urllib", "http", "requests", "aiohttp", "ftplib",
}
FORBIDDEN_CALLS = {
    "os.remove", "os.unlink", "os.rename", "os.renames", "os.replace",
    "shutil.move", "shutil.copy", "shutil.copy2", "shutil.copytree",
    "Path.unlink", "Path.rename", "Path.replace", "Path.symlink_to", "Path.hardlink_to",
    "os.symlink", "os.link", "subprocess.run", "subprocess.Popen", "subprocess.call",
}


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def test_production_has_no_forbidden_imports_or_calls() -> None:
    violations: list[str] = []
    for path in sorted(PRODUCTION.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_IMPORT_ROOTS:
                        violations.append(f"{path.name}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in FORBIDDEN_IMPORT_ROOTS:
                    violations.append(f"{path.name}:{node.lineno}: from {node.module}")
            elif isinstance(node, ast.Call) and dotted(node.func) in FORBIDDEN_CALLS:
                violations.append(f"{path.name}:{node.lineno}: {dotted(node.func)}")
    assert violations == []


def test_scanner_has_no_content_open_calls() -> None:
    path = PRODUCTION / "scanner.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [dotted(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert "open" not in calls
    assert "Path.open" not in calls
