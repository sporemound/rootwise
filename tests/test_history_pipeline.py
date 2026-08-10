from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from rootwise_analytics.pipeline import run_analysis
from rootwise_history.cli import main as history_main
from rootwise_history.pipeline import HISTORY_APPLICATION_ID, run_history_analysis
from rootwise_longitudinal.pipeline import run_longitudinal

from .test_longitudinal_pipeline import repeated_snapshots, scan, tree_digest


def history_fixture(
    tmp_path: Path, *, ambiguous_removal: bool = False
) -> tuple[Path, Path, Path, list[Path]]:
    source, inventory, baseline, current, baseline_run, current_run = repeated_snapshots(tmp_path)
    if ambiguous_removal:
        inventory_db = sqlite3.connect(inventory)
        current_session = str(inventory_db.execute(
            "SELECT scan_session_id FROM scan_sessions ORDER BY rowid DESC LIMIT 1"
        ).fetchone()[0])
        inventory_db.execute(
            "INSERT INTO scan_errors(scan_session_id,relative_path,operation,error_type,error_code,"
            "message) VALUES(?,?,?,?,?,?)",
            (current_session, "unicode", "fixture", "SyntheticError", None, "test only"),
        )
        inventory_db.commit()
        inventory_db.close()
    (source / "project" / "src" / "main.py").write_text(
        "print('metadata changed for the third snapshot with a distinct size')\n", encoding="utf-8"
    )
    (source / "project2" / "src" / "app.py").unlink()
    (source / "project" / "src" / "new.py").write_text("NEW_VALUE = 3\n", encoding="utf-8")
    third_session = scan(source, inventory, tmp_path)
    third = tmp_path / "third-analysis.db"
    third_run = run_analysis(inventory, third, session_id=third_session).run_id

    first_link = tmp_path / "transition-01.db"
    first = run_longitudinal(
        baseline, current, first_link,
        baseline_analysis_run_id=baseline_run, current_analysis_run_id=current_run,
        shared_extension_threshold=0.2,
    )
    second_link = tmp_path / "transition-02.db"
    second = run_longitudinal(
        current, third, second_link,
        baseline_analysis_run_id=current_run, current_analysis_run_id=third_run,
        shared_extension_threshold=0.2,
    )
    manifest = tmp_path / "history-chain.json"
    manifest.write_text(json.dumps({
        "schema": "rootwise-longitudinal-chain-v1",
        "created_at": "2026-08-09T00:00:00Z",
        "label": "synthetic-three-snapshot-history",
        "links": [
            {"database": first_link.name, "run_id": first.run_id,
             "output_digest": first.output_digest},
            {"database": second_link.name, "run_id": second.run_id,
             "output_digest": second.output_digest},
        ],
    }, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    return source, inventory, manifest, [first_link, second_link]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_history_is_deterministic_contiguous_and_snapshot_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, inventory, manifest, links = history_fixture(tmp_path)
    inputs = [inventory, manifest, *links]
    before = {path: _sha256(path) for path in inputs}
    source_before = tree_digest(source)
    first_path = tmp_path / "history-one.db"
    second_path = tmp_path / "history-two.db"
    first = run_history_analysis(manifest, first_path)
    status = history_main(["--chain-manifest", str(manifest), "--output", str(second_path)])
    assert status == 0
    assert json.loads(capsys.readouterr().out)["snapshot_count"] == 3
    second_db = sqlite3.connect(second_path)
    assert second_db.execute("SELECT output_digest FROM history_runs").fetchone()[0] == first.output_digest
    second_db.close()
    assert before == {path: _sha256(path) for path in inputs}
    assert tree_digest(source) == source_before

    connection = sqlite3.connect(first_path)
    assert connection.execute("PRAGMA application_id").fetchone()[0] == HISTORY_APPLICATION_ID
    assert connection.execute(
        "SELECT observed_snapshot_count,metadata_change_count,current_observation_state "
        "FROM file_history_features WHERE relative_path='project/src/main.py'"
    ).fetchone() == (3, 2, "OBSERVED")
    assert connection.execute(
        "SELECT observed_snapshot_count,disappearance_count,current_observation_state "
        "FROM file_history_features WHERE relative_path='unicode/café.txt'"
    ).fetchone() == (1, 1, "NOT_OBSERVED")
    assert connection.execute(
        "SELECT first_observed_snapshot,appearance_count FROM file_history_features "
        "WHERE relative_path='project/src/new.py'"
    ).fetchone() == (2, 1)
    assert connection.execute(
        "SELECT longest_stable_transition_run,observation_ratio FROM file_history_features "
        "WHERE relative_path='media/final exports/render.wav'"
    ).fetchone() == (2, 1.0)
    assert connection.execute(
        "SELECT active_transition_count,current_observation_state FROM project_history_features "
        "WHERE project_id='project2'"
    ).fetchone() == (2, "OBSERVED")
    assert {row[0] for row in connection.execute(
        "SELECT stage_name FROM history_stages"
    )} == {"validate_chain", "file_history", "aggregate_history"}
    connection.close()


def test_history_rejects_discontinuous_or_noncanonical_chain(tmp_path: Path) -> None:
    _, _, manifest, _ = history_fixture(tmp_path)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["links"].reverse()
    manifest.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n",
    )
    with pytest.raises(ValueError, match="contiguous"):
        run_history_analysis(manifest, tmp_path / "reversed.db")

    second_root = tmp_path / "noncanonical"
    second_root.mkdir()
    _, _, second_manifest, _ = history_fixture(second_root)
    second_manifest.write_bytes(second_manifest.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(ValueError, match="canonical JSON"):
        run_history_analysis(second_manifest, second_root / "noncanonical.db")


def test_history_does_not_count_ambiguous_removal_as_disappearance(tmp_path: Path) -> None:
    _, _, manifest, _ = history_fixture(tmp_path, ambiguous_removal=True)
    output = tmp_path / "history.db"
    run_history_analysis(manifest, output)
    database = sqlite3.connect(output)
    assert database.execute(
        "SELECT disappearance_count,ambiguous_transition_count,current_observation_state "
        "FROM file_history_features WHERE relative_path='unicode/café.txt'"
    ).fetchone() == (0, 1, "NOT_OBSERVED")
    database.close()


def test_history_rejects_longitudinal_table_tampering(tmp_path: Path) -> None:
    _, _, manifest, links = history_fixture(tmp_path)
    database = sqlite3.connect(links[1])
    database.execute("UPDATE file_changes SET current_logical_bytes=current_logical_bytes+1 "
                     "WHERE current_logical_bytes IS NOT NULL")
    database.commit()
    database.close()
    with pytest.raises(ValueError, match="file_changes logical digest"):
        run_history_analysis(manifest, tmp_path / "tampered.db")
