from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from paretodrive.database import InventoryDatabase
from paretodrive.models import ScanConfig
from paretodrive.scanner import MetadataScanner
from paretodrive_view.inventory import InventoryReadError, InventoryReader

from .helpers import RecordingGuard, actual_volume, make_corpus


def completed_inventory(tmp_path: Path) -> tuple[Path, str]:
    source = make_corpus(tmp_path / "source")
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database_path), 100_000, 4, 0)
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        session, _ = MetadataScanner(source, actual_volume(source), database, config).run()
    return database_path, session


def test_search_is_bounded_parameterized_and_inventory_remains_unchanged(tmp_path: Path) -> None:
    database_path, session = completed_inventory(tmp_path)
    before = hashlib.sha256(database_path.read_bytes()).hexdigest()
    with InventoryReader(database_path) as reader:
        assert reader.query_only
        results = reader.search(session, "final exports", limit=20)
        assert {item.name for item in results} >= {"render.wav", "other.wav"}
        assert reader.search(session, "%", limit=20) == []
        with pytest.raises(ValueError, match="between 1 and 500"):
            reader.search(session, limit=501)
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == before


def test_viewer_rejects_incomplete_session_and_foreign_database(tmp_path: Path) -> None:
    database_path, session = completed_inventory(tmp_path)
    connection = sqlite3.connect(database_path)
    connection.execute("UPDATE scan_sessions SET state='STOPPED' WHERE scan_session_id=?", (session,))
    connection.commit()
    connection.close()
    with InventoryReader(database_path) as reader:
        with pytest.raises(InventoryReadError, match="COMPLETE"):
            reader.search(session)

    foreign = tmp_path / "foreign.db"
    sqlite3.connect(foreign).close()
    with pytest.raises(InventoryReadError, match="application identity"):
        InventoryReader(foreign)


def test_sessions_and_exact_item_lookup(tmp_path: Path) -> None:
    database_path, session = completed_inventory(tmp_path)
    with InventoryReader(database_path) as reader:
        summaries = reader.sessions()
        assert summaries[-1].scan_session_id == session
        assert summaries[-1].state == "COMPLETE"
        item = reader.item(session, "project/src/main.py")
        assert item is not None
        assert item.kind == "file"
        assert item.extension == ".py"
        assert reader.item(session, "missing") is None
