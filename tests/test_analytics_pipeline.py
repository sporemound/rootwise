from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

import paretodrive_analytics.pipeline as pipeline
from paretodrive_analytics.cli import main
from paretodrive_analytics.pipeline import ANALYSIS_APPLICATION_ID, run_analysis

from .test_viewer_inventory import completed_inventory


def test_structural_analysis_is_deterministic_explainable_and_snapshot_only(tmp_path: Path) -> None:
    inventory, session = completed_inventory(tmp_path)
    before = hashlib.sha256(inventory.read_bytes()).hexdigest()
    first_path = tmp_path / "analysis-one.db"
    second_path = tmp_path / "analysis-two.db"
    first = run_analysis(inventory, first_path, session_id=session)
    second = run_analysis(inventory, second_path, session_id=session)
    assert first.state == second.state == "COMPLETE"
    assert first.input_digest == second.input_digest
    assert first.output_digest == second.output_digest
    assert first.role_count == 15
    assert first.project_count == 1
    assert hashlib.sha256(inventory.read_bytes()).hexdigest() == before

    connection = sqlite3.connect(first_path)
    assert connection.execute("PRAGMA application_id").fetchone()[0] == ANALYSIS_APPLICATION_ID
    roles = dict(connection.execute(
        "SELECT relative_path,role FROM item_roles WHERE run_id=?", (first.run_id,)
    ))
    assert roles["project/pyproject.toml"] == "PROJECT_METADATA"
    assert roles["project/src/main.py"] == "SOURCE"
    assert roles["project/.cache/item.bin"] == "CACHE"
    assert roles["project/build/output.dat"] == "BUILD_OUTPUT"
    assert roles["project/.venv/lib/site-packages/dependency.py"] == "DEPENDENCY_ENVIRONMENT"
    assert roles["media/final exports/render.wav"] == "FINAL_EXPORT"
    root = connection.execute(
        "SELECT recursive_bytes,file_count,directory_count,role_counts_json,role_coherence "
        "FROM directory_aggregates WHERE run_id=? AND relative_path=''", (first.run_id,)
    ).fetchone()
    assert root is not None
    inventory_connection = sqlite3.connect(inventory)
    expected_bytes = inventory_connection.execute(
        "SELECT SUM(logical_bytes) FROM files WHERE scan_session_id=?", (session,)
    ).fetchone()[0]
    inventory_connection.close()
    assert root[0] == expected_bytes
    assert root[1] == 15
    assert root[2] == 15
    assert json.loads(root[3])["SOURCE"] == 1
    assert 0.0 <= root[4] <= 1.0
    project = connection.execute(
        "SELECT relative_path,boundary_score,markers_json FROM projects WHERE run_id=?",
        (first.run_id,),
    ).fetchone()
    assert project == ("project", 5, '["pyproject.toml"]')
    stages = connection.execute(
        "SELECT stage_name,state,input_digest,output_digest FROM analysis_stages "
        "WHERE run_id=? ORDER BY stage_name", (first.run_id,),
    ).fetchall()
    assert {row[0] for row in stages} == {
        "roles", "directory_aggregates", "projects", "relationships"
    }
    assert all(row[1] == "COMPLETE" and len(row[2]) == 64 and len(row[3]) == 64 for row in stages)
    assert connection.execute(
        "SELECT COUNT(*) FROM relationships WHERE run_id=? AND relationship_type='HAS_ROLE'",
        (first.run_id,),
    ).fetchone()[0] > 0
    connection.close()


def test_analysis_cli_and_destination_boundary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inventory, session = completed_inventory(tmp_path)
    analysis = tmp_path / "analysis.db"
    assert main([
        "--inventory", str(inventory), "--analysis", str(analysis), "--session", session
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "COMPLETE"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    try:
        run_analysis(inventory, elsewhere / "analysis.db", session_id=session)
    except ValueError as exc:
        assert "external directory" in str(exc)
    else:
        raise AssertionError("analysis destination boundary was not enforced")


def test_failed_analysis_is_recorded_and_cannot_appear_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory, session = completed_inventory(tmp_path)
    analysis = tmp_path / "failed-analysis.db"

    def fail_classification(_: object) -> object:
        raise RuntimeError("injected analysis failure")

    monkeypatch.setattr(pipeline, "classify", fail_classification)
    with pytest.raises(RuntimeError, match="injected analysis failure"):
        run_analysis(inventory, analysis, session_id=session)
    connection = sqlite3.connect(analysis)
    state, output_digest, error = connection.execute(
        "SELECT state,output_digest,error FROM analysis_runs"
    ).fetchone()
    connection.close()
    assert state == "FAILED"
    assert output_digest is None
    assert "injected analysis failure" in error
