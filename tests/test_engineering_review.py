from __future__ import annotations

from pathlib import Path


def test_cold_start_review_records_required_questions_controls_and_limits() -> None:
    root = Path(__file__).parents[1]
    review = (root / "docs" / "validation" / "engineering-review.md").read_text(
        encoding="utf-8"
    )
    for question in (
        "What does Rootwise do?",
        "What touches the source filesystem?",
        "Where would you add a Viewer feature?",
        "Where would you add an analytics feature?",
        "Where would you add a Rust scanner?",
        "What seems redundant or unclear?",
    ):
        assert question in review
    for control in (
        "README.md",
        "ARCHITECTURE.md",
        "DEVELOPMENT.md",
        "CHANGELOG.md",
        "docs/archive/",
        "prior conversation",
    ):
        assert control in review
    assert "534a80a2ae3eee956ce1a66f6add00978f548033" in review
    assert "isolated automated cold-start engineering review" in review
    assert "not a human review" in review
    assert "Review duration" in review
    assert "**PASS — A technically experienced reviewer" in review
    assert review.count("\n1. ") >= 2
    assert review.count("\n9. ") == 1


def test_reviewer_discovered_primary_document_inconsistencies_are_corrected() -> None:
    root = Path(__file__).parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    architecture = (root / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "Optimize, approve, and inspect proposals" not in readme
    assert "Optimize, approve, and preflight proposals" in readme
    assert "History Evidence ownership documented" in architecture
    assert "whether multi-snapshot history is Evidence input" not in architecture
