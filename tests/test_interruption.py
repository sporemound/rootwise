from __future__ import annotations

from pathlib import Path

from paretodrive.database import InventoryDatabase
from paretodrive.models import ScanConfig, SessionState
from paretodrive.scanner import MetadataScanner

from .helpers import RecordingGuard, actual_volume, make_corpus


def test_stop_after_marks_partial_session_stopped(tmp_path: Path) -> None:
    source = make_corpus(tmp_path / "source")
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database_path), 100_000, 2, 0, stop_after=3)
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        session, state = MetadataScanner(source, actual_volume(source), database, config).run()
        assert state is SessionState.STOPPED
        row = database.connection.execute(
            "SELECT state FROM scan_sessions WHERE scan_session_id=?", (session,)
        ).fetchone()
        assert row[0] == "STOPPED"
        assert database.connection.execute(
            "SELECT COUNT(*) FROM scan_frontier WHERE scan_session_id=? AND state!='DONE'", (session,)
        ).fetchone()[0] > 0
