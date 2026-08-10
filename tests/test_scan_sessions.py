from __future__ import annotations

from pathlib import Path

import pytest

from rootwise.database import InventoryDatabase
from rootwise.errors import ScanStateError
from rootwise.models import ScanConfig, SessionState

from .helpers import RecordingGuard, fake_volume


def test_unfinished_frontier_cannot_be_complete(tmp_path: Path) -> None:
    path = tmp_path / "inventory.db"
    source = tmp_path / "source"
    source.mkdir()
    config = ScanConfig(str(source), str(path))
    with InventoryDatabase(path, RecordingGuard(tmp_path)) as database:
        session = database.start_session(fake_volume(), config)
        with pytest.raises(ScanStateError, match="unfinished"):
            database.finish(session, SessionState.COMPLETE)


def test_database_uses_durable_rollback_journal(tmp_path: Path) -> None:
    path = tmp_path / "inventory.db"
    with InventoryDatabase(path, RecordingGuard(tmp_path)) as database:
        assert database.connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert database.connection.execute("PRAGMA synchronous").fetchone()[0] == 2
