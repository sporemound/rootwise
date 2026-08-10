from __future__ import annotations

import json
from pathlib import Path

import pytest

from rootwise_view.cli import main

from .test_viewer_inventory import completed_inventory


def test_headless_search_and_decision_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database, session = completed_inventory(tmp_path)
    result = main([
        "search", "--inventory", str(database), "--session", session,
        "--query", "main.py", "--limit", "10",
    ])
    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert [item["relative_path"] for item in output] == ["project/src/main.py"]

    decisions = tmp_path / "decisions.db"
    result = main([
        "decide", "--inventory", str(database), "--session", session,
        "--decisions", str(decisions), "--path", "project/src/main.py",
        "--decision", "PROTECT", "--note", "source",
    ])
    assert result == 0
    decision = json.loads(capsys.readouterr().out)
    assert decision["revision"] == 1
    assert decision["decision"] == "PROTECT"
