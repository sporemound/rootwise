from __future__ import annotations

import ast
from pathlib import Path

PRODUCTION = Path(__file__).parents[1] / "src" / "rootwise_acceptance"
FORBIDDEN_IMPORTS = {
    "socket", "subprocess", "sqlite3", "zipfile", "tarfile", "shutil", "send2trash",
    "urllib", "http", "requests", "aiohttp", "ftplib", "rootwise_enrich", "rootwise_preflight",
}
FORBIDDEN_CALLS = {
    "os.remove", "os.unlink", "os.rename", "os.replace", "shutil.move", "shutil.copy",
    "Path.unlink", "Path.rename", "Path.replace", "Path.symlink_to", "Path.hardlink_to",
    "subprocess.run", "subprocess.Popen",
}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def test_acceptance_has_no_scanner_source_executor_network_or_destructive_capability() -> None:
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
            elif isinstance(node, ast.Call) and _dotted(node.func) in FORBIDDEN_CALLS:
                violations.append(f"{path.name}:{node.lineno}: {_dotted(node.func)}")
    assert violations == []
    assert "rootwise-acceptance-evidence-v1" in combined
    assert "INCOMPLETE" in combined and "independent_replication" in combined
