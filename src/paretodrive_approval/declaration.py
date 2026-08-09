"""Strict human-authored declaration bound to one immutable plan proposal."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = "paretodrive-plan-approval-declaration-1"
INTENT = "SELECT_PLAN_FOR_FUTURE_EXECUTOR_REVIEW"
ACKNOWLEDGEMENTS = (
    "ARCHIVE_CREATION_REQUIRES_A_SEPARATE_EXECUTOR",
    "ORIGINAL_REMOVAL_REQUIRES_A_LATER_SEPARATE_REVIEW",
)


@dataclass(frozen=True)
class ApprovalDeclaration:
    plan_run_id: str
    plan_id: str
    plan_output_digest: str
    decisions_digest: str
    operator: str
    approved_at: str
    note: str
    declaration_digest: str


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be lowercase SHA-256")
    return value


def load_declaration(path: str | Path) -> ApprovalDeclaration:
    declaration_path = Path(path).expanduser().resolve(strict=True)
    try:
        value = json.loads(declaration_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("approval declaration is not valid UTF-8 JSON") from exc
    fields = {
        "schema_version", "plan_run_id", "plan_id", "plan_output_digest",
        "decisions_digest", "intent", "acknowledgements", "operator", "approved_at", "note",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("approval declaration fields do not match the required schema")
    if value["schema_version"] != SCHEMA_VERSION or value["intent"] != INTENT:
        raise ValueError("approval declaration schema or intent mismatch")
    if value["acknowledgements"] != list(ACKNOWLEDGEMENTS):
        raise ValueError("approval declaration acknowledgements are incomplete or reordered")
    run_id = value["plan_run_id"]
    operator = value["operator"]
    approved_at = value["approved_at"]
    note = value["note"]
    if not isinstance(run_id, str) or not run_id or len(run_id) > 128 or "\x00" in run_id:
        raise ValueError("approval plan run ID is invalid")
    if not isinstance(operator, str) or not operator.strip() or len(operator) > 200 or "\x00" in operator:
        raise ValueError("approval operator label is invalid")
    if not isinstance(note, str) or len(note) > 4_000 or "\x00" in note:
        raise ValueError("approval note is invalid")
    if not isinstance(approved_at, str):
        raise ValueError("approval timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("approval timestamp must be RFC 3339 compatible") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("approval timestamp must include an offset")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return ApprovalDeclaration(
        run_id,
        _sha256(value["plan_id"], "plan ID"),
        _sha256(value["plan_output_digest"], "plan output digest"),
        _sha256(value["decisions_digest"], "decisions digest"),
        operator,
        approved_at,
        note,
        hashlib.sha256(canonical).hexdigest(),
    )
