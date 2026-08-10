from __future__ import annotations

from pathlib import Path


def test_tracked_product_surfaces_use_only_rootwise_namespace() -> None:
    root = Path(__file__).parents[1]
    legacy = "pareto" + "drive"
    checked_roots = [root / "src", root / "docs", root / "tests", root / "tools"]
    violations: list[str] = []
    for checked_root in checked_roots:
        for path in checked_root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(root).as_posix()
            if legacy in relative.casefold():
                violations.append(relative)
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if legacy in content.casefold():
                violations.append(relative)
    for name in ("README.md", "CHANGELOG.md", "LICENSE", "pyproject.toml"):
        if legacy in (root / name).read_text(encoding="utf-8").casefold():
            violations.append(name)
    assert violations == []


def test_distribution_and_console_scripts_use_rootwise_namespace() -> None:
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "rootwise"' in pyproject
    assert 'rootwise = "rootwise.cli:main"' in pyproject
    assert "rootwise-synthesize-evidence" in pyproject

