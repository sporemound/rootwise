from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.run_scale_acceptance import (
    MINIMUM_SCALE_ENTRIES,
    Budgets,
    _canonical,
    _measurements_pass,
    _output_pair,
    _plan,
    _require_outside,
    _validate_revision,
    run_viewer_scale,
)

from .test_viewer_inventory import completed_inventory


def test_plan_is_nonexecuting_and_names_all_three_scale_gates() -> None:
    revision = "a" * 40
    assert _plan(revision) == {
        "code_version": "0.22.0-alpha",
        "execution_authorized": False,
        "gates": ["scanner_scale", "snapshot_pipeline_scale", "viewer_search_scale"],
        "minimum_entry_count": 1_000_000,
        "requirements": [
            "exact clean subject revision",
            "operator-supplied corpus and budgets",
            "new explicit output paths",
            "--execute for every measured operation",
        ],
        "source_corpus_created": False,
        "subject_revision": revision,
    }


def test_scale_contract_rejects_weak_budgets_revision_mismatch_and_output_reuse(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="1000000"):
        Budgets(60, 64 * 1024 * 1024, 1, 999_999).validate()
    with pytest.raises(ValueError, match="does not match"):
        _validate_revision("a" * 40, current="b" * 40)
    first = tmp_path / "evidence.json"
    second = tmp_path / "measurements.json"
    first.write_text("occupied", encoding="utf-8")
    with pytest.raises(ValueError, match="new files"):
        _output_pair(first, second)
    with pytest.raises(ValueError, match="outside"):
        _require_outside(tmp_path, tmp_path / "inside.json")


def test_viewer_scale_writes_canonical_fail_evidence_for_subscale_inventory(
    tmp_path: Path,
) -> None:
    inventory, _ = completed_inventory(tmp_path)
    queries = tmp_path / "queries.json"
    queries.write_bytes(_canonical(["project", "src", "missing"] * 34))
    evidence = tmp_path / "viewer-evidence.json"
    measurements = tmp_path / "viewer-measurements.json"
    result = run_viewer_scale(
        inventory,
        queries,
        evidence,
        measurements,
        subject_revision="a" * 40,
        budgets=Budgets(60, 512 * 1024 * 1024, 0, MINIMUM_SCALE_ENTRIES),
        maximum_p95_query_seconds=1,
    )
    values = json.loads(measurements.read_bytes())
    assert result["status"] == "FAIL"
    assert values["completed"] is True
    assert values["inputs_unchanged"] is True
    assert values["query_count"] == 102
    assert values["query_only"] is True
    assert values["observed_entry_count"] < MINIMUM_SCALE_ENTRIES
    assert not _measurements_pass(values)
    assert evidence.read_bytes() == _canonical(json.loads(evidence.read_bytes()))
    assert measurements.read_bytes() == _canonical(values)


def test_query_file_must_be_canonical_and_have_at_least_one_hundred_queries(
    tmp_path: Path,
) -> None:
    inventory, _ = completed_inventory(tmp_path)
    queries = tmp_path / "queries.json"
    queries.write_text(json.dumps(["x"] * 99, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical array"):
        run_viewer_scale(
            inventory,
            queries,
            tmp_path / "evidence.json",
            tmp_path / "measurements.json",
            subject_revision="a" * 40,
            budgets=Budgets(60, 512 * 1024 * 1024, 0),
            maximum_p95_query_seconds=1,
        )
