from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rootwise.viewer.decisions import (
    DecisionConflictError,
    DecisionStore,
)


def inventory_file(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA application_id=1346654806")
    connection.close()
    return path


def test_decisions_are_separate_revisioned_and_append_audited(tmp_path: Path) -> None:
    inventory = inventory_file(tmp_path / "inventory.db")
    decisions = tmp_path / "decisions.db"
    with DecisionStore(decisions, inventory_path=inventory) as store:
        first = store.set_decision("session-1", "project", "PROTECT", note="original")
        assert first.revision == 1
        assert store.current("session-1", "project") == first
        assert store.current_for_paths("session-1", ["project", "missing"]) == {
            "project": first
        }
        with pytest.raises(DecisionConflictError, match="expected revision"):
            store.set_decision("session-1", "project", "KEEP")
        second = store.set_decision(
            "session-1", "project", "KEEP", note="reviewed", expected_revision=1
        )
        assert second.revision == 2
        assert [entry.revision for entry in store.history("session-1", "project")] == [1, 2]


def test_decision_store_rejects_inventory_path_invalid_values_and_stale_updates(
    tmp_path: Path,
) -> None:
    inventory = inventory_file(tmp_path / "inventory.db")
    with pytest.raises(ValueError, match="distinct"):
        DecisionStore(inventory, inventory_path=inventory)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    with pytest.raises(ValueError, match="external directory"):
        DecisionStore(elsewhere / "decisions.db", inventory_path=inventory)
    with DecisionStore(tmp_path / "decisions.db", inventory_path=inventory) as store:
        with pytest.raises(ValueError, match="unsupported decision"):
            store.set_decision("session-1", "project", "DELETE")
        with pytest.raises(ValueError, match="relative"):
            store.set_decision("session-1", "../escape", "KEEP")
        store.set_decision("session-1", "project", "KEEP")
        with pytest.raises(DecisionConflictError, match="expected revision 1"):
            store.set_decision(
                "session-1", "project", "PROTECT", expected_revision=0
            )
