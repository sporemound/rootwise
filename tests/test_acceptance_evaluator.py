from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rootwise_acceptance.cli import main as acceptance_main
from rootwise_acceptance.evaluator import REQUIRED_GATES, evaluate_acceptance


def _scale() -> dict[str, object]:
    return {
        "completed": True,
        "duration_seconds": 10.0,
        "inputs_unchanged": True,
        "maximum_duration_seconds": 60.0,
        "maximum_peak_rss_bytes": 2_000_000_000,
        "maximum_temporary_bytes": 10_000_000_000,
        "minimum_entry_count": 1_000_000,
        "observed_entry_count": 1_000_000,
        "peak_rss_bytes": 1_000_000_000,
        "temporary_bytes": 5_000_000_000,
    }


def _measurements(gate_id: str) -> dict[str, object]:
    if gate_id in {"scanner_scale", "snapshot_pipeline_scale"}:
        return _scale()
    if gate_id == "viewer_search_scale":
        return {
            **_scale(), "query_count": 100, "p95_query_seconds": 0.5,
            "maximum_p95_query_seconds": 2.0, "query_only": True,
        }
    fields = {
        "enrichment_distinct_volume": (
            "completed", "distinct_os_volumes", "selection_immutable",
            "source_contents_unchanged", "access_time_risk_acknowledged",
        ),
        "forced_interruption_recovery": (
            "interruption_observed", "stopped_state_recorded", "resume_completed",
            "source_contents_unchanged",
        ),
        "database_corruption": ("corruption_detected", "failed_closed"),
        "metadata_edge_cases": (
            "long_paths_tested", "invalid_metadata_tested", "permission_errors_tested",
            "concurrent_mutation_tested", "failed_closed",
        ),
        "visible_gui_review": ("visible_session", "review_completed", "no_critical_defects"),
        "independent_replication": (
            "independent_host", "fresh_clone", "revision_matched", "mandatory_tests_passed",
            "source_contents_unchanged",
        ),
    }
    return {name: True for name in fields[gate_id]}


def _manifest(gates: list[str] | None = None) -> dict[str, object]:
    selected = sorted(REQUIRED_GATES if gates is None else gates)
    return {
        "schema": "rootwise-acceptance-evidence-v1",
        "subject_revision": "a" * 40,
        "producer": "synthetic-stage-0.16-test",
        "created_at": "2026-08-09T00:00:00Z",
        "environment": {"host_id": "fixture-host", "os": "Windows", "python": "3.12"},
        "gates": [{
            "gate_id": gate_id,
            "evidence_sha256": hashlib.sha256(gate_id.encode()).hexdigest(),
            "measurements": _measurements(gate_id),
            "notes": "Synthetic evidence for evaluator behavior only.",
        } for gate_id in selected],
    }


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n",
    )


def test_complete_acceptance_manifest_passes_deterministically(tmp_path: Path) -> None:
    manifest = tmp_path / "acceptance.json"
    _write(manifest, _manifest())
    first = tmp_path / "report-one.json"
    second = tmp_path / "report-two.json"
    first_result = evaluate_acceptance(manifest, first)
    second_result = evaluate_acceptance(manifest, second)
    assert first_result.status == "PASS"
    assert first_result.passed_gate_count == len(REQUIRED_GATES)
    assert first_result.output_digest == second_result.output_digest
    assert first.read_bytes() == second.read_bytes()
    report = json.loads(first.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert {gate["status"] for gate in report["gates"]} == {"PASS"}


def test_missing_gate_is_incomplete_and_cli_returns_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "acceptance.json"
    _write(manifest, _manifest(["database_corruption"]))
    report = tmp_path / "report.json"
    assert acceptance_main(["--manifest", str(manifest), "--report", str(report)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "INCOMPLETE"
    assert result["incomplete_gate_count"] == len(REQUIRED_GATES) - 1


def test_failed_budget_cannot_be_self_declared_as_pass(tmp_path: Path) -> None:
    value = _manifest()
    scanner = next(gate for gate in value["gates"] if gate["gate_id"] == "scanner_scale")
    scanner["measurements"]["peak_rss_bytes"] = 3_000_000_000
    manifest = tmp_path / "acceptance.json"
    _write(manifest, value)
    result = evaluate_acceptance(manifest, tmp_path / "report.json")
    assert result.status == "FAIL"
    assert result.failed_gate_count == 1


def test_manifest_rejects_noncanonical_unknown_and_reused_paths(tmp_path: Path) -> None:
    manifest = tmp_path / "acceptance.json"
    value = _manifest()
    manifest.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="canonical JSON"):
        evaluate_acceptance(manifest, tmp_path / "report.json")
    _write(manifest, value)
    value["gates"][0]["gate_id"] = "invented_gate"
    _write(manifest, value)
    with pytest.raises(ValueError, match="unknown acceptance gate"):
        evaluate_acceptance(manifest, tmp_path / "unknown.json")
    _write(manifest, _manifest())
    with pytest.raises(ValueError, match="distinct siblings"):
        evaluate_acceptance(manifest, manifest)
