from __future__ import annotations

import ast
import importlib
import tomllib
from pathlib import Path
from typing import Sequence

import pytest

from rootwise import cli, legacy_cli


GROUPS = {"scan", "view", "analyze", "plan", "evidence", "verify"}

COMPATIBILITY_SCRIPTS = {
    "rootwise-view": "rootwise.legacy_cli:view",
    "rootwise-analyze": "rootwise.legacy_cli:analyze",
    "rootwise-rank": "rootwise.legacy_cli:rank",
    "rootwise-optimize": "rootwise.legacy_cli:optimize",
    "rootwise-enrich": "rootwise.legacy_cli:enrich",
    "rootwise-approve": "rootwise.legacy_cli:approve",
    "rootwise-preflight": "rootwise.legacy_cli:preflight",
    "rootwise-fuse-evidence": "rootwise.legacy_cli:fuse",
    "rootwise-longitudinal": "rootwise.legacy_cli:temporal",
    "rootwise-dependency-graph": "rootwise.legacy_cli:dependency",
    "rootwise-history": "rootwise.legacy_cli:history",
    "rootwise-synthesize-evidence": "rootwise.legacy_cli:synthesize",
    "rootwise-acceptance": "rootwise.legacy_cli:acceptance",
}


def test_root_help_exposes_only_six_domain_groups(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--help"]) == 0
    output = capsys.readouterr()
    for group in GROUPS:
        assert group in output.out
    for legacy in ("rootwise-view", "rootwise-rank", "rootwise-acceptance"):
        assert legacy not in output.out
    assert output.err == ""


def test_installed_scripts_have_one_canonical_root_and_explicit_compatibility_wrappers() -> None:
    project = Path(__file__).parents[1]
    configuration = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = configuration["project"]["scripts"]
    assert scripts["rootwise"] == "rootwise.cli:main"
    assert {name: scripts[name] for name in COMPATIBILITY_SCRIPTS} == COMPATIBILITY_SCRIPTS


def test_group_help_does_not_import_optional_implementations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = Path(cli.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = {
        node.module.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not top_level_imports.intersection({
        "rootwise_view",
        "rootwise_analytics",
        "rootwise_enrich",
        "rootwise_acceptance",
    })
    assert cli.main(["analyze", "--help"]) == 0
    output = capsys.readouterr()
    assert "rootwise analyze" in output.out
    assert "structural" in output.out
    assert output.err == ""


@pytest.mark.parametrize(
    ("arguments", "module_name", "expected_arguments", "expected_prog"),
    (
        (["view", "search", "--limit", "1"], "rootwise_view.cli", ["search", "--limit", "1"], "rootwise view"),
        (["analyze", "structural", "--inventory", "i"], "rootwise_analytics.cli", ["--inventory", "i"], "rootwise analyze structural"),
        (["analyze", "rank", "--analysis", "a"], "rootwise_analytics.ranking_cli", ["--analysis", "a"], "rootwise analyze rank"),
        (["analyze", "fuse", "--analysis", "a"], "rootwise_fusion.cli", ["--analysis", "a"], "rootwise analyze fuse"),
        (["analyze", "temporal", "--baseline-analysis", "a"], "rootwise_longitudinal.cli", ["--baseline-analysis", "a"], "rootwise analyze temporal"),
        (["analyze", "synthesize", "--ranking", "r"], "rootwise_synthesis.cli", ["--ranking", "r"], "rootwise analyze synthesize"),
        (["plan", "optimize", "--ranking", "r"], "rootwise_analytics.optimizer_cli", ["--ranking", "r"], "rootwise plan optimize"),
        (["plan", "approve", "--plans", "p"], "rootwise_approval.cli", ["--plans", "p"], "rootwise plan approve"),
        (["plan", "preflight", "--plans", "p"], "rootwise_preflight.cli", ["--plans", "p"], "rootwise plan preflight"),
        (["evidence", "enrich", "--inventory", "i"], "rootwise_enrich.cli", ["--inventory", "i"], "rootwise evidence enrich"),
        (["evidence", "dependency", "--longitudinal", "l"], "rootwise_dependency.cli", ["--longitudinal", "l"], "rootwise evidence dependency"),
        (["evidence", "history", "--chain-manifest", "m"], "rootwise_history.cli", ["--chain-manifest", "m"], "rootwise evidence history"),
        (["verify", "acceptance", "guide"], "rootwise_acceptance.cli", ["guide"], "rootwise verify acceptance"),
    ),
)
def test_grouped_command_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    module_name: str,
    expected_arguments: list[str],
    expected_prog: str,
) -> None:
    module = importlib.import_module(module_name)
    observed: dict[str, object] = {}

    def fake_main(argv: Sequence[str] | None = None, *, prog: str) -> int:
        observed.update({"arguments": list(argv or ()), "prog": prog})
        return 37

    monkeypatch.setattr(module, "main", fake_main)
    assert cli.main(arguments) == 37
    assert observed == {"arguments": expected_arguments, "prog": expected_prog}


def test_scan_group_preserves_direct_scan_and_nests_auxiliary_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[list[str], str]] = []

    def fake_core(argv: list[str], *, prog: str = "rootwise") -> int:
        observed.append((argv, prog))
        return 0

    monkeypatch.setattr(cli, "_run_core", fake_core)
    assert cli.main(["scan", "--source", "s", "--database", "d"]) == 0
    assert cli.main(["scan", "report", "--database", "d"]) == 0
    assert observed == [
        (["scan", "--source", "s", "--database", "d"], "rootwise"),
        (["report", "--database", "d"], "rootwise scan"),
    ]


def test_legacy_core_operation_warns_and_dispatches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    observed: list[str] = []

    def fake_core(argv: list[str], *, prog: str = "rootwise") -> int:
        observed.extend(argv)
        return 0

    monkeypatch.setattr(cli, "_run_core", fake_core)
    assert cli.main(["report", "--database", "inventory.db"]) == 0
    output = capsys.readouterr()
    assert observed == ["report", "--database", "inventory.db"]
    assert "rootwise scan report" in output.err


def test_legacy_console_wrapper_warns_and_preserves_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = importlib.import_module("rootwise_view.cli")
    monkeypatch.setattr(module, "main", lambda: 19)
    assert legacy_cli.view() == 19
    output = capsys.readouterr()
    assert "rootwise-view" in output.err
    assert "rootwise view" in output.err


@pytest.mark.parametrize(
    ("arguments", "expected_usage"),
    (
        (["view", "search", "--help"], "usage: rootwise view search"),
        (["analyze", "rank", "--help"], "usage: rootwise analyze rank"),
        (["plan", "approve", "--help"], "usage: rootwise plan approve"),
        (["evidence", "dependency", "--help"], "usage: rootwise evidence dependency"),
        (["verify", "acceptance", "--help"], "usage: rootwise verify acceptance"),
    ),
)
def test_leaf_help_uses_canonical_program_name(
    arguments: list[str],
    expected_usage: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(arguments)
    assert raised.value.code == 0
    output = capsys.readouterr()
    assert expected_usage in output.out
    assert output.err == ""
