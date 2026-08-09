from __future__ import annotations

import ast
from pathlib import Path

PRODUCTION = Path(__file__).parents[1] / "src" / "paretodrive_preflight"
FORBIDDEN_IMPORTS = {
    "socket", "subprocess", "zipfile", "tarfile", "shutil", "send2trash", "urllib", "http",
    "requests", "aiohttp", "ftplib", "paretodrive_enrich",
}
FORBIDDEN_CALLS = {
    "os.remove", "os.unlink", "os.rename", "os.replace", "shutil.move", "shutil.copy",
    "Path.unlink", "Path.rename", "Path.replace", "Path.symlink_to", "Path.hardlink_to",
    "subprocess.run", "subprocess.Popen",
}


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def test_preflight_has_no_content_read_executor_network_or_destructive_capability() -> None:
    violations: list[str] = []
    combined = ""
    for path in sorted(PRODUCTION.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        combined += source
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                        violations.append(f"{path.name}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                    violations.append(f"{path.name}:{node.lineno}: from {node.module}")
            elif isinstance(node, ast.Call) and dotted(node.func) in FORBIDDEN_CALLS:
                violations.append(f"{path.name}:{node.lineno}: {dotted(node.func)}")
    assert violations == []
    assert "mode=ro" in combined and "query_only=ON" in combined
    assert "source_content_read_authorized\": False" in combined
    assert "archive_creation_authorized\": False" in combined
    assert "NO_ARCHIVE_WAS_CREATED" in combined
