"""Query-only proposal validation and canonical non-executable approval receipt export."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rootwise_analytics.optimizer_pipeline import PLAN_APPLICATION_ID
from rootwise_analytics.plan_models import Action, Candidate, PlanMetrics, PlanPolicy
from rootwise_analytics.plan_validation import validate_plan

from .declaration import ACKNOWLEDGEMENTS, INTENT, ApprovalDeclaration, load_declaration

RECEIPT_SCHEMA_VERSION = "rootwise-plan-approval-receipt-1"
CODE_VERSION = "0.8.0-alpha"
OBJECTIVE_NAMES = (
    "negative_recoverable_bytes", "remaining_loose_files", "preservation_risk",
    "peak_temporary_bytes", "archive_count", "archive_incoherence",
)


@dataclass(frozen=True)
class ApprovalResult:
    receipt_digest: str
    plan_run_id: str
    plan_id: str
    candidate_count: int
    archive_action_count: int
    state: str = "PLAN_SELECTED_FOR_FUTURE_EXECUTOR_REVIEW"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _logical_digest(rows: list[tuple[object, ...]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(_canonical(row) + b"\n")
    return digest.hexdigest()


def _json_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ValueError(f"{label} is not JSON text")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return dict(parsed)


def _metrics(value: object) -> PlanMetrics:
    if not isinstance(value, str):
        raise ValueError("plan objectives are not JSON text")
    parsed = json.loads(value)
    if not isinstance(parsed, list) or len(parsed) != len(OBJECTIVE_NAMES) or any(
        not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(item)
        for item in parsed
    ):
        raise ValueError("plan objectives must contain six finite numbers")
    return PlanMetrics(*(float(item) for item in parsed))


def _action(value: object) -> Action:
    if not isinstance(value, str):
        raise ValueError("plan action must be a named action")
    try:
        return Action[value]
    except KeyError as exc:
        raise ValueError(f"unsupported plan action: {value}") from exc


def _validate_stages(connection: sqlite3.Connection, run_id: str) -> list[tuple[object, ...]]:
    rows = [tuple(row) for row in connection.execute(
        "SELECT stage_name,state,input_digest,config_digest,output_digest,code_version,error "
        "FROM plan_stages WHERE run_id=? ORDER BY stage_name", (run_id,),
    )]
    states = {str(row[0]): str(row[1]) for row in rows}
    if set(states) != {"candidates", "exact", "nsga3", "rnsga3", "validate", "present"}:
        raise ValueError("plan prerequisite stages are incomplete or mismatched")
    if any(states[name] != "COMPLETE" for name in states if name != "exact") or states[
        "exact"
    ] not in {"COMPLETE", "SKIPPED_LIMIT"}:
        raise ValueError("plan prerequisite stage state is not consumable")
    return rows


def _load_candidates(
    connection: sqlite3.Connection, run_id: str, maximum_candidates: int
) -> tuple[list[Candidate], list[tuple[object, ...]]]:
    rows = [tuple(row) for row in connection.execute(
        "SELECT candidate_id,relative_path,parent_id,recursive_bytes,file_count,eligible,protected,"
        "preservation_risk,incoherence FROM candidate_groups WHERE run_id=? ORDER BY candidate_id",
        (run_id,),
    )]
    if not 1 <= len(rows) <= maximum_candidates:
        raise ValueError("plan candidate count is outside the configured approval bound")
    candidates: list[Candidate] = []
    for row in rows:
        if row[5] not in {0, 1} or row[6] not in {0, 1}:
            raise ValueError("plan candidate booleans are invalid")
        risk, incoherence = float(row[7]), float(row[8])
        if not math.isfinite(risk) or not math.isfinite(incoherence):
            raise ValueError("plan candidate objectives must be finite")
        candidates.append(Candidate(
            str(row[0]), str(row[1]), None if row[2] is None else str(row[2]),
            int(row[3]), int(row[4]), bool(row[5]), bool(row[6]), risk, incoherence,
        ))
    return candidates, rows


def _build_receipt(
    plans: Path,
    declaration: ApprovalDeclaration,
    run: tuple[object, ...],
    stages: list[tuple[object, ...]],
    candidate_rows: list[tuple[object, ...]],
    candidates: list[Candidate],
    plan_row: tuple[object, ...],
    action_rows: list[tuple[object, ...]],
    archive_rows: list[tuple[object, ...]],
    configuration: dict[str, Any],
    metrics: PlanMetrics,
) -> dict[str, object]:
    actions_by_id = {str(row[0]): _action(row[1]) for row in action_rows}
    policy = PlanPolicy(
        int(configuration["maximum_archive_bytes"]),
        int(configuration["destination_available_bytes"]),
        float(configuration["destination_safety_margin"]),
    )
    validated = validate_plan(candidates, policy, actions_by_id, expected_metrics=metrics)
    if validated.plan_id != declaration.plan_id or str(plan_row[0]) != validated.plan_id:
        raise ValueError("selected plan ID does not match independent recomputation")
    expected_archives = tuple((candidate_id, name) for candidate_id, name in validated.archive_names)
    actual_archives = tuple((str(row[0]), str(row[1])) for row in archive_rows)
    if actual_archives != expected_archives:
        raise ValueError("proposed archive labels do not match independent recomputation")
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    archive_names = dict(actual_archives)
    selected_actions = [{
        "candidate_id": candidate_id,
        "relative_path": by_id[candidate_id].relative_path,
        "action": action.name,
        "recursive_bytes": by_id[candidate_id].recursive_bytes,
        "file_count": by_id[candidate_id].file_count,
        "proposed_archive_label": archive_names.get(candidate_id),
    } for candidate_id, action in validated.actions]
    source_digest = _logical_digest([
        tuple(run), *stages, *candidate_rows, tuple(plan_row), *action_rows, *archive_rows,
    ])
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "code_version": CODE_VERSION,
        "state": "PLAN_SELECTED_FOR_FUTURE_EXECUTOR_REVIEW",
        "authorizations": {
            "execution_authorized": False,
            "archive_creation_authorized": False,
            "original_removal_authorized": False,
        },
        "approval": {
            "declaration_digest": declaration.declaration_digest,
            "intent": INTENT,
            "acknowledgements": list(ACKNOWLEDGEMENTS),
            "operator": declaration.operator,
            "approved_at": declaration.approved_at,
            "note": declaration.note,
        },
        "source": {
            "plans_filename": plans.name,
            "plan_database_application_id": PLAN_APPLICATION_ID,
            "plan_database_logical_digest": source_digest,
            "plan_run_id": declaration.plan_run_id,
            "plan_id": declaration.plan_id,
            "plan_output_digest": declaration.plan_output_digest,
            "input_digest": str(run[5]),
            "decisions_digest": declaration.decisions_digest,
            "scan_session_id": str(run[4]),
        },
        "plan": {
            "configuration": configuration,
            "objectives": dict(zip(OBJECTIVE_NAMES, metrics.values(), strict=True)),
            "actions": selected_actions,
        },
        "limitations": [
            "DIRECTORY_ACTIONS_ARE_NOT_AN_ENUMERATED_ARCHIVE_MEMBER_MANIFEST",
            "SOURCE_OBSERVATIONS_MUST_BE_REVALIDATED_BY_A_FUTURE_SEPARATE_COMPONENT",
            "PROPOSED_ARCHIVE_NAMES_ARE_LABELS_ONLY",
        ],
    }


def export_approval_receipt(
    plans_path: str | Path,
    declaration_path: str | Path,
    receipt_path: str | Path,
    *,
    maximum_candidates: int = 10_000,
) -> ApprovalResult:
    if maximum_candidates < 1:
        raise ValueError("maximum candidate bound must be positive")
    plans = Path(plans_path).expanduser().resolve(strict=True)
    declaration_file = Path(declaration_path).expanduser().resolve(strict=True)
    destination = Path(receipt_path).expanduser().resolve(strict=False)
    if len({plans, declaration_file, destination}) != 3:
        raise ValueError("plans, declaration, and receipt paths must be distinct")
    if declaration_file.parent != plans.parent or destination.parent != plans.parent:
        raise ValueError("declaration and new receipt must be siblings of the plans database")
    if destination.exists():
        raise ValueError("approval receipt must be a new file")
    declaration = load_declaration(declaration_file)
    connection = sqlite3.connect(plans.as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    try:
        if connection.execute("PRAGMA application_id").fetchone()[0] != PLAN_APPLICATION_ID:
            raise ValueError("plans database application identity mismatch")
        raw_run = connection.execute(
            "SELECT run_id,ranking_path,ranking_run_id,decisions_path,scan_session_id,input_digest,"
            "decisions_digest,output_digest,state,configuration_json,dependencies_json "
            "FROM plan_runs WHERE run_id=?", (declaration.plan_run_id,),
        ).fetchone()
        if raw_run is None:
            raise ValueError("declared plan run does not exist")
        run = tuple(raw_run)
        if run[8] != "COMPLETE" or run[7] is None:
            raise ValueError("approval requires a COMPLETE plan run")
        if run[7] != declaration.plan_output_digest or run[6] != declaration.decisions_digest:
            raise ValueError("approval declaration digests do not match the plan run")
        stages = _validate_stages(connection, declaration.plan_run_id)
        candidates, candidate_rows = _load_candidates(
            connection, declaration.plan_run_id, maximum_candidates
        )
        raw_plan = connection.execute(
            "SELECT plan_id,sources_json,labels_json,objectives_json,validated,approval_state "
            "FROM proposed_plans WHERE run_id=? AND plan_id=?",
            (declaration.plan_run_id, declaration.plan_id),
        ).fetchone()
        if raw_plan is None or raw_plan[4] != 1 or raw_plan[5] != "UNAPPROVED":
            raise ValueError("approval requires one validated UNAPPROVED proposal")
        plan_row = tuple(raw_plan)
        action_rows = [tuple(row) for row in connection.execute(
            "SELECT candidate_id,action FROM plan_actions WHERE run_id=? AND plan_id=? "
            "ORDER BY candidate_id", (declaration.plan_run_id, declaration.plan_id),
        )]
        archive_rows = [tuple(row) for row in connection.execute(
            "SELECT candidate_id,proposed_name FROM proposed_archives WHERE run_id=? AND plan_id=? "
            "ORDER BY candidate_id", (declaration.plan_run_id, declaration.plan_id),
        )]
        configuration = _json_object(run[9], "plan configuration")
        required_policy = {
            "maximum_archive_bytes", "destination_available_bytes", "destination_safety_margin"
        }
        if not required_policy <= set(configuration):
            raise ValueError("plan configuration lacks capacity policy")
        metrics = _metrics(plan_row[3])
        receipt = _build_receipt(
            plans, declaration, run, stages, candidate_rows, candidates, plan_row,
            action_rows, archive_rows, configuration, metrics,
        )
    finally:
        connection.close()
    receipt_digest = hashlib.sha256(_canonical(receipt)).hexdigest()
    receipt["receipt_digest"] = receipt_digest
    with destination.open("xb") as stream:
        stream.write(_canonical(receipt) + b"\n")
    return ApprovalResult(
        receipt_digest,
        declaration.plan_run_id,
        declaration.plan_id,
        len(candidates),
        sum(action.name == "ARCHIVE_AS_UNIT" for action in (
            _action(row[1]) for row in action_rows
        )),
    )
