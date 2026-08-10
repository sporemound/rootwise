from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from paretodrive.database import InventoryDatabase
from paretodrive.models import ScanConfig
from paretodrive.scanner import MetadataScanner
from paretodrive_analytics.pipeline import run_analysis
from paretodrive_longitudinal.cli import main as longitudinal_main
from paretodrive_longitudinal.pipeline import LONGITUDINAL_APPLICATION_ID, run_longitudinal

from .helpers import RecordingGuard, actual_volume, make_corpus


def scan(source: Path, inventory_path: Path, root: Path) -> str:
    config = ScanConfig(str(source), str(inventory_path), 100_000, 4, 0)
    with InventoryDatabase(
        inventory_path, RecordingGuard(root)  # type: ignore[arg-type]
    ) as inventory:
        session, _ = MetadataScanner(
            source, actual_volume(source), inventory, config
        ).run()
    return session


def repeated_snapshots(tmp_path: Path) -> tuple[Path, Path, Path, Path, str, str]:
    source = make_corpus(tmp_path / "source")
    inventory = tmp_path / "inventory.db"
    baseline_session = scan(source, inventory, tmp_path)
    baseline_analysis = tmp_path / "baseline-analysis.db"
    baseline_run = run_analysis(
        inventory, baseline_analysis, session_id=baseline_session
    ).run_id

    (source / "project" / "src" / "main.py").write_text(
        "print('metadata changed')\n", encoding="utf-8"
    )
    (source / "unicode" / "café.txt").unlink()
    second = source / "project2"
    (second / "src").mkdir(parents=True)
    (second / "pyproject.toml").write_text("[project]\nname='two'\n", encoding="utf-8")
    (second / "src" / "app.py").write_text("print('two')\n", encoding="utf-8")
    current_session = scan(source, inventory, tmp_path)
    current_analysis = tmp_path / "current-analysis.db"
    current_run = run_analysis(inventory, current_analysis, session_id=current_session).run_id
    return (
        source, inventory, baseline_analysis, current_analysis, baseline_run, current_run
    )


def tree_digest(source: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        digest.update(path.relative_to(source).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_longitudinal_changes_and_project_graph_are_deterministic_and_snapshot_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, inventory, baseline, current, baseline_run, current_run = repeated_snapshots(tmp_path)
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (inventory, baseline, current)
    }
    source_before = tree_digest(source)
    first_path = tmp_path / "history-one.db"
    second_path = tmp_path / "history-two.db"
    first = run_longitudinal(
        baseline,
        current,
        first_path,
        baseline_analysis_run_id=baseline_run,
        current_analysis_run_id=current_run,
        shared_extension_threshold=0.2,
    )
    status = longitudinal_main([
        "--baseline-analysis", str(baseline), "--current-analysis", str(current),
        "--output", str(second_path), "--baseline-run", baseline_run,
        "--current-run", current_run, "--shared-extension-threshold", "0.2",
    ])
    assert status == 0 and json.loads(capsys.readouterr().out)["state"] == "COMPLETE"
    second_db = sqlite3.connect(second_path)
    second_output = str(second_db.execute(
        "SELECT output_digest FROM longitudinal_runs"
    ).fetchone()[0])
    second_db.close()
    assert first.output_digest == second_output
    assert before == {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (inventory, baseline, current)
    }
    assert tree_digest(source) == source_before

    connection = sqlite3.connect(first_path)
    assert connection.execute("PRAGMA application_id").fetchone()[0] == LONGITUDINAL_APPLICATION_ID
    changes = dict(connection.execute(
        "SELECT relative_path,change_type FROM file_changes"
    ))
    assert changes["project/src/main.py"] == "METADATA_CHANGED"
    assert changes["unicode/café.txt"] == "REMOVED"
    assert changes["project2/src/app.py"] == "ADDED"
    assert changes["media/final exports/render.wav"] == "METADATA_UNCHANGED"
    assert connection.execute(
        "SELECT temporal_state FROM project_nodes WHERE project_id='project2'"
    ).fetchone()[0] == "ADDED"
    edge = connection.execute(
        "SELECT directed,evidence_json FROM project_edges "
        "WHERE relationship_type='SHARED_EXTENSION_PROFILE'"
    ).fetchone()
    assert edge is not None and edge[0] == 0
    assert json.loads(edge[1])["dependency_claim"] is False
    assert connection.execute(
        "SELECT MAX(dependency_evidence_coverage) FROM project_graph_features"
    ).fetchone()[0] == 0.0
    assert {row[0] for row in connection.execute(
        "SELECT stage_name FROM longitudinal_stages"
    )} == {"validate", "file_changes", "directory_changes", "project_graph"}
    connection.close()


def test_scan_error_makes_removal_ambiguous(tmp_path: Path) -> None:
    _, inventory, baseline, current, baseline_run, current_run = repeated_snapshots(tmp_path)
    inventory_db = sqlite3.connect(inventory)
    current_session = str(inventory_db.execute(
        "SELECT scan_session_id FROM scan_sessions ORDER BY rowid DESC LIMIT 1"
    ).fetchone()[0])
    inventory_db.execute(
        "INSERT INTO scan_errors(scan_session_id,relative_path,operation,error_type,error_code,message) "
        "VALUES(?,?,?,?,?,?)",
        (current_session, "unicode", "fixture", "SyntheticError", None, "test only"),
    )
    inventory_db.commit()
    inventory_db.close()
    output = tmp_path / "history.db"
    run_longitudinal(
        baseline, current, output,
        baseline_analysis_run_id=baseline_run,
        current_analysis_run_id=current_run,
    )
    connection = sqlite3.connect(output)
    assert connection.execute(
        "SELECT change_type,confidence_state FROM file_changes WHERE relative_path='unicode/café.txt'"
    ).fetchone() == ("REMOVED", "AMBIGUOUS_ERROR_REGION")
    assert connection.execute(
        "SELECT ambiguous_count FROM directory_change_features WHERE relative_path='unicode'"
    ).fetchone()[0] == 1
    connection.close()


def test_longitudinal_rejects_same_session_and_inventory_tampering(tmp_path: Path) -> None:
    _, inventory, baseline, current, baseline_run, current_run = repeated_snapshots(tmp_path)
    duplicate_analysis = tmp_path / "duplicate-analysis.db"
    inventory_db = sqlite3.connect(inventory)
    current_session = str(inventory_db.execute(
        "SELECT scan_session_id FROM scan_sessions ORDER BY rowid DESC LIMIT 1"
    ).fetchone()[0])
    inventory_db.close()
    run_analysis(inventory, duplicate_analysis, session_id=current_session)
    with pytest.raises(ValueError, match="distinct inventory sessions"):
        run_longitudinal(current, duplicate_analysis, tmp_path / "same-session.db")
    inventory_db = sqlite3.connect(inventory)
    inventory_db.execute(
        "UPDATE files SET logical_bytes=logical_bytes+1 WHERE scan_session_id=("
        "SELECT scan_session_id FROM scan_sessions ORDER BY rowid DESC LIMIT 1) "
        "AND rowid=(SELECT MAX(rowid) FROM files)"
    )
    inventory_db.commit()
    inventory_db.close()
    with pytest.raises(ValueError, match="inventory logical digest"):
        run_longitudinal(
            baseline, current, tmp_path / "tampered.db",
            baseline_analysis_run_id=baseline_run,
            current_analysis_run_id=current_run,
        )
