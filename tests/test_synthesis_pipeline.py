from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from paretodrive_analytics.pipeline import run_analysis
from paretodrive_analytics.ranking_pipeline import run_ranking
from paretodrive_dependency.pipeline import run_dependency_analysis
from paretodrive_enrich.pipeline import run_enrichment
from paretodrive_enrich.reader import ReadPolicy
from paretodrive_fusion.pipeline import run_fusion
from paretodrive_history.pipeline import run_history_analysis
from paretodrive_longitudinal.pipeline import run_longitudinal
from paretodrive_synthesis.cli import main as synthesis_main
from paretodrive_synthesis.pipeline import SYNTHESIS_APPLICATION_ID, run_synthesis

from .test_enrichment_pipeline import (
    enrichment_fixture,
    fake_resolver,
    manifest as enrichment_manifest,
    tree_digest,
)
from .test_longitudinal_pipeline import scan


def synthesis_fixture(tmp_path: Path) -> tuple[Path, list[Path]]:
    source, inventory, session_zero = enrichment_fixture(tmp_path)
    analysis_zero = tmp_path / "analysis-00.db"
    run_zero = run_analysis(inventory, analysis_zero, session_id=session_zero).run_id

    (source / "project" / "src" / "main.py").write_text(
        "print('snapshot one changed')\n", encoding="utf-8"
    )
    session_one = scan(source, inventory, tmp_path)
    analysis_one = tmp_path / "analysis-01.db"
    run_one = run_analysis(inventory, analysis_one, session_id=session_one).run_id

    second = source / "project2"
    (second / "src").mkdir(parents=True)
    (second / "pyproject.toml").write_text("[project]\nname='two'\n", encoding="utf-8")
    (second / "src" / "app.py").write_text("print('two')\n", encoding="utf-8")
    (source / "project" / "src" / "main.py").write_text(
        "print('snapshot two changed with another distinct size')\n", encoding="utf-8"
    )
    session_two = scan(source, inventory, tmp_path)
    analysis_two = tmp_path / "analysis-02.db"
    run_two = run_analysis(inventory, analysis_two, session_id=session_two).run_id

    ranking = tmp_path / "ranking.db"
    run_ranking(analysis_two, ranking, analysis_run_id=run_two, review_limit=10)
    selection = tmp_path / "selection.json"
    evidence = tmp_path / "evidence.db"
    enrichment_manifest(selection, inventory, session_two, "D3", [
        "media/final exports/other.wav",
        "media/final exports/render-copy.wav",
        "media/final exports/render.wav",
    ])
    run_enrichment(
        inventory, source, selection, evidence, allow_content_read=True,
        read_policy=ReadPolicy(4096, 4096, 10**9), volume_resolver=fake_resolver(source),
    )
    fusion = tmp_path / "fusion.db"
    run_fusion(analysis_two, evidence, fusion, analysis_run_id=run_two)

    first_link = tmp_path / "transition-01.db"
    first = run_longitudinal(
        analysis_zero, analysis_one, first_link,
        baseline_analysis_run_id=run_zero, current_analysis_run_id=run_one,
        shared_extension_threshold=0.2,
    )
    second_link = tmp_path / "transition-02.db"
    second_result = run_longitudinal(
        analysis_one, analysis_two, second_link,
        baseline_analysis_run_id=run_one, current_analysis_run_id=run_two,
        shared_extension_threshold=0.2,
    )
    chain = tmp_path / "history-chain.json"
    chain.write_text(json.dumps({
        "schema": "paretodrive-longitudinal-chain-v1",
        "created_at": "2026-08-09T00:00:00Z", "label": "synthesis-fixture",
        "links": [
            {"database": first_link.name, "run_id": first.run_id,
             "output_digest": first.output_digest},
            {"database": second_link.name, "run_id": second_result.run_id,
             "output_digest": second_result.output_digest},
        ],
    }, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    history = tmp_path / "history.db"
    run_history_analysis(chain, history)

    link_db = sqlite3.connect(second_link)
    projects = sorted(str(row[0]) for row in link_db.execute(
        "SELECT project_id FROM project_nodes WHERE temporal_state!='REMOVED' ORDER BY project_id"
    ))
    link_db.close()
    dependency_manifest = tmp_path / "dependency-evidence.json"
    relationships = [] if len(projects) < 2 else [{
        "evidence_id": "edge-001", "source_project": projects[1],
        "target_project": projects[0], "relationship_type": "DEPENDS_ON",
        "confidence": 0.9, "evidence_reference": "explicit synthetic declaration",
    }]
    dependency_manifest.write_text(json.dumps({
        "schema": "paretodrive-project-dependency-evidence-v1",
        "longitudinal_run_id": second_result.run_id,
        "longitudinal_output_digest": second_result.output_digest,
        "producer": "synthesis-fixture", "created_at": "2026-08-09T00:00:00Z",
        "evaluated_projects": projects, "relationships": relationships,
    }, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    dependency = tmp_path / "dependency.db"
    run_dependency_analysis(second_link, dependency_manifest, dependency)
    return source, [inventory, ranking, fusion, dependency, history]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_synthesis_is_deterministic_lineage_safe_and_dimension_separated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, inputs = synthesis_fixture(tmp_path)
    before = {path: _sha256(path) for path in inputs}
    source_before = tree_digest(source)
    first_path = tmp_path / "synthesis-one.db"
    second_path = tmp_path / "synthesis-two.db"
    first = run_synthesis(inputs[1], inputs[2], inputs[3], inputs[4], first_path)
    status = synthesis_main([
        "--ranking", str(inputs[1]), "--fusion", str(inputs[2]),
        "--dependency", str(inputs[3]), "--history", str(inputs[4]),
        "--output", str(second_path),
    ])
    assert status == 0 and json.loads(capsys.readouterr().out)["state"] == "COMPLETE"
    second_db = sqlite3.connect(second_path)
    assert second_db.execute("SELECT output_digest FROM synthesis_runs").fetchone()[0] == first.output_digest
    second_db.close()
    assert before == {path: _sha256(path) for path in inputs}
    assert tree_digest(source) == source_before

    database = sqlite3.connect(first_path)
    assert database.execute("PRAGMA application_id").fetchone()[0] == SYNTHESIS_APPLICATION_ID
    assert database.execute(
        "SELECT COUNT(*) FROM candidate_evidence"
    ).fetchone()[0] == first.candidate_count
    media = database.execute(
        "SELECT confirmed_duplicate_member_count,enrichment_coverage "
        "FROM candidate_evidence WHERE relative_path='media/final exports'"
    ).fetchone()
    assert media[0] == 2 and media[1] == pytest.approx(1.0)
    assert database.execute(
        "SELECT COUNT(*) FROM review_signals WHERE signal_type='CONFIRMED_DUPLICATE_MEMBERS'"
    ).fetchone()[0] >= 1
    assert database.execute(
        "SELECT COUNT(*) FROM review_signals WHERE signal_type='HISTORY_CHURN_OBSERVED'"
    ).fetchone()[0] >= 1
    assert {row[0] for row in database.execute(
        "SELECT stage_name FROM synthesis_stages"
    )} == {"validate", "join_evidence", "review_signals"}
    columns = {str(row[1]) for row in database.execute("PRAGMA table_info(candidate_evidence)")}
    assert "priority" not in columns and "score" not in columns and "pareto_rank" not in columns
    database.close()

    fusion_db = sqlite3.connect(inputs[2])
    fusion_db.execute("UPDATE fusion_runs SET analysis_run_id='wrong-lineage'")
    fusion_db.commit()
    fusion_db.close()
    with pytest.raises(ValueError, match="analysis lineage mismatch"):
        run_synthesis(inputs[1], inputs[2], inputs[3], inputs[4], tmp_path / "wrong-lineage.db")


def test_synthesis_rejects_tampered_evidence_table(tmp_path: Path) -> None:
    _, inputs = synthesis_fixture(tmp_path)
    dependency_db = sqlite3.connect(inputs[3])
    dependency_db.execute("UPDATE dependency_graph_features SET dependency_in_degree=99")
    dependency_db.commit()
    dependency_db.close()
    with pytest.raises(ValueError, match="dependency logical output digest"):
        run_synthesis(inputs[1], inputs[2], inputs[3], inputs[4], tmp_path / "tampered.db")
