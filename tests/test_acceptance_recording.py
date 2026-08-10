from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rootwise_acceptance.cli import main as acceptance_main
from rootwise_acceptance.evaluator import evaluate_acceptance
from rootwise_acceptance.recording import record_gate

from .test_acceptance_evaluator import _manifest, _write


def _files(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest = tmp_path / "manifest.json"
    _write(manifest, _manifest([]))
    evidence = tmp_path / "gui-evidence.json"
    evidence.write_bytes(b'{"confirmed":true}\n')
    measurements = tmp_path / "gui-measurements.json"
    _write(measurements, {
        "no_critical_defects": True,
        "review_completed": True,
        "visible_session": True,
    })
    return manifest, evidence, measurements


def test_record_gate_hashes_evidence_and_writes_new_canonical_revision(tmp_path: Path) -> None:
    manifest, evidence, measurements = _files(tmp_path)
    before = {path: path.read_bytes() for path in (manifest, evidence, measurements)}
    output = tmp_path / "with-gui.json"
    result = record_gate(
        manifest, evidence, measurements, output,
        gate_id="visible_gui_review", notes="Confirmed visible synthetic GUI review.",
    )
    assert result.gate_status == "PASS"
    assert result.recorded_gate_count == 1
    assert result.evidence_sha256 == hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert before == {path: path.read_bytes() for path in (manifest, evidence, measurements)}
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["gates"][0]["evidence_sha256"] == result.evidence_sha256
    report_result = evaluate_acceptance(output, tmp_path / "report.json")
    assert report_result.status == "INCOMPLETE"
    assert report_result.passed_gate_count == 1
    assert report_result.incomplete_gate_count == 8


def test_record_gate_preserves_failed_evidence_as_failure(tmp_path: Path) -> None:
    manifest, evidence, _ = _files(tmp_path)
    measurements = tmp_path / "corruption-measurements.json"
    _write(measurements, {"corruption_detected": True, "failed_closed": False})
    output = tmp_path / "failed.json"
    result = record_gate(
        manifest, evidence, measurements, output,
        gate_id="database_corruption", notes="Synthetic negative acceptance evidence.",
    )
    assert result.gate_status == "FAIL"
    report = evaluate_acceptance(output, tmp_path / "failed-report.json")
    assert report.status == "FAIL"
    assert report.failed_gate_count == 1


def test_record_gate_rejects_noncanonical_missing_and_extra_measurements(tmp_path: Path) -> None:
    manifest, evidence, measurements = _files(tmp_path)
    measurements.write_text(json.dumps({
        "no_critical_defects": True, "review_completed": True, "visible_session": True,
    }, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="canonical JSON"):
        record_gate(
            manifest, evidence, measurements, tmp_path / "pretty.json",
            gate_id="visible_gui_review", notes="Rejected pretty-printed measurements.",
        )
    _write(measurements, {"review_completed": True, "visible_session": True})
    with pytest.raises(ValueError, match="missing=.*no_critical_defects"):
        record_gate(
            manifest, evidence, measurements, tmp_path / "missing.json",
            gate_id="visible_gui_review", notes="Rejected missing measurement.",
        )
    _write(measurements, {
        "no_critical_defects": True, "review_completed": True, "visible_session": True,
        "invented": True,
    })
    with pytest.raises(ValueError, match="unexpected=.*invented"):
        record_gate(
            manifest, evidence, measurements, tmp_path / "extra.json",
            gate_id="visible_gui_review", notes="Rejected extra measurement.",
        )


def test_record_gate_rejects_duplicate_replacement_and_overwrite(tmp_path: Path) -> None:
    manifest, evidence, measurements = _files(tmp_path)
    first = tmp_path / "first.json"
    record_gate(
        manifest, evidence, measurements, first,
        gate_id="visible_gui_review", notes="First immutable gate revision.",
    )
    with pytest.raises(ValueError, match="replacement is forbidden"):
        record_gate(
            first, evidence, measurements, tmp_path / "replacement.json",
            gate_id="visible_gui_review", notes="Forbidden replacement.",
        )
    existing = tmp_path / "existing.json"
    existing.write_text("occupied", encoding="utf-8")
    with pytest.raises(ValueError, match="new file"):
        record_gate(
            manifest, evidence, measurements, existing,
            gate_id="visible_gui_review", notes="Forbidden overwrite.",
        )
    with pytest.raises(ValueError, match="must be distinct"):
        record_gate(
            manifest, evidence, measurements, manifest,
            gate_id="visible_gui_review", notes="Forbidden path reuse.",
        )


def test_record_cli_reports_computed_gate_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest, evidence, measurements = _files(tmp_path)
    output = tmp_path / "recorded.json"
    assert acceptance_main([
        "record", "--manifest", str(manifest), "--evidence", str(evidence),
        "--measurements", str(measurements), "--output", str(output),
        "--gate", "visible_gui_review", "--notes", "Confirmed by CLI test.",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["gate_status"] == "PASS"
    assert result["recorded_gate_count"] == 1
