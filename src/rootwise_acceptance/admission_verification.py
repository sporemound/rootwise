"""Independent, read-only Stage 0.20 admission-chain verification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .admission import (
    ADMISSION_SCHEMA_ID,
    _canonical,
    _commit_id,
    _hash_file,
    _load_bounded_json,
    _sha256,
    _validate_provenance,
    _validate_release_verification,
)
from .evaluator import MAX_MANIFEST_BYTES, REQUIRED_GATES
from .workflow import inspect_report

RECEIPT_KEYS = {
    "schema", "code_version", "status", "source_revision", "source_manifest_sha256",
    "acceptance_report_sha256", "acceptance_output_digest", "passed_gate_count",
    "source_archive_name", "source_archive_sha256", "build_provenance_sha256",
    "release_verification_sha256", "release_candidate_admitted",
    "filesystem_execution_authorized", "receipt_digest",
}


@dataclass(frozen=True)
class AdmissionVerification:
    status: str
    source_revision: str
    source_archive_sha256: str
    receipt_digest: str
    receipt_file_sha256: str
    passed_gate_count: int


def _bounded_string(value: object, label: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{label} must be a non-empty bounded string")
    return value


def _load_receipt(path: Path) -> tuple[dict[str, object], str]:
    raw = path.read_bytes()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("admission receipt exceeds the size limit")
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != RECEIPT_KEYS:
        raise ValueError("admission receipt keys do not match the required schema")
    if value["schema"] != ADMISSION_SCHEMA_ID or raw != _canonical(value) + b"\n":
        raise ValueError("admission receipt must use the expected schema and canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def _stable_archive_hash(path: Path) -> str:
    before = path.stat()
    digest = _hash_file(path)
    after = path.stat()
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise ValueError("source archive changed during admission verification")
    return digest


def verify_admission(
    receipt_path: str | Path,
    report_path: str | Path,
    archive_path: str | Path,
    provenance_path: str | Path,
    verification_path: str | Path,
) -> AdmissionVerification:
    paths = tuple(
        Path(path).expanduser().resolve(strict=True)
        for path in (receipt_path, report_path, archive_path, provenance_path, verification_path)
    )
    receipt, report, archive, provenance, verification = paths
    if len(set(paths)) != len(paths):
        raise ValueError("admission receipt and bound inputs must be distinct")
    if not all(path.is_file() for path in paths):
        raise ValueError("admission receipt and bound inputs must be regular files")

    receipt_value, receipt_file_sha256 = _load_receipt(receipt)
    if receipt_value["status"] != "ADMITTED" or receipt_value["release_candidate_admitted"] is not True:
        raise ValueError("admission receipt does not record an admitted candidate")
    if receipt_value["filesystem_execution_authorized"] is not False:
        raise ValueError("admission receipt must not authorize filesystem execution")
    code_version = _bounded_string(receipt_value["code_version"], "code_version", 100)
    recorded_revision = _commit_id(receipt_value["source_revision"], "source_revision")
    recorded_manifest = _sha256(
        receipt_value["source_manifest_sha256"], "source_manifest_sha256"
    )
    recorded_digest = _sha256(receipt_value["receipt_digest"], "receipt_digest")
    body = dict(receipt_value)
    del body["receipt_digest"]
    if hashlib.sha256(_canonical(body)).hexdigest() != recorded_digest:
        raise ValueError("admission receipt semantic digest mismatch")

    report_before = _hash_file(report)
    inspection = inspect_report(report)
    report_after = _hash_file(report)
    if report_before != report_after:
        raise ValueError("acceptance report changed during admission verification")
    if inspection.status != "PASS" or inspection.passed_gate_count != len(REQUIRED_GATES):
        raise ValueError("admission verification requires a complete PASS acceptance report")
    provenance_value, provenance_sha256 = _load_bounded_json(provenance, "build provenance")
    source_revision, source_manifest_sha256 = _validate_provenance(provenance_value)
    if inspection.subject_revision != source_revision:
        raise ValueError("acceptance report and build provenance revision mismatch")
    archive_sha256 = _stable_archive_hash(archive)
    verification_value, verification_sha256 = _load_bounded_json(
        verification, "release verification"
    )
    _validate_release_verification(verification_value, archive.name, archive_sha256)

    expected_body: dict[str, object] = {
        "schema": ADMISSION_SCHEMA_ID,
        "code_version": code_version,
        "status": "ADMITTED",
        "source_revision": source_revision,
        "source_manifest_sha256": source_manifest_sha256,
        "acceptance_report_sha256": report_after,
        "acceptance_output_digest": inspection.output_digest,
        "passed_gate_count": inspection.passed_gate_count,
        "source_archive_name": archive.name,
        "source_archive_sha256": archive_sha256,
        "build_provenance_sha256": provenance_sha256,
        "release_verification_sha256": verification_sha256,
        "release_candidate_admitted": True,
        "filesystem_execution_authorized": False,
    }
    if body != expected_body or recorded_revision != source_revision or (
        recorded_manifest != source_manifest_sha256
    ):
        raise ValueError("admission receipt does not match the supplied verified artifact chain")
    return AdmissionVerification(
        "VERIFIED", source_revision, archive_sha256, recorded_digest,
        receipt_file_sha256, inspection.passed_gate_count,
    )
