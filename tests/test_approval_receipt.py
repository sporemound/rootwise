from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from rootwise_analytics.optimizer_pipeline import run_optimization
from rootwise_analytics.pipeline import run_analysis
from rootwise_analytics.ranking_pipeline import run_ranking
from rootwise_approval.cli import main as approval_main
from rootwise_approval.declaration import ACKNOWLEDGEMENTS, INTENT, SCHEMA_VERSION
from rootwise_approval.receipt import export_approval_receipt
from rootwise_view.decisions import DecisionStore

from .test_viewer_inventory import completed_inventory


def completed_plan(tmp_path: Path) -> tuple[Path, str, str, str, str]:
    inventory, session = completed_inventory(tmp_path)
    analysis = tmp_path / "analysis.db"
    ranking = tmp_path / "ranking.db"
    decisions = tmp_path / "decisions.db"
    plans = tmp_path / "plans.db"
    analysis_result = run_analysis(inventory, analysis, session_id=session)
    run_ranking(analysis, ranking, analysis_run_id=analysis_result.run_id, review_limit=5)
    with DecisionStore(decisions, inventory_path=inventory) as store:
        store.set_decision(session, "project/src", "ARCHIVE_ELIGIBLE")
        store.set_decision(session, "originals", "PROTECT")
    result = run_optimization(
        ranking,
        decisions,
        plans,
        maximum_archive_bytes=10_000,
        destination_available_bytes=100_000,
        generations=2,
        max_frontier_states=200,
    )
    connection = sqlite3.connect(plans)
    row = connection.execute(
        "SELECT p.plan_id,r.output_digest,r.decisions_digest FROM proposed_plans p "
        "JOIN plan_runs r USING(run_id) WHERE p.run_id=? AND EXISTS ("
        "SELECT 1 FROM proposed_archives a WHERE a.run_id=p.run_id AND a.plan_id=p.plan_id) "
        "ORDER BY p.plan_id LIMIT 1",
        (result.run_id,),
    ).fetchone()
    connection.close()
    assert row is not None
    return plans, result.run_id, str(row[0]), str(row[1]), str(row[2])


def write_declaration(
    path: Path, run_id: str, plan_id: str, output_digest: str, decisions_digest: str
) -> None:
    path.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "plan_run_id": run_id,
        "plan_id": plan_id,
        "plan_output_digest": output_digest,
        "decisions_digest": decisions_digest,
        "intent": INTENT,
        "acknowledgements": list(ACKNOWLEDGEMENTS),
        "operator": "synthetic-test-operator",
        "approved_at": "2026-08-09T22:00:00Z",
        "note": "Synthetic approval fixture only.",
    }, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def test_approval_receipt_is_deterministic_non_executable_and_snapshot_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    plans, run_id, plan_id, output_digest, decisions_digest = completed_plan(tmp_path)
    declaration = tmp_path / "approval-declaration.json"
    write_declaration(declaration, run_id, plan_id, output_digest, decisions_digest)
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (plans, declaration)
    }
    first_path = tmp_path / "approval-one.json"
    second_path = tmp_path / "approval-two.json"
    first = export_approval_receipt(plans, declaration, first_path)
    status = approval_main([
        "--plans", str(plans), "--declaration", str(declaration),
        "--receipt", str(second_path),
    ])
    cli_result = json.loads(capsys.readouterr().out)
    assert status == 0
    assert first.receipt_digest == cli_result["receipt_digest"]
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first.archive_action_count > 0
    assert before == {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (plans, declaration)
    }
    receipt = json.loads(first_path.read_bytes())
    assert receipt["authorizations"] == {
        "execution_authorized": False,
        "archive_creation_authorized": False,
        "original_removal_authorized": False,
    }
    recorded_digest = receipt.pop("receipt_digest")
    canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == recorded_digest
    assert receipt["source"]["plan_id"] == plan_id
    assert receipt["limitations"][0].startswith("DIRECTORY_ACTIONS_ARE_NOT_")


def test_approval_revalidates_plan_and_rejects_tampering(tmp_path: Path) -> None:
    plans, run_id, plan_id, output_digest, decisions_digest = completed_plan(tmp_path)
    declaration = tmp_path / "approval-declaration.json"
    write_declaration(declaration, run_id, plan_id, output_digest, decisions_digest)
    connection = sqlite3.connect(plans)
    connection.execute(
        "UPDATE proposed_plans SET objectives_json=? WHERE run_id=? AND plan_id=?",
        (json.dumps([0, 0, 0, 0, 0, 0]), run_id, plan_id),
    )
    connection.commit()
    connection.close()
    receipt = tmp_path / "tampered-receipt.json"
    with pytest.raises(ValueError, match="objective values"):
        export_approval_receipt(plans, declaration, receipt)
    assert not receipt.exists()


def test_declaration_and_candidate_bounds_fail_closed(tmp_path: Path) -> None:
    plans, run_id, plan_id, output_digest, decisions_digest = completed_plan(tmp_path)
    declaration = tmp_path / "approval-declaration.json"
    write_declaration(declaration, run_id, plan_id, output_digest, decisions_digest)
    with pytest.raises(ValueError, match="candidate count"):
        export_approval_receipt(
            plans, declaration, tmp_path / "bounded.json", maximum_candidates=1
        )
    value = json.loads(declaration.read_bytes())
    value["acknowledgements"].reverse()
    declaration.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="acknowledgements"):
        export_approval_receipt(plans, declaration, tmp_path / "invalid.json")
