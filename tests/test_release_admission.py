from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rootwise_acceptance.admission import ADMISSION_SCHEMA_ID, admit_release_candidate
from rootwise_acceptance.cli import main as acceptance_main
from rootwise_acceptance.evaluator import REQUIRED_GATES, evaluate_acceptance

from .test_acceptance_evaluator import _manifest, _write


def _admission_files(tmp_path: Path, *, complete: bool = True) -> tuple[Path, Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest = tmp_path / "manifest.json"
    _write(manifest, _manifest() if complete else _manifest([]))
    report = tmp_path / "report.json"
    evaluate_acceptance(manifest, report)
    archive = tmp_path / "rootwise-source.zip"
    archive.write_bytes(b"synthetic deterministic source archive\n")
    revision = "a" * 40
    provenance = tmp_path / "BUILD_PROVENANCE.json"
    _write(provenance, {
        "platform": "synthetic-windows",
        "python": "3.14.3",
        "revision_check": {
            "passed": True, "exit_code": 0, "stdout": revision + "\n", "stderr": "",
        },
        "source_manifest_sha256": "b" * 64,
        "source_revision": revision,
        "status": "VERIFIED",
    })
    verification = tmp_path / "VERIFY-RELEASE.json"
    _write(verification, {
        "command": ["python", "tools/verify.py"],
        "duration_seconds": 1.0,
        "exit_code": 0,
        "passed": True,
        "stderr": "",
        "stdout": json.dumps({"status": "PASS", "source_unchanged": True}) + "\n",
        "source_archive_name": archive.name,
        "source_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "timeout_seconds": 240,
    })
    return report, archive, provenance, verification


def test_release_admission_binds_complete_evidence_deterministically(tmp_path: Path) -> None:
    report, archive, provenance, verification = _admission_files(tmp_path)
    before = {path: path.read_bytes() for path in (report, archive, provenance, verification)}
    first = tmp_path / "admission-one.json"
    second = tmp_path / "admission-two.json"
    first_result = admit_release_candidate(report, archive, provenance, verification, first)
    second_result = admit_release_candidate(report, archive, provenance, verification, second)
    assert first_result.status == "ADMITTED"
    assert first_result.passed_gate_count == len(REQUIRED_GATES)
    assert first_result.receipt_digest == second_result.receipt_digest
    assert first.read_bytes() == second.read_bytes()
    assert before == {path: path.read_bytes() for path in (report, archive, provenance, verification)}
    receipt = json.loads(first.read_text(encoding="utf-8"))
    assert receipt["schema"] == ADMISSION_SCHEMA_ID
    assert receipt["release_candidate_admitted"] is True
    assert receipt["filesystem_execution_authorized"] is False
    assert receipt["source_archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()


def test_release_admission_refuses_incomplete_acceptance_without_output(tmp_path: Path) -> None:
    report, archive, provenance, verification = _admission_files(tmp_path, complete=False)
    output = tmp_path / "refused.json"
    with pytest.raises(ValueError, match="complete PASS"):
        admit_release_candidate(report, archive, provenance, verification, output)
    assert not output.exists()


def test_release_admission_rejects_revision_and_verification_mismatch(tmp_path: Path) -> None:
    report, archive, provenance, verification = _admission_files(tmp_path)
    value = json.loads(provenance.read_text(encoding="utf-8"))
    value["source_revision"] = "c" * 40
    value["revision_check"]["stdout"] = "c" * 40 + "\n"
    _write(provenance, value)
    with pytest.raises(ValueError, match="revision mismatch"):
        admit_release_candidate(
            report, archive, provenance, verification, tmp_path / "mismatch.json"
        )
    report, archive, provenance, verification = _admission_files(tmp_path / "second")
    value = json.loads(verification.read_text(encoding="utf-8"))
    value["passed"] = False
    _write(verification, value)
    with pytest.raises(ValueError, match="did not pass"):
        admit_release_candidate(
            report, archive, provenance, verification, tmp_path / "second" / "failed.json"
        )
    report, archive, provenance, verification = _admission_files(tmp_path / "third")
    archive.write_bytes(b"different source archive\n")
    with pytest.raises(ValueError, match="does not bind"):
        admit_release_candidate(
            report, archive, provenance, verification, tmp_path / "third" / "wrong-archive.json"
        )


def test_release_admission_rejects_tampering_overwrite_and_path_reuse(tmp_path: Path) -> None:
    report, archive, provenance, verification = _admission_files(tmp_path)
    report.write_bytes(report.read_bytes().replace(b'"status":"PASS"', b'"status":"FAIL"'))
    with pytest.raises(ValueError, match="canonical JSON|digest mismatch"):
        admit_release_candidate(
            report, archive, provenance, verification, tmp_path / "tampered.json"
        )
    report, archive, provenance, verification = _admission_files(tmp_path / "fresh")
    existing = tmp_path / "fresh" / "existing.json"
    existing.write_text("occupied", encoding="utf-8")
    with pytest.raises(ValueError, match="new file"):
        admit_release_candidate(report, archive, provenance, verification, existing)
    with pytest.raises(ValueError, match="must be distinct"):
        admit_release_candidate(report, archive, provenance, verification, report)


def test_release_admission_cli_emits_admitted_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report, archive, provenance, verification = _admission_files(tmp_path)
    output = tmp_path / "admission.json"
    assert acceptance_main([
        "admit", "--report", str(report), "--archive", str(archive),
        "--provenance", str(provenance), "--verification", str(verification),
        "--output", str(output),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ADMITTED"
    assert result["passed_gate_count"] == len(REQUIRED_GATES)
