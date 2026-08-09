"""Strict reader for immutable Stage 0.8 non-executing approval receipts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paretodrive_approval.receipt import RECEIPT_SCHEMA_VERSION


@dataclass(frozen=True)
class ReceiptSnapshot:
    value: dict[str, Any]
    receipt_digest: str
    plan_run_id: str
    plan_id: str
    plan_output_digest: str
    plan_input_digest: str
    decisions_digest: str
    scan_session_id: str
    actions: tuple[dict[str, Any], ...]


def _text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"approval receipt {key} is invalid")
    return value


def _sha256(mapping: dict[str, Any], key: str) -> str:
    value = _text(mapping, key)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"approval receipt {key} must be lowercase SHA-256")
    return value


def load_receipt(path: str | Path) -> ReceiptSnapshot:
    receipt_path = Path(path).expanduser().resolve(strict=True)
    try:
        raw = json.loads(receipt_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("approval receipt is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version", "code_version", "state", "authorizations", "approval", "source",
        "plan", "limitations", "receipt_digest",
    }:
        raise ValueError("approval receipt fields do not match the required schema")
    value: dict[str, Any] = dict(raw)
    recorded = value.pop("receipt_digest")
    if not isinstance(recorded, str):
        raise ValueError("approval receipt digest is invalid")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != recorded:
        raise ValueError("approval receipt digest mismatch")
    value["receipt_digest"] = recorded
    if value["schema_version"] != RECEIPT_SCHEMA_VERSION or value[
        "state"
    ] != "PLAN_SELECTED_FOR_FUTURE_EXECUTOR_REVIEW":
        raise ValueError("approval receipt schema or state mismatch")
    authorizations = value["authorizations"]
    if not isinstance(authorizations, dict) or authorizations != {
        "execution_authorized": False,
        "archive_creation_authorized": False,
        "original_removal_authorized": False,
    }:
        raise ValueError("approval receipt must not authorize filesystem action")
    source = value["source"]
    plan = value["plan"]
    if not isinstance(source, dict) or not isinstance(plan, dict):
        raise ValueError("approval receipt source or plan section is invalid")
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("approval receipt plan actions are missing")
    if any(not isinstance(action, dict) for action in actions):
        raise ValueError("approval receipt contains an invalid action")
    return ReceiptSnapshot(
        value,
        recorded,
        _text(source, "plan_run_id"),
        _sha256(source, "plan_id"),
        _sha256(source, "plan_output_digest"),
        _sha256(source, "input_digest"),
        _sha256(source, "decisions_digest"),
        _text(source, "scan_session_id"),
        tuple(dict(action) for action in actions),
    )
