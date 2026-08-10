from __future__ import annotations

import ast
from pathlib import Path


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def test_enrichment_is_separate_and_has_no_write_or_execution_capability() -> None:
    root = Path(__file__).parents[1] / "src" / "rootwise_enrich"
    forbidden_imports = {"subprocess", "socket", "shutil", "zipfile", "tarfile", "send2trash"}
    forbidden_calls = {
        "os.remove", "os.unlink", "os.rename", "os.replace", "shutil.move", "shutil.copy",
        "shutil.copy2", "Path.unlink", "Path.rename", "Path.replace",
    }
    violations: list[str] = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                violations.extend(alias.name for alias in node.names
                                  if alias.name.split(".")[0] in forbidden_imports)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in forbidden_imports:
                    violations.append(node.module)
            elif isinstance(node, ast.Call) and dotted(node.func) in forbidden_calls:
                violations.append(dotted(node.func))
    assert violations == []
    pipeline = (root / "pipeline.py").read_text(encoding="utf-8")
    reader = (root / "reader.py").read_text(encoding="utf-8")
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in root.glob("*.py")
    )
    assert "rootwise_analytics" not in combined
    assert "allow_content_read" in pipeline
    assert "validate_distinct_volumes" in pipeline
    assert "os.O_RDONLY" in reader and "O_NOFOLLOW" in reader
    assert '"rb"' in reader
    assert '"wb"' not in reader and '"r+b"' not in reader
