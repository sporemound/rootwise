from __future__ import annotations

from pathlib import Path


CAPABILITY_CLASSES = {
    "METADATA_ONLY",
    "DECISIONS_ONLY",
    "PERMISSIONED_CONTENT_READ",
    "PROHIBITED_EXECUTION",
}


def test_stage_024_product_contract_is_complete_and_explicit() -> None:
    root = Path(__file__).parents[1]
    documents = {
        name: (root / "docs" / name).read_text(encoding="utf-8")
        for name in (
            "PRODUCT_EXPERIENCE.md",
            "VIEW_MODES.md",
            "KEYBOARD_AND_NAVIGATION.md",
            "ACCESSIBILITY.md",
        )
    }
    combined = "\n".join(documents.values())
    for capability in CAPABILITY_CLASSES:
        assert capability in combined
    for feature in (
        "Details view",
        "Compact list view",
        "Tile view",
        "Breadcrumb",
        "Back",
        "Forward",
        "Up",
        "Sorting",
        "Column selection",
        "Persistent settings",
        "File-type icons",
        "Context menu",
        "Saved searches",
        "Bookmarks",
        "Empty state",
        "Loading state",
        "Error state",
        "High-DPI",
    ):
        assert feature in combined
    product = documents["PRODUCT_EXPERIENCE.md"]
    assert product.count("USER APPROVED") == 5
    assert "PENDING USER APPROVAL" not in product
    assert "Smallest Stage 0.25 slice" in documents["VIEW_MODES.md"]
    assert "No source path is opened" in combined
