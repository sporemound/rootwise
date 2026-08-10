from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from rootwise_analytics.optimizer_pipeline import PLAN_APPLICATION_ID, run_optimization
from rootwise_analytics.pipeline import run_analysis
from rootwise_analytics.ranking_pipeline import run_ranking
from rootwise.viewer.decisions import DecisionStore

from .test_viewer_inventory import completed_inventory


def test_proposal_pipeline_is_validated_deterministic_and_snapshot_only(tmp_path: Path) -> None:
    inventory, session = completed_inventory(tmp_path)
    analysis = tmp_path / "analysis.db"
    ranking = tmp_path / "ranking.db"
    decisions = tmp_path / "decisions.db"
    analysis_result = run_analysis(inventory, analysis, session_id=session)
    run_ranking(analysis, ranking, analysis_run_id=analysis_result.run_id, review_limit=5)
    with DecisionStore(decisions, inventory_path=inventory) as store:
        store.set_decision(session, "project/src", "ARCHIVE_ELIGIBLE")
        store.set_decision(session, "originals", "PROTECT")
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (analysis, ranking, decisions)}
    first = run_optimization(
        ranking, decisions, tmp_path / "plans-one.db",
        maximum_archive_bytes=10_000, destination_available_bytes=100_000,
        generations=3, max_frontier_states=200,
    )
    second = run_optimization(
        ranking, decisions, tmp_path / "plans-two.db",
        maximum_archive_bytes=10_000, destination_available_bytes=100_000,
        generations=3, max_frontier_states=200,
    )
    assert first.state == second.state == "COMPLETE"
    assert first.output_digest == second.output_digest
    assert first.validated_plan_count <= 12
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (analysis, ranking, decisions)}
    connection = sqlite3.connect(tmp_path / "plans-one.db")
    assert connection.execute("PRAGMA application_id").fetchone()[0] == PLAN_APPLICATION_ID
    assert {row[0] for row in connection.execute("SELECT stage_name FROM plan_stages")} == {
        "candidates", "exact", "nsga3", "rnsga3", "validate", "present"
    }
    assert connection.execute(
        "SELECT COUNT(*) FROM proposed_plans WHERE validated!=1 OR approval_state!='UNAPPROVED'"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM plan_actions WHERE action='ARCHIVE_AS_UNIT'"
    ).fetchone()[0] > 0
    versions = json_load(connection.execute(
        "SELECT dependencies_json FROM plan_runs"
    ).fetchone()[0])
    assert versions == {"numpy": "2.4.6", "pymoo": "0.6.2", "scipy": "1.17.1"}
    connection.close()
    limited = run_optimization(
        ranking, decisions, tmp_path / "plans-limited.db",
        maximum_archive_bytes=10_000, destination_available_bytes=100_000,
        generations=2, max_frontier_states=1,
    )
    assert limited.state == "COMPLETE"
    connection = sqlite3.connect(tmp_path / "plans-limited.db")
    assert connection.execute(
        "SELECT state FROM plan_stages WHERE stage_name='exact'"
    ).fetchone()[0] == "SKIPPED_LIMIT"
    assert connection.execute("SELECT COUNT(*) FROM proposed_plans").fetchone()[0] > 0
    connection.close()


def json_load(value: str) -> dict[str, str]:
    import json
    return dict(json.loads(value))
