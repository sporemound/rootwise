"""Guided, deterministic Stage 0.17 acceptance workflow helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .evaluator import (
    GATE_MEASUREMENT_FIELDS,
    MAX_MANIFEST_BYTES,
    REPORT_SCHEMA_ID,
    REQUIRED_GATES,
    SCHEMA_ID,
)


@dataclass(frozen=True)
class ManifestInitialization:
    output_path: str
    manifest_digest: str
    required_gate_count: int


@dataclass(frozen=True)
class ReportInspection:
    status: str
    subject_revision: str
    output_digest: str
    passed_gate_count: int
    failed_gate_count: int
    incomplete_gate_count: int


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bounded_string(value: object, label: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{label} must be a non-empty bounded string")
    return value


def _commit_id(value: object, label: str) -> str:
    text = _bounded_string(value, label, 40)
    if len(text) != 40 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{label} must be a lowercase full Git commit ID")
    return text


def _digest(value: object, label: str) -> str:
    text = _bounded_string(value, label, 64)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def initialize_manifest(
    output_path: str | Path,
    *,
    subject_revision: str,
    producer: str,
    created_at: str,
    host_id: str,
    os_name: str,
    python_version: str,
) -> ManifestInitialization:
    output = Path(output_path).expanduser().resolve(strict=False)
    if output.exists() or not output.parent.is_dir():
        raise ValueError("manifest output must be a new file in an existing directory")
    value = {
        "schema": SCHEMA_ID,
        "subject_revision": _commit_id(subject_revision, "subject_revision"),
        "producer": _bounded_string(producer, "producer"),
        "created_at": _bounded_string(created_at, "created_at"),
        "environment": {
            "host_id": _bounded_string(host_id, "host_id"),
            "os": _bounded_string(os_name, "os"),
            "python": _bounded_string(python_version, "python"),
        },
        "gates": [],
    }
    encoded = _canonical(value) + b"\n"
    output.write_bytes(encoded)
    return ManifestInitialization(str(output), _sha256(encoded), len(REQUIRED_GATES))


def gate_guide() -> dict[str, object]:
    return {
        "schema": SCHEMA_ID,
        "status_semantics": {
            "PASS": "every required gate is present and satisfies its rule",
            "FAIL": "at least one supplied gate fails its rule",
            "INCOMPLETE": "no supplied gate fails, but required evidence is absent",
        },
        "gates": [{
            "gate_id": gate_id,
            "required_measurements": list(GATE_MEASUREMENT_FIELDS[gate_id]),
        } for gate_id in sorted(REQUIRED_GATES)],
    }


def _load_canonical_report(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("acceptance report exceeds the size limit")
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {
        "schema", "code_version", "status", "subject_revision", "input_digest",
        "environment", "gates", "output_digest",
    }:
        raise ValueError("acceptance report keys do not match the required schema")
    if value["schema"] != REPORT_SCHEMA_ID or raw != _canonical(value) + b"\n":
        raise ValueError("acceptance report must use the expected schema and canonical JSON")
    recorded = _digest(value["output_digest"], "output_digest")
    body = dict(value)
    del body["output_digest"]
    if _sha256(_canonical(body)) != recorded:
        raise ValueError("acceptance report output digest mismatch")
    return value


def inspect_report(report_path: str | Path) -> ReportInspection:
    value = _load_canonical_report(Path(report_path).expanduser().resolve(strict=True))
    _bounded_string(value["code_version"], "code_version")
    subject = _commit_id(value["subject_revision"], "subject_revision")
    _digest(value["input_digest"], "input_digest")
    environment = value["environment"]
    if not isinstance(environment, dict) or set(environment) != {"host_id", "os", "python"}:
        raise ValueError("report environment keys do not match the required schema")
    for name in ("host_id", "os", "python"):
        _bounded_string(environment[name], f"environment.{name}")
    gates = value["gates"]
    if not isinstance(gates, list):
        raise ValueError("report gates must be a sorted list")
    identifiers: list[str] = []
    statuses: list[str] = []
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != {
            "gate_id", "status", "evidence_sha256", "reasons"
        }:
            raise ValueError("report gate keys do not match the required schema")
        gate_id = _bounded_string(gate["gate_id"], "gate_id")
        if gate_id not in REQUIRED_GATES:
            raise ValueError(f"report contains an unknown gate: {gate_id}")
        status = gate["status"]
        if status not in {"PASS", "FAIL", "INCOMPLETE"}:
            raise ValueError("report gate status is invalid")
        evidence = gate["evidence_sha256"]
        if status == "INCOMPLETE":
            if evidence is not None:
                raise ValueError("incomplete report gate must not claim evidence")
        else:
            _digest(evidence, "evidence_sha256")
        reasons = gate["reasons"]
        if not isinstance(reasons, list) or any(
            not isinstance(reason, str) or not reason or len(reason) > 2_000 for reason in reasons
        ):
            raise ValueError("report gate reasons must be bounded strings")
        if (status == "PASS" and reasons) or (status != "PASS" and not reasons):
            raise ValueError("report gate reasons do not match its status")
        identifiers.append(gate_id)
        statuses.append(status)
    if identifiers != sorted(REQUIRED_GATES):
        raise ValueError("report must contain every required gate exactly once in sorted order")
    passed = statuses.count("PASS")
    failed = statuses.count("FAIL")
    incomplete = statuses.count("INCOMPLETE")
    expected = "FAIL" if failed else ("INCOMPLETE" if incomplete else "PASS")
    if value["status"] != expected:
        raise ValueError("report aggregate status does not match its gates")
    return ReportInspection(
        expected, subject, str(value["output_digest"]), passed, failed, incomplete
    )
