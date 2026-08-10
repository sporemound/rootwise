"""Fail-closed evaluation of externally produced acceptance evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SCHEMA_ID = "rootwise-acceptance-evidence-v1"
REPORT_SCHEMA_ID = "rootwise-acceptance-report-v1"
CODE_VERSION = "0.21.0-alpha"
MAX_MANIFEST_BYTES = 1_048_576
SHA256_LENGTH = 64


@dataclass(frozen=True)
class AcceptanceResult:
    status: str
    input_digest: str
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


def _boolean(measurements: dict[str, object], name: str) -> bool:
    return measurements.get(name) is True


def _number(measurements: dict[str, object], name: str) -> float | None:
    value = measurements.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


def _within_budget(measurements: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    for metric in ("duration_seconds", "peak_rss_bytes", "temporary_bytes"):
        observed = _number(measurements, metric)
        limit = _number(measurements, f"maximum_{metric}")
        if observed is None or limit is None:
            reasons.append(f"{metric} and maximum_{metric} must be non-negative numbers")
        elif observed > limit:
            reasons.append(f"{metric} exceeds its declared acceptance budget")
    return reasons


def _scale_gate(measurements: dict[str, object]) -> list[str]:
    reasons = _within_budget(measurements)
    observed = _number(measurements, "observed_entry_count")
    minimum = _number(measurements, "minimum_entry_count")
    if observed is None or minimum is None or minimum < 1_000_000:
        reasons.append("minimum_entry_count must be at least 1000000")
    elif observed < minimum:
        reasons.append("observed_entry_count is below the declared minimum")
    for field in ("completed", "inputs_unchanged"):
        if not _boolean(measurements, field):
            reasons.append(f"{field} must be true")
    return reasons


def _viewer_gate(measurements: dict[str, object]) -> list[str]:
    reasons = _scale_gate(measurements)
    query_count = _number(measurements, "query_count")
    p95 = _number(measurements, "p95_query_seconds")
    maximum = _number(measurements, "maximum_p95_query_seconds")
    if query_count is None or query_count < 100:
        reasons.append("query_count must be at least 100")
    if p95 is None or maximum is None or p95 > maximum:
        reasons.append("p95_query_seconds must satisfy its declared budget")
    if not _boolean(measurements, "query_only"):
        reasons.append("query_only must be true")
    return reasons


def _booleans(*names: str) -> Callable[[dict[str, object]], list[str]]:
    def validate(measurements: dict[str, object]) -> list[str]:
        return [f"{name} must be true" for name in names if not _boolean(measurements, name)]
    return validate


VALIDATORS: dict[str, Callable[[dict[str, object]], list[str]]] = {
    "scanner_scale": _scale_gate,
    "viewer_search_scale": _viewer_gate,
    "snapshot_pipeline_scale": _scale_gate,
    "enrichment_distinct_volume": _booleans(
        "completed", "distinct_os_volumes", "selection_immutable",
        "source_contents_unchanged", "access_time_risk_acknowledged",
    ),
    "forced_interruption_recovery": _booleans(
        "interruption_observed", "stopped_state_recorded", "resume_completed",
        "source_contents_unchanged",
    ),
    "database_corruption": _booleans("corruption_detected", "failed_closed"),
    "metadata_edge_cases": _booleans(
        "long_paths_tested", "invalid_metadata_tested", "permission_errors_tested",
        "concurrent_mutation_tested", "failed_closed",
    ),
    "visible_gui_review": _booleans("visible_session", "review_completed", "no_critical_defects"),
    "independent_replication": _booleans(
        "independent_host", "fresh_clone", "revision_matched", "mandatory_tests_passed",
        "source_contents_unchanged",
    ),
}
REQUIRED_GATES = tuple(VALIDATORS)
GATE_MEASUREMENT_FIELDS: dict[str, tuple[str, ...]] = {
    "scanner_scale": (
        "completed", "duration_seconds", "inputs_unchanged", "maximum_duration_seconds",
        "maximum_peak_rss_bytes", "maximum_temporary_bytes", "minimum_entry_count",
        "observed_entry_count", "peak_rss_bytes", "temporary_bytes",
    ),
    "viewer_search_scale": (
        "completed", "duration_seconds", "inputs_unchanged", "maximum_duration_seconds",
        "maximum_p95_query_seconds", "maximum_peak_rss_bytes", "maximum_temporary_bytes",
        "minimum_entry_count", "observed_entry_count", "p95_query_seconds", "peak_rss_bytes",
        "query_count", "query_only", "temporary_bytes",
    ),
    "snapshot_pipeline_scale": (
        "completed", "duration_seconds", "inputs_unchanged", "maximum_duration_seconds",
        "maximum_peak_rss_bytes", "maximum_temporary_bytes", "minimum_entry_count",
        "observed_entry_count", "peak_rss_bytes", "temporary_bytes",
    ),
    "enrichment_distinct_volume": (
        "access_time_risk_acknowledged", "completed", "distinct_os_volumes",
        "selection_immutable", "source_contents_unchanged",
    ),
    "forced_interruption_recovery": (
        "interruption_observed", "resume_completed", "source_contents_unchanged",
        "stopped_state_recorded",
    ),
    "database_corruption": ("corruption_detected", "failed_closed"),
    "metadata_edge_cases": (
        "concurrent_mutation_tested", "failed_closed", "invalid_metadata_tested",
        "long_paths_tested", "permission_errors_tested",
    ),
    "visible_gui_review": ("no_critical_defects", "review_completed", "visible_session"),
    "independent_replication": (
        "fresh_clone", "independent_host", "mandatory_tests_passed", "revision_matched",
        "source_contents_unchanged",
    ),
}


def _load_manifest(path: Path) -> tuple[dict[str, object], str]:
    raw = path.read_bytes()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("acceptance manifest exceeds the size limit")
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {
        "schema", "subject_revision", "producer", "created_at", "environment", "gates"
    }:
        raise ValueError("acceptance manifest keys do not match the required schema")
    if value["schema"] != SCHEMA_ID or raw != _canonical(value) + b"\n":
        raise ValueError("acceptance manifest must use the expected schema and canonical JSON")
    revision = value["subject_revision"]
    if not isinstance(revision, str) or len(revision) != 40 or any(
        character not in "0123456789abcdef" for character in revision
    ):
        raise ValueError("subject_revision must be a lowercase full Git commit ID")
    _bounded_string(value["producer"], "producer")
    _bounded_string(value["created_at"], "created_at")
    environment = value["environment"]
    if not isinstance(environment, dict) or set(environment) != {"host_id", "os", "python"}:
        raise ValueError("environment keys do not match the required schema")
    for name in ("host_id", "os", "python"):
        _bounded_string(environment[name], f"environment.{name}")
    return value, _sha256(raw)


def _evaluate_gate(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {
        "gate_id", "evidence_sha256", "measurements", "notes"
    }:
        raise ValueError("acceptance gate keys do not match the required schema")
    gate_id = _bounded_string(value["gate_id"], "gate_id")
    evidence = value["evidence_sha256"]
    if not isinstance(evidence, str) or len(evidence) != SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in evidence
    ):
        raise ValueError("evidence_sha256 must be a lowercase SHA-256 digest")
    measurements = value["measurements"]
    if not isinstance(measurements, dict) or len(measurements) > 100:
        raise ValueError("measurements must be a bounded object")
    _bounded_string(value["notes"], "notes", 2_000)
    validator = VALIDATORS.get(gate_id)
    if validator is None:
        raise ValueError(f"unknown acceptance gate: {gate_id}")
    reasons = validator(measurements)
    return {
        "gate_id": gate_id,
        "status": "PASS" if not reasons else "FAIL",
        "evidence_sha256": evidence,
        "reasons": reasons,
    }


def evaluate_acceptance(manifest_path: str | Path, report_path: str | Path) -> AcceptanceResult:
    manifest = Path(manifest_path).expanduser().resolve(strict=True)
    report = Path(report_path).expanduser().resolve(strict=False)
    if manifest == report or manifest.parent != report.parent or report.exists():
        raise ValueError("manifest and new report must be distinct siblings")
    value, input_digest = _load_manifest(manifest)
    gates_value = value["gates"]
    if not isinstance(gates_value, list):
        raise ValueError("gates must be a sorted list")
    evaluated = [_evaluate_gate(gate) for gate in gates_value]
    gate_ids = [str(gate["gate_id"]) for gate in evaluated]
    if gate_ids != sorted(set(gate_ids)):
        raise ValueError("gates must have sorted unique gate IDs")
    missing = sorted(set(REQUIRED_GATES) - set(gate_ids))
    for gate_id in missing:
        evaluated.append({
            "gate_id": gate_id, "status": "INCOMPLETE", "evidence_sha256": None,
            "reasons": ["required gate evidence is absent"],
        })
    evaluated.sort(key=lambda gate: str(gate["gate_id"]))
    passed = sum(gate["status"] == "PASS" for gate in evaluated)
    failed = sum(gate["status"] == "FAIL" for gate in evaluated)
    incomplete = sum(gate["status"] == "INCOMPLETE" for gate in evaluated)
    status = "FAIL" if failed else ("INCOMPLETE" if incomplete else "PASS")
    body: dict[str, object] = {
        "schema": REPORT_SCHEMA_ID,
        "code_version": CODE_VERSION,
        "status": status,
        "subject_revision": value["subject_revision"],
        "input_digest": input_digest,
        "environment": value["environment"],
        "gates": evaluated,
    }
    output_digest = _sha256(_canonical(body))
    body["output_digest"] = output_digest
    report.write_bytes(_canonical(body) + b"\n")
    return AcceptanceResult(status, input_digest, output_digest, passed, failed, incomplete)
