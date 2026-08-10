"""Fail-closed Stage 0.22 release-candidate admission."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .evaluator import MAX_MANIFEST_BYTES, REQUIRED_GATES
from .workflow import inspect_report

ADMISSION_SCHEMA_ID = "rootwise-release-admission-v1"
CODE_VERSION = "0.23.0-alpha"


@dataclass(frozen=True)
class AdmissionResult:
    status: str
    source_revision: str
    source_archive_sha256: str
    receipt_digest: str
    passed_gate_count: int


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def _load_bounded_json(path: Path, label: str) -> tuple[dict[str, object], str]:
    raw = path.read_bytes()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError(f"{label} exceeds the size limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _commit_id(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be a lowercase full Git commit ID")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_provenance(value: dict[str, object]) -> tuple[str, str]:
    if set(value) != {
        "platform", "python", "revision_check", "source_manifest_sha256",
        "source_revision", "status",
    }:
        raise ValueError("build provenance keys do not match the required schema")
    if value["status"] != "VERIFIED":
        raise ValueError("build provenance is not VERIFIED")
    revision = _commit_id(value["source_revision"], "provenance source_revision")
    source_manifest = _sha256(value["source_manifest_sha256"], "source_manifest_sha256")
    for name in ("platform", "python"):
        field = value[name]
        if not isinstance(field, str) or not field or len(field) > 1_000:
            raise ValueError(f"provenance {name} must be a bounded string")
    check = value["revision_check"]
    if not isinstance(check, dict) or check.get("passed") is not True or check.get("exit_code") != 0:
        raise ValueError("build provenance revision check did not pass")
    if check.get("stdout") != revision + "\n" or check.get("stderr") != "":
        raise ValueError("build provenance revision check output mismatch")
    return revision, source_manifest


def _validate_release_verification(
    value: dict[str, object], archive_name: str, archive_sha256: str
) -> None:
    if set(value) != {
        "command", "duration_seconds", "exit_code", "passed", "stderr", "stdout",
        "timeout_seconds", "source_archive_name", "source_archive_sha256",
    }:
        raise ValueError("release verification keys do not match the required schema")
    if value["source_archive_name"] != archive_name or value["source_archive_sha256"] != archive_sha256:
        raise ValueError("release verification does not bind the supplied source archive")
    if value["passed"] is not True or value["exit_code"] != 0 or value["stderr"] != "":
        raise ValueError("fresh-extraction release verification did not pass")
    stdout = value["stdout"]
    if not isinstance(stdout, str):
        raise ValueError("release verification stdout must be a string")
    try:
        summary = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("release verification stdout is not valid JSON") from exc
    if not isinstance(summary, dict) or summary.get("status") != "PASS" or (
        summary.get("source_unchanged") is not True
    ):
        raise ValueError("release verification summary is not a source-unchanged PASS")


def admit_release_candidate(
    report_path: str | Path,
    archive_path: str | Path,
    provenance_path: str | Path,
    verification_path: str | Path,
    output_path: str | Path,
) -> AdmissionResult:
    report = Path(report_path).expanduser().resolve(strict=True)
    archive = Path(archive_path).expanduser().resolve(strict=True)
    provenance = Path(provenance_path).expanduser().resolve(strict=True)
    verification = Path(verification_path).expanduser().resolve(strict=True)
    output = Path(output_path).expanduser().resolve(strict=False)
    if len({report, archive, provenance, verification, output}) != 5:
        raise ValueError("admission inputs and output must be distinct")
    if output.exists() or not output.parent.is_dir():
        raise ValueError("admission output must be a new file in an existing directory")
    if not all(path.is_file() for path in (report, archive, provenance, verification)):
        raise ValueError("admission inputs must be existing regular files")

    inspection = inspect_report(report)
    if inspection.status != "PASS" or inspection.passed_gate_count != len(REQUIRED_GATES):
        raise ValueError("release admission requires a complete PASS acceptance report")
    provenance_value, provenance_sha256 = _load_bounded_json(provenance, "build provenance")
    source_revision, source_manifest_sha256 = _validate_provenance(provenance_value)
    if inspection.subject_revision != source_revision:
        raise ValueError("acceptance report and build provenance revision mismatch")
    archive_sha256 = _hash_file(archive)
    verification_value, verification_sha256 = _load_bounded_json(
        verification, "release verification"
    )
    _validate_release_verification(verification_value, archive.name, archive_sha256)
    report_sha256 = _hash_file(report)
    receipt: dict[str, object] = {
        "schema": ADMISSION_SCHEMA_ID,
        "code_version": CODE_VERSION,
        "status": "ADMITTED",
        "source_revision": source_revision,
        "source_manifest_sha256": source_manifest_sha256,
        "acceptance_report_sha256": report_sha256,
        "acceptance_output_digest": inspection.output_digest,
        "passed_gate_count": inspection.passed_gate_count,
        "source_archive_name": archive.name,
        "source_archive_sha256": archive_sha256,
        "build_provenance_sha256": provenance_sha256,
        "release_verification_sha256": verification_sha256,
        "release_candidate_admitted": True,
        "filesystem_execution_authorized": False,
    }
    receipt_digest = hashlib.sha256(_canonical(receipt)).hexdigest()
    receipt["receipt_digest"] = receipt_digest
    output.write_bytes(_canonical(receipt) + b"\n")
    return AdmissionResult(
        "ADMITTED", source_revision, archive_sha256, receipt_digest,
        inspection.passed_gate_count,
    )
