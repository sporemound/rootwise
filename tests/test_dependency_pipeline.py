from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from paretodrive_dependency.cli import main as dependency_main
from paretodrive_dependency.pipeline import DEPENDENCY_APPLICATION_ID, run_dependency_analysis
from paretodrive_longitudinal.pipeline import run_longitudinal

from .test_longitudinal_pipeline import repeated_snapshots, tree_digest


def dependency_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source, inventory, baseline, current, baseline_run, current_run = repeated_snapshots(tmp_path)
    longitudinal = tmp_path / "longitudinal.db"
    result = run_longitudinal(
        baseline, current, longitudinal,
        baseline_analysis_run_id=baseline_run,
        current_analysis_run_id=current_run,
        shared_extension_threshold=0.2,
    )
    manifest = tmp_path / "dependency-evidence.json"
    manifest.write_text(json.dumps({
        "schema": "paretodrive-project-dependency-evidence-v1",
        "longitudinal_run_id": result.run_id,
        "longitudinal_output_digest": result.output_digest,
        "producer": "synthetic-test-fixture",
        "created_at": "2026-08-09T00:00:00Z",
        "evaluated_projects": ["project", "project2"],
        "relationships": [{
            "evidence_id": "edge-001",
            "source_project": "project2",
            "target_project": "project",
            "relationship_type": "DEPENDS_ON",
            "confidence": 0.9,
            "evidence_reference": "explicit synthetic declaration",
        }],
    }, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    return source, inventory, longitudinal, manifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dependency_graph_is_deterministic_explicit_and_snapshot_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, inventory, longitudinal, manifest = dependency_fixture(tmp_path)
    before = {_path: _sha256(_path) for _path in (inventory, longitudinal, manifest)}
    source_before = tree_digest(source)
    first_path = tmp_path / "dependency-one.db"
    second_path = tmp_path / "dependency-two.db"
    first = run_dependency_analysis(longitudinal, manifest, first_path)
    status = dependency_main([
        "--longitudinal", str(longitudinal), "--evidence-manifest", str(manifest),
        "--output", str(second_path),
    ])
    assert status == 0
    assert json.loads(capsys.readouterr().out)["state"] == "COMPLETE"
    second = sqlite3.connect(second_path)
    assert second.execute("SELECT output_digest FROM dependency_runs").fetchone()[0] == first.output_digest
    second.close()
    assert before == {_path: _sha256(_path) for _path in (inventory, longitudinal, manifest)}
    assert tree_digest(source) == source_before

    connection = sqlite3.connect(first_path)
    assert connection.execute("PRAGMA application_id").fetchone()[0] == DEPENDENCY_APPLICATION_ID
    assert connection.execute(
        "SELECT relationship_type,directed,confidence FROM dependency_edges"
    ).fetchone() == ("DEPENDS_ON", 1, 0.9)
    assert connection.execute(
        "SELECT dependency_out_degree,evidence_state FROM dependency_graph_features "
        "WHERE project_id='project2'"
    ).fetchone() == (1, "EVALUATED")
    assert connection.execute(
        "SELECT dependency_in_degree FROM dependency_graph_features WHERE project_id='project'"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT dependency_evidence_coverage FROM dependency_runs"
    ).fetchone()[0] == 1.0
    assert {row[0] for row in connection.execute(
        "SELECT stage_name FROM dependency_stages"
    )} == {"validate", "import_evidence", "graph_features"}
    connection.close()


def test_dependency_manifest_marks_unevaluated_as_unknown(tmp_path: Path) -> None:
    _, _, longitudinal, manifest = dependency_fixture(tmp_path)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["evaluated_projects"] = ["project"]
    value["relationships"] = []
    manifest.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n"
    )
    output = tmp_path / "dependency.db"
    run_dependency_analysis(longitudinal, manifest, output)
    connection = sqlite3.connect(output)
    assert connection.execute(
        "SELECT evidence_state FROM dependency_graph_features WHERE project_id='project2'"
    ).fetchone()[0] == "NOT_EVALUATED"
    assert connection.execute(
        "SELECT dependency_evidence_coverage FROM dependency_runs"
    ).fetchone()[0] == 0.5
    connection.close()


def test_dependency_manifest_rejects_noncanonical_windows_newlines(tmp_path: Path) -> None:
    _, _, longitudinal, manifest = dependency_fixture(tmp_path)
    manifest.write_bytes(manifest.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(ValueError, match="canonical JSON"):
        run_dependency_analysis(longitudinal, manifest, tmp_path / "noncanonical.db")


def test_dependency_manifest_rejects_unknown_edges_and_tampering(tmp_path: Path) -> None:
    _, _, longitudinal, manifest = dependency_fixture(tmp_path)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["relationships"][0]["target_project"] = "missing-project"
    manifest.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n"
    )
    with pytest.raises(ValueError, match="endpoints"):
        run_dependency_analysis(longitudinal, manifest, tmp_path / "invalid.db")

    second_root = tmp_path / "second"
    second_root.mkdir()
    _, _, second_longitudinal, second_manifest = dependency_fixture(second_root)
    database = sqlite3.connect(second_longitudinal)
    database.execute("UPDATE project_nodes SET current_file_count=current_file_count+1")
    database.commit()
    database.close()
    with pytest.raises(ValueError, match="project_graph logical digest"):
        run_dependency_analysis(second_longitudinal, second_manifest, tmp_path / "second" / "tampered.db")
