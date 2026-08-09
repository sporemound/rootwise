from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from paretodrive_analytics.pipeline import run_analysis
from paretodrive_enrich.pipeline import run_enrichment
from paretodrive_enrich.reader import ReadPolicy
from paretodrive_fusion.cli import main as fusion_main
from paretodrive_fusion.pipeline import FUSION_APPLICATION_ID, run_fusion

from .test_enrichment_pipeline import (
    enrichment_fixture,
    fake_resolver,
    manifest,
    tree_digest,
)


def fusion_inputs(
    tmp_path: Path, level: str, selected: list[str]
) -> tuple[Path, Path, Path, Path, str]:
    source, inventory, session = enrichment_fixture(tmp_path)
    analysis = tmp_path / "analysis.db"
    analysis_result = run_analysis(inventory, analysis, session_id=session)
    selection = tmp_path / "selection.json"
    evidence = tmp_path / "evidence.db"
    manifest(selection, inventory, session, level, selected)
    run_enrichment(
        inventory,
        source,
        selection,
        evidence,
        allow_content_read=True,
        read_policy=ReadPolicy(4096, 4096, 10**9),
        volume_resolver=fake_resolver(source),
    )
    return source, inventory, analysis, evidence, analysis_result.run_id


def test_d3_fusion_is_deterministic_confirmed_and_snapshot_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    selected = [
        "media/final exports/other.wav",
        "media/final exports/render-copy.wav",
        "media/final exports/render.wav",
    ]
    source, inventory, analysis, evidence, analysis_run = fusion_inputs(tmp_path, "D3", selected)
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (inventory, analysis, evidence)
    }
    source_before = tree_digest(source)
    first_path = tmp_path / "fusion-one.db"
    second_path = tmp_path / "fusion-two.db"
    first = run_fusion(analysis, evidence, first_path, analysis_run_id=analysis_run)
    status = fusion_main([
        "--analysis", str(analysis), "--evidence", str(evidence),
        "--fusion", str(second_path), "--analysis-run", analysis_run,
    ])
    assert status == 0 and '"state": "COMPLETE"' in capsys.readouterr().out
    second = sqlite3.connect(second_path)
    second_output = str(second.execute("SELECT output_digest FROM fusion_runs").fetchone()[0])
    second.close()
    assert first.output_digest == second_output
    assert first.evidence_level == "D3" and first.selected_count == 3
    assert before == {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (inventory, analysis, evidence)
    }
    assert tree_digest(source) == source_before
    connection = sqlite3.connect(first_path)
    assert connection.execute("PRAGMA application_id").fetchone()[0] == FUSION_APPLICATION_ID
    assert connection.execute(
        "SELECT evidence_status,member_count FROM imported_duplicate_groups"
    ).fetchone() == ("CONFIRMED", 2)
    root = connection.execute(
        "SELECT observed_file_count,selected_file_count,candidate_member_count,"
        "confirmed_member_count,evidence_coverage,confirmed_member_ratio_of_selected "
        "FROM directory_evidence_features WHERE relative_path=''"
    ).fetchone()
    assert root[:4] == (16, 3, 0, 2)
    assert root[4] == pytest.approx(3 / 16) and root[5] == pytest.approx(2 / 3)
    assert {row[0] for row in connection.execute("SELECT stage_name FROM fusion_stages")} == {
        "validate", "import", "directory_features"
    }
    connection.close()


def test_d2_fusion_never_promotes_candidate_evidence(tmp_path: Path) -> None:
    selected = [
        "media/final exports/render-copy.wav",
        "media/final exports/render.wav",
    ]
    _, _, analysis, evidence, _ = fusion_inputs(tmp_path, "D2", selected)
    fusion = tmp_path / "fusion.db"
    result = run_fusion(analysis, evidence, fusion)
    assert result.evidence_level == "D2"
    connection = sqlite3.connect(fusion)
    assert connection.execute(
        "SELECT evidence_status FROM imported_duplicate_groups"
    ).fetchone()[0] == "CANDIDATE"
    assert connection.execute(
        "SELECT candidate_member_count,confirmed_member_count "
        "FROM directory_evidence_features WHERE relative_path=''"
    ).fetchone() == (2, 0)
    connection.close()


def test_fusion_rejects_tampered_or_stopped_evidence(tmp_path: Path) -> None:
    selected = [
        "media/final exports/render-copy.wav",
        "media/final exports/render.wav",
    ]
    source, inventory, analysis, evidence, _ = fusion_inputs(tmp_path, "D4", selected)
    connection = sqlite3.connect(evidence)
    connection.execute(
        "UPDATE file_evidence SET digest=? WHERE relative_path=?", ("0" * 64, selected[0])
    )
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="duplicate group members|logical output"):
        run_fusion(analysis, evidence, tmp_path / "tampered-fusion.db")
    stopped_selection = tmp_path / "stopped-selection.json"
    stopped_evidence = tmp_path / "stopped-evidence.db"
    inventory_db = sqlite3.connect(inventory)
    session = str(inventory_db.execute(
        "SELECT scan_session_id FROM scan_sessions WHERE state='COMPLETE'"
    ).fetchone()[0])
    inventory_db.close()
    manifest(stopped_selection, inventory, session, "D4", selected)
    run_enrichment(
        inventory,
        source,
        stopped_selection,
        stopped_evidence,
        allow_content_read=True,
        read_policy=ReadPolicy(4096, 4096, 10**9),
        stop_after=1,
        volume_resolver=fake_resolver(source),
    )
    with pytest.raises(ValueError, match="COMPLETE enrichment"):
        run_fusion(analysis, stopped_evidence, tmp_path / "stopped-fusion.db")
