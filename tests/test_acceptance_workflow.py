from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rootwise_acceptance.cli import main as acceptance_main
from rootwise_acceptance.evaluator import REQUIRED_GATES, evaluate_acceptance
from rootwise_acceptance.workflow import gate_guide, initialize_manifest, inspect_report

from .test_acceptance_evaluator import _manifest, _write


def _recanonicalize_report(path: Path, value: dict[str, object]) -> None:
    body = dict(value)
    body.pop("output_digest", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    value["output_digest"] = hashlib.sha256(encoded).hexdigest()
    _write(path, value)


def test_manifest_initialization_is_canonical_empty_and_deterministic(tmp_path: Path) -> None:
    arguments = {
        "subject_revision": "b" * 40,
        "producer": "manual-acceptance-review",
        "created_at": "2026-08-09T00:00:00Z",
        "host_id": "review-host",
        "os_name": "Windows 10",
        "python_version": "3.14.3",
    }
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first_result = initialize_manifest(first, **arguments)
    second_result = initialize_manifest(second, **arguments)
    assert first.read_bytes() == second.read_bytes()
    assert first_result.manifest_digest == second_result.manifest_digest
    assert first_result.required_gate_count == len(REQUIRED_GATES)
    value = json.loads(first.read_text(encoding="utf-8"))
    assert value["gates"] == []
    assert evaluate_acceptance(first, tmp_path / "report.json").status == "INCOMPLETE"
    with pytest.raises(ValueError, match="new file"):
        initialize_manifest(first, **arguments)


def test_guide_lists_every_gate_and_required_measurement() -> None:
    guide = gate_guide()
    assert [gate["gate_id"] for gate in guide["gates"]] == sorted(REQUIRED_GATES)
    assert all(gate["required_measurements"] for gate in guide["gates"])
    viewer = next(gate for gate in guide["gates"] if gate["gate_id"] == "viewer_search_scale")
    assert {"query_only", "query_count", "p95_query_seconds"} <= set(
        viewer["required_measurements"]
    )


def test_report_inspection_accepts_pass_and_prior_code_version(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write(manifest, _manifest())
    report = tmp_path / "report.json"
    evaluate_acceptance(manifest, report)
    inspection = inspect_report(report)
    assert inspection.status == "PASS"
    assert inspection.passed_gate_count == len(REQUIRED_GATES)
    value = json.loads(report.read_text(encoding="utf-8"))
    value["code_version"] = "0.16.0-alpha"
    _recanonicalize_report(report, value)
    assert inspect_report(report).status == "PASS"


def test_report_inspection_rejects_digest_and_semantic_tampering(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write(manifest, _manifest())
    report = tmp_path / "report.json"
    evaluate_acceptance(manifest, report)
    value = json.loads(report.read_text(encoding="utf-8"))
    value["environment"]["host_id"] = "tampered-host"
    _write(report, value)
    with pytest.raises(ValueError, match="output digest mismatch"):
        inspect_report(report)
    evaluate_acceptance(manifest, tmp_path / "fresh.json")
    fresh = tmp_path / "fresh.json"
    value = json.loads(fresh.read_text(encoding="utf-8"))
    value["gates"][0]["status"] = "FAIL"
    _recanonicalize_report(fresh, value)
    with pytest.raises(ValueError, match="reasons do not match"):
        inspect_report(fresh)


def test_workflow_subcommands_and_legacy_evaluation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    initialized = tmp_path / "initialized.json"
    assert acceptance_main([
        "init", "--output", str(initialized), "--subject-revision", "c" * 40,
        "--producer", "cli-test", "--created-at", "2026-08-09T00:00:00Z",
        "--host-id", "cli-host", "--os", "Windows", "--python", "3.14.3",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["required_gate_count"] == len(REQUIRED_GATES)
    report = tmp_path / "report.json"
    assert acceptance_main([
        "evaluate", "--manifest", str(initialized), "--report", str(report)
    ]) == 2
    capsys.readouterr()
    assert acceptance_main(["inspect", "--report", str(report)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "INCOMPLETE"
    assert acceptance_main(["guide"]) == 0
    assert len(json.loads(capsys.readouterr().out)["gates"]) == len(REQUIRED_GATES)
    complete = tmp_path / "complete.json"
    _write(complete, _manifest())
    legacy_report = tmp_path / "legacy-report.json"
    assert acceptance_main([
        "--manifest", str(complete), "--report", str(legacy_report)
    ]) == 0
