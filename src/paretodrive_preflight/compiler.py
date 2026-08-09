"""Compile bounded archive-member observations without opening source filesystem paths."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paretodrive_analytics.optimizer_pipeline import PLAN_APPLICATION_ID
from paretodrive_analytics.pipeline import ANALYSIS_APPLICATION_ID
from paretodrive_analytics.ranking_pipeline import RANKING_APPLICATION_ID
from paretodrive_analytics.snapshot import INVENTORY_APPLICATION_ID

from .receipt_snapshot import ReceiptSnapshot, load_receipt

SCHEMA_VERSION = "paretodrive-executor-preflight-manifest-1"
CODE_VERSION = "0.9.0-alpha"


@dataclass(frozen=True)
class PreflightResult:
    manifest_digest: str
    archive_count: int
    member_count: int
    logical_bytes: int
    state: str = "PREFLIGHT_ONLY_NON_EXECUTABLE"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _open_database(path: Path, application_id: int, label: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        if connection.execute("PRAGMA application_id").fetchone()[0] != application_id:
            raise ValueError(f"{label} database application identity mismatch")
    except BaseException:
        connection.close()
        raise
    return connection


def _recorded_sibling(raw: object, parent: Path, label: str) -> Path:
    if not isinstance(raw, str):
        raise ValueError(f"recorded {label} path is invalid")
    path = Path(raw).expanduser().resolve(strict=True)
    if path.parent != parent:
        raise ValueError(f"recorded {label} path escaped the external database directory")
    return path


def _inventory_digest(connection: sqlite3.Connection, session_id: str) -> str:
    digest = hashlib.sha256()
    names = ("kind", "relative_path", "parent_path", "name", "extension", "logical_bytes", "depth")
    rows = connection.execute(
        "SELECT kind,relative_path,parent_path,name,extension,logical_bytes,depth FROM ("
        "SELECT 'directory' kind,relative_path,parent_path,name,'' extension,logical_bytes,depth "
        "FROM directories WHERE scan_session_id=? UNION ALL "
        "SELECT 'file' kind,relative_path,parent_path,name,extension,logical_bytes,depth "
        "FROM files WHERE scan_session_id=?) ORDER BY relative_path COLLATE BINARY,kind",
        (session_id, session_id),
    )
    for row in rows:
        payload = json.dumps(dict(zip(names, row, strict=True)), sort_keys=True, separators=(",", ":"))
        digest.update(payload.encode("utf-8") + b"\n")
    return digest.hexdigest()


def _under(path: str, root: str) -> bool:
    return root == "" or path == root or path.startswith(root + "/")


def _archive_actions(receipt: ReceiptSnapshot) -> list[dict[str, Any]]:
    required = {
        "candidate_id", "relative_path", "action", "recursive_bytes", "file_count",
        "proposed_archive_label",
    }
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for action in receipt.actions:
        if set(action) != required:
            raise ValueError("approval receipt action fields are invalid")
        candidate_id = action["candidate_id"]
        relative_path = action["relative_path"]
        if not isinstance(candidate_id, str) or not isinstance(relative_path, str):
            raise ValueError("approval receipt action identity is invalid")
        if candidate_id in seen:
            raise ValueError("approval receipt candidate IDs are not unique")
        seen.add(candidate_id)
        if action["action"] == "ARCHIVE_AS_UNIT":
            if not relative_path or action["proposed_archive_label"] is None:
                raise ValueError("archive action lacks a path or proposed label")
            actions.append(action)
    if not actions:
        raise ValueError("selected plan contains no archive actions")
    roots = sorted(str(action["relative_path"]) for action in actions)
    if any(_under(right, left) for index, left in enumerate(roots) for right in roots[index + 1:]):
        raise ValueError("selected archive roots overlap")
    return sorted(actions, key=lambda action: str(action["relative_path"]))


def _verify_plan(
    connection: sqlite3.Connection, receipt: ReceiptSnapshot, archives: list[dict[str, Any]]
) -> tuple[Path, str]:
    row = connection.execute(
        "SELECT ranking_path,ranking_run_id,scan_session_id,input_digest,decisions_digest,"
        "output_digest,state FROM plan_runs WHERE run_id=?", (receipt.plan_run_id,),
    ).fetchone()
    if row is None or row[6] != "COMPLETE":
        raise ValueError("preflight requires the declared COMPLETE plan run")
    if (str(row[2]), str(row[3]), str(row[4]), str(row[5])) != (
        receipt.scan_session_id, receipt.plan_input_digest, receipt.decisions_digest,
        receipt.plan_output_digest,
    ):
        raise ValueError("approval receipt does not match the plan run")
    database_actions = [tuple(item) for item in connection.execute(
        "SELECT a.candidate_id,c.relative_path,a.action,c.recursive_bytes,c.file_count,"
        "p.proposed_name FROM plan_actions a JOIN candidate_groups c USING(run_id,candidate_id) "
        "LEFT JOIN proposed_archives p USING(run_id,plan_id,candidate_id) "
        "WHERE a.run_id=? AND a.plan_id=? ORDER BY a.candidate_id",
        (receipt.plan_run_id, receipt.plan_id),
    )]
    receipt_actions = sorted((
        str(action["candidate_id"]), str(action["relative_path"]), str(action["action"]),
        int(action["recursive_bytes"]), int(action["file_count"]),
        action["proposed_archive_label"],
    ) for action in receipt.actions)
    if database_actions != receipt_actions:
        raise ValueError("approval receipt actions no longer match the plans database")
    if {str(action["candidate_id"]) for action in archives} != {
        str(row[0]) for row in database_actions if row[2] == "ARCHIVE_AS_UNIT"
    }:
        raise ValueError("approval receipt archive selection is inconsistent")
    return Path(str(row[0])), str(row[1])


def _trace_inventory(
    parent: Path,
    ranking_path: Path,
    ranking_run_id: str,
    receipt: ReceiptSnapshot,
    explicit_inventory: Path,
) -> tuple[sqlite3.Connection, str, str]:
    ranking = _recorded_sibling(str(ranking_path), parent, "ranking")
    ranking_db = _open_database(ranking, RANKING_APPLICATION_ID, "ranking")
    try:
        ranking_run = ranking_db.execute(
            "SELECT analysis_path,analysis_run_id,input_digest,output_digest,state "
            "FROM ranking_runs WHERE run_id=?", (ranking_run_id,),
        ).fetchone()
        if ranking_run is None or ranking_run[4] != "COMPLETE" or ranking_run[3] is None:
            raise ValueError("recorded ranking run is not COMPLETE")
        if _digest([str(ranking_run[2]), str(ranking_run[3]), receipt.decisions_digest]) != (
            receipt.plan_input_digest
        ):
            raise ValueError("ranking provenance does not match the plan input digest")
        analysis = _recorded_sibling(ranking_run[0], parent, "analysis")
        analysis_run_id = str(ranking_run[1])
    finally:
        ranking_db.close()
    analysis_db = _open_database(analysis, ANALYSIS_APPLICATION_ID, "analysis")
    try:
        analysis_run = analysis_db.execute(
            "SELECT inventory_path,scan_session_id,input_digest,output_digest,state "
            "FROM analysis_runs WHERE run_id=?", (analysis_run_id,),
        ).fetchone()
        if analysis_run is None or analysis_run[4] != "COMPLETE" or analysis_run[3] is None:
            raise ValueError("recorded analysis run is not COMPLETE")
        if _digest([str(analysis_run[2]), str(analysis_run[3])]) != str(ranking_run[2]):
            raise ValueError("analysis provenance does not match the ranking input digest")
        inventory = _recorded_sibling(analysis_run[0], parent, "inventory")
        if inventory != explicit_inventory or str(analysis_run[1]) != receipt.scan_session_id:
            raise ValueError("explicit inventory or session does not match the provenance chain")
        expected_inventory_digest = str(analysis_run[2])
    finally:
        analysis_db.close()
    inventory_db = _open_database(inventory, INVENTORY_APPLICATION_ID, "inventory")
    session = inventory_db.execute(
        "SELECT source_root,state FROM scan_sessions WHERE scan_session_id=?",
        (receipt.scan_session_id,),
    ).fetchone()
    if session is None or session[1] != "COMPLETE":
        inventory_db.close()
        raise ValueError("preflight requires the recorded COMPLETE inventory session")
    actual_inventory_digest = _inventory_digest(inventory_db, receipt.scan_session_id)
    if actual_inventory_digest != expected_inventory_digest:
        inventory_db.close()
        raise ValueError("inventory logical digest does not match the analysis snapshot")
    return inventory_db, str(session[0]), actual_inventory_digest


def _enumerate_members(
    connection: sqlite3.Connection,
    session_id: str,
    archives: list[dict[str, Any]],
    maximum_inventory_rows: int,
    maximum_members: int,
) -> tuple[list[dict[str, Any]], int, int]:
    total_rows = int(connection.execute(
        "SELECT COUNT(*) FROM files WHERE scan_session_id=?", (session_id,),
    ).fetchone()[0])
    if total_rows > maximum_inventory_rows:
        raise ValueError("inventory file count exceeds the configured preflight row bound")
    roots = [str(action["relative_path"]) for action in archives]
    errors = [str(row[0]) for row in connection.execute(
        "SELECT relative_path FROM scan_errors WHERE scan_session_id=? ORDER BY relative_path",
        (session_id,),
    )]
    if any(
        _under(error, root) or _under(root, error)
        for error in errors for root in roots
    ):
        raise ValueError("selected archive region intersects recorded scan errors")
    groups = [{
        "candidate_id": str(action["candidate_id"]),
        "relative_path": str(action["relative_path"]),
        "proposed_archive_label": str(action["proposed_archive_label"]),
        "expected_file_count": int(action["file_count"]),
        "expected_logical_bytes": int(action["recursive_bytes"]),
        "members": [],
    } for action in archives]
    selected_count = 0
    selected_bytes = 0
    for row in connection.execute(
        "SELECT relative_path,logical_bytes,created_ns,modified_ns,attributes,entry_type,"
        "observation_status FROM files WHERE scan_session_id=? ORDER BY relative_path COLLATE BINARY",
        (session_id,),
    ):
        path = str(row[0])
        matched = next((index for index, root in enumerate(roots) if _under(path, root)), None)
        if matched is None:
            continue
        if row[5] != "FILE" or row[6] != "OBSERVED":
            raise ValueError("selected archive region contains a non-regular or unobserved file")
        selected_count += 1
        if selected_count > maximum_members:
            raise ValueError("selected member count exceeds the configured preflight bound")
        logical_bytes = int(row[1])
        selected_bytes += logical_bytes
        members = groups[matched]["members"]
        if not isinstance(members, list):
            raise AssertionError("preflight member accumulator is invalid")
        members.append({
            "relative_path": path,
            "logical_bytes": logical_bytes,
            "created_ns": None if row[2] is None else int(row[2]),
            "modified_ns": None if row[3] is None else int(row[3]),
            "attributes": int(row[4]),
        })
    for group in groups:
        members = group["members"]
        if not isinstance(members, list):
            raise AssertionError("preflight member accumulator is invalid")
        if len(members) != group["expected_file_count"] or sum(
            int(member["logical_bytes"]) for member in members
        ) != group["expected_logical_bytes"]:
            raise ValueError("enumerated archive members do not reconcile with the approved plan")
    return groups, selected_count, selected_bytes


def compile_preflight_manifest(
    plans_path: str | Path,
    approval_receipt_path: str | Path,
    inventory_path: str | Path,
    manifest_path: str | Path,
    *,
    maximum_inventory_rows: int = 10_000_000,
    maximum_members: int = 1_000_000,
) -> PreflightResult:
    if maximum_inventory_rows < 1 or maximum_members < 1:
        raise ValueError("preflight row and member bounds must be positive")
    plans = Path(plans_path).expanduser().resolve(strict=True)
    receipt_path = Path(approval_receipt_path).expanduser().resolve(strict=True)
    inventory = Path(inventory_path).expanduser().resolve(strict=True)
    destination = Path(manifest_path).expanduser().resolve(strict=False)
    if len({plans, receipt_path, inventory, destination}) != 4:
        raise ValueError("plans, receipt, inventory, and manifest paths must be distinct")
    if any(path.parent != plans.parent for path in (receipt_path, inventory, destination)):
        raise ValueError("preflight inputs and new manifest must be sibling external artifacts")
    if destination.exists():
        raise ValueError("preflight manifest must be a new file")
    receipt = load_receipt(receipt_path)
    archives = _archive_actions(receipt)
    plans_db = _open_database(plans, PLAN_APPLICATION_ID, "plans")
    try:
        ranking_path, ranking_run_id = _verify_plan(plans_db, receipt, archives)
    finally:
        plans_db.close()
    inventory_db, source_root, inventory_digest = _trace_inventory(
        plans.parent, ranking_path, ranking_run_id, receipt, inventory
    )
    try:
        groups, member_count, logical_bytes = _enumerate_members(
            inventory_db, receipt.scan_session_id, archives,
            maximum_inventory_rows, maximum_members,
        )
    finally:
        inventory_db.close()
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "code_version": CODE_VERSION,
        "state": "PREFLIGHT_ONLY_NON_EXECUTABLE",
        "authorizations": {
            "source_content_read_authorized": False,
            "execution_authorized": False,
            "archive_creation_authorized": False,
            "original_removal_authorized": False,
        },
        "source": {
            "approval_receipt_digest": receipt.receipt_digest,
            "plan_run_id": receipt.plan_run_id,
            "plan_id": receipt.plan_id,
            "scan_session_id": receipt.scan_session_id,
            "inventory_filename": inventory.name,
            "inventory_logical_digest": inventory_digest,
            "recorded_source_root": source_root,
        },
        "bounds": {
            "maximum_inventory_rows": maximum_inventory_rows,
            "maximum_members": maximum_members,
        },
        "archives": groups,
        "totals": {
            "archive_count": len(groups),
            "member_count": member_count,
            "logical_bytes": logical_bytes,
        },
        "limitations": [
            "NO_SOURCE_PATH_WAS_OPENED_OR_REVALIDATED",
            "NO_DESTINATION_CAPACITY_WAS_OBSERVED",
            "NO_ARCHIVE_WAS_CREATED",
            "FUTURE_EXECUTION_REQUIRES_A_SEPARATE_COMPONENT_AND_NEW_AUTHORIZATION",
        ],
    }
    manifest_digest = hashlib.sha256(_canonical(manifest)).hexdigest()
    manifest["manifest_digest"] = manifest_digest
    with destination.open("xb") as stream:
        stream.write(_canonical(manifest) + b"\n")
    return PreflightResult(manifest_digest, len(groups), member_count, logical_bytes)
