from __future__ import annotations

import json
from pathlib import Path

import pytest

from rootwise_acceptance.admission import admit_release_candidate
from rootwise_acceptance.admission_verification import verify_admission
from rootwise_acceptance.cli import main as acceptance_main

from .test_release_admission import _admission_files


def _verified_chain(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    report, archive, provenance, verification = _admission_files(tmp_path)
    receipt = tmp_path / "admission.json"
    admit_release_candidate(report, archive, provenance, verification, receipt)
    return receipt, report, archive, provenance, verification


def test_verify_admission_rechecks_complete_chain_without_writes(tmp_path: Path) -> None:
    paths = _verified_chain(tmp_path)
    before = {path: path.read_bytes() for path in paths}
    first = verify_admission(*paths)
    second = verify_admission(*paths)
    assert first == second
    assert first.status == "VERIFIED"
    assert first.source_revision == "a" * 40
    assert first.passed_gate_count == 9
    assert before == {path: path.read_bytes() for path in paths}


def test_verify_admission_rejects_noncanonical_and_semantically_tampered_receipts(
    tmp_path: Path,
) -> None:
    receipt, report, archive, provenance, verification = _verified_chain(tmp_path)
    value = json.loads(receipt.read_text(encoding="utf-8"))
    receipt.write_text(json.dumps(value, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical JSON"):
        verify_admission(receipt, report, archive, provenance, verification)
    receipt, report, archive, provenance, verification = _verified_chain(tmp_path / "semantic")
    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["source_archive_name"] = "other.zip"
    receipt.write_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    )
    with pytest.raises(ValueError, match="semantic digest mismatch"):
        verify_admission(receipt, report, archive, provenance, verification)


@pytest.mark.parametrize("member", ["report", "archive", "provenance", "verification"])
def test_verify_admission_rejects_changed_bound_artifacts(tmp_path: Path, member: str) -> None:
    receipt, report, archive, provenance, verification = _verified_chain(tmp_path)
    selected = {
        "report": report, "archive": archive, "provenance": provenance,
        "verification": verification,
    }[member]
    if member == "archive":
        selected.write_bytes(selected.read_bytes() + b"tampered")
    else:
        value = json.loads(selected.read_text(encoding="utf-8"))
        if member == "report":
            value["input_digest"] = "c" * 64
        elif member == "provenance":
            value["platform"] = "changed-platform"
        else:
            value["duration_seconds"] = 2.0
        selected.write_bytes(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        )
    with pytest.raises(ValueError):
        verify_admission(receipt, report, archive, provenance, verification)


def test_verify_admission_rejects_path_reuse(tmp_path: Path) -> None:
    receipt, report, archive, provenance, _ = _verified_chain(tmp_path)
    with pytest.raises(ValueError, match="must be distinct"):
        verify_admission(receipt, report, archive, provenance, report)


def test_verify_admission_cli_reports_verified(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt, report, archive, provenance, verification = _verified_chain(tmp_path)
    assert acceptance_main([
        "verify-admission", "--receipt", str(receipt), "--report", str(report),
        "--archive", str(archive), "--provenance", str(provenance),
        "--verification", str(verification),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "VERIFIED"
