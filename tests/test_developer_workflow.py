from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools import bootstrap, smoke


def test_bootstrap_profiles_are_locked_and_install_the_project(tmp_path: Path) -> None:
    root = tmp_path / "rootwise"
    root.mkdir()
    environment = root / ".venv-new"

    core = bootstrap.command_plan(
        root, environment, "core", platform_name="win32", bootstrap_python="py"
    )
    assert [label for label, _ in core] == [
        "create_environment",
        "install_development_dependencies",
        "install_rootwise",
        "smoke",
    ]
    assert core[-2][1][-3:] == ["--no-deps", "--editable", "."]
    assert core[-1][1][-2:] == [
        "--rootwise",
        str(environment / "Scripts" / "rootwise.exe"),
    ]

    full = bootstrap.command_plan(
        root, environment, "full", platform_name="win32", bootstrap_python="py"
    )
    labels = [label for label, _ in full]
    assert labels[1:6] == [
        "install_development_dependencies",
        "install_viewer",
        "install_analytics",
        "install_optimizer",
        "install_enrichment",
    ]
    for label, command in full[1:6]:
        assert label.startswith("install_")
        assert "--require-hashes" in command

    headless = bootstrap.command_plan(
        root, environment, "headless", platform_name="linux", bootstrap_python="python3.12"
    )
    assert "install_viewer" not in {label for label, _ in headless}
    with pytest.raises(ValueError, match="Viewer lock is Windows-only"):
        bootstrap.command_plan(root, environment, "full", platform_name="linux")


def test_bootstrap_environment_must_be_repository_local_virtualenv(tmp_path: Path) -> None:
    root = tmp_path / "rootwise"
    root.mkdir()
    assert bootstrap.environment_path(root, ".venv") == root / ".venv"
    with pytest.raises(ValueError, match="child of the repository"):
        bootstrap.environment_path(root, "..")

    occupied = root / "occupied"
    occupied.mkdir()
    with pytest.raises(ValueError, match="not a Python virtual environment"):
        bootstrap.environment_path(root, "occupied")


def test_bootstrap_does_not_treat_successful_pip_stderr_as_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PYTHONPATH", "must-not-leak")
    assert "PYTHONPATH" not in bootstrap.clean_environment()
    completed = subprocess.CompletedProcess(
        args=["python", "-m", "pip"], returncode=0, stdout="installed\n", stderr="notice\n"
    )
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: completed)
    assert bootstrap.execute(
        "install", ["python", "-m", "pip"], root=tmp_path, timeout_seconds=10
    )
    result = json.loads(capsys.readouterr().out)
    assert result["exit_code"] == 0
    assert result["stderr"] == "notice\n"


def test_installed_command_smoke_passes_for_all_six_domains(
    capsys: pytest.CaptureFixture[str],
) -> None:
    executable_name = "rootwise.exe" if sys.platform == "win32" else "rootwise"
    executable = Path(sys.executable).with_name(executable_name)
    assert smoke.main(["--rootwise", str(executable)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PASS"
    assert len(result["checks"]) == 7
    assert all(check["passed"] for check in result["checks"])


def test_smoke_reports_a_missing_installed_command_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert smoke.main(["--rootwise", str(tmp_path / "missing-rootwise")]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL"
    assert result["error"].startswith("FileNotFoundError:")


def test_onboarding_documents_one_command_setup_and_expected_results() -> None:
    root = Path(__file__).parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    development = (root / "DEVELOPMENT.md").read_text(encoding="utf-8")
    for expected in (
        "tools\\bootstrap.py --profile full",
        '"status": "READY"',
        "tools\\smoke.py",
        '"status": "PASS"',
    ):
        assert expected in development
    assert "tools\\bootstrap.py --profile full" in readme
