from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from rootwise_analytics.pareto import Interval, pareto_ranks, robustly_dominates
from rootwise_analytics.pipeline import run_analysis
from rootwise_analytics.ranking_pipeline import RANKING_APPLICATION_ID, run_ranking

from .test_viewer_inventory import completed_inventory


def test_interval_dominance_keeps_overlaps_incomparable() -> None:
    better = (Interval("x", 0.0, 0.1, 0.2, 0.9), Interval("y", 0.0, 0.1, 0.2, 0.9))
    worse = (Interval("x", 0.3, 0.4, 0.5, 0.9), Interval("y", 0.3, 0.4, 0.5, 0.9))
    overlap = (Interval("x", 0.1, 0.2, 0.3, 0.5), Interval("y", 0.1, 0.2, 0.3, 0.5))
    assert robustly_dominates(better, worse)
    assert not robustly_dominates(better, overlap)
    assert pareto_ranks({"better": better, "worse": worse}) == {"better": 0, "worse": 1}


def test_ranking_is_deterministic_bounded_and_does_not_modify_analysis(tmp_path: Path) -> None:
    inventory, session = completed_inventory(tmp_path)
    analysis = tmp_path / "analysis.db"
    analysis_result = run_analysis(inventory, analysis, session_id=session)
    before = hashlib.sha256(analysis.read_bytes()).hexdigest()
    first = run_ranking(analysis, tmp_path / "rank-one.db", analysis_run_id=analysis_result.run_id,
        review_limit=5)
    second = run_ranking(analysis, tmp_path / "rank-two.db", analysis_run_id=analysis_result.run_id,
        review_limit=5)
    assert first.state == second.state == "COMPLETE"
    assert first.input_digest == second.input_digest
    assert first.output_digest == second.output_digest
    assert first.review_count <= 5
    assert hashlib.sha256(analysis.read_bytes()).hexdigest() == before
    connection = sqlite3.connect(tmp_path / "rank-one.db")
    assert connection.execute("PRAGMA application_id").fetchone()[0] == RANKING_APPLICATION_ID
    assert {row[0] for row in connection.execute("SELECT stage_name FROM ranking_stages")} == {
        "materialize", "objectives", "pareto", "review"
    }
    assert connection.execute("SELECT COUNT(*) FROM objective_intervals").fetchone()[0] == (
        first.candidate_count * 4
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM objective_intervals WHERE NOT (0<=confidence AND confidence<=1) "
        "OR NOT (low<=point AND point<=high)"
    ).fetchone()[0] == 0
    orders = [row[0] for row in connection.execute("SELECT review_order FROM review_queue ORDER BY review_order")]
    assert orders == list(range(1, len(orders) + 1))
    versions = connection.execute(
        "SELECT duckdb_version,polars_version,pyarrow_version FROM ranking_runs"
    ).fetchone()
    assert versions == ("1.5.5", "1.43.2", "25.0.0")
    connection.close()
