from __future__ import annotations

from pathlib import Path

from rootwise.database import InventoryDatabase
from rootwise.models import ScanConfig, SessionState
from rootwise.scanner import MetadataScanner
from rootwise.errors import ScanStateError
import pytest

from .helpers import RecordingGuard, actual_volume, make_corpus


def test_resume_reuses_session_and_finishes_without_duplicate_rows(tmp_path: Path) -> None:
    source = make_corpus(tmp_path / "source")
    database_path = tmp_path / "inventory.db"
    stopped = ScanConfig(str(source), str(database_path), 100_000, 2, 0, stop_after=4)
    complete = ScanConfig(str(source), str(database_path), 100_000, 3, 0)
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        first_session, first_state = MetadataScanner(
            source, actual_volume(source), database, stopped
        ).run()
        assert first_state is SessionState.STOPPED
        second_session, second_state = MetadataScanner(
            source, actual_volume(source), database, complete
        ).run(resume=True)
        assert second_session == first_session
        assert second_state is SessionState.COMPLETE
        count = database.connection.execute(
            "SELECT observed_count FROM scan_sessions WHERE scan_session_id=?", (first_session,)
        ).fetchone()[0]
        actual = database.connection.execute(
            "SELECT (SELECT COUNT(*) FROM files WHERE scan_session_id=?)+"
            "(SELECT COUNT(*) FROM directories WHERE scan_session_id=?)",
            (first_session, first_session),
        ).fetchone()[0]
        assert count == actual


def test_resume_rejects_different_root_on_same_volume(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "one.txt").touch()
    (second / "two.txt").touch()
    database_path = tmp_path / "inventory.db"
    stopped = ScanConfig(str(first), str(database_path), 100_000, 1, 0, stop_after=1)
    resume_config = ScanConfig(str(second), str(database_path), 100_000, 1, 0)
    volume = actual_volume(first)
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        session, state = MetadataScanner(first, volume, database, stopped).run()
        assert state is SessionState.STOPPED
        with pytest.raises(ScanStateError, match="no resumable"):
            MetadataScanner(second, volume, database, resume_config).run(resume=True)
        assert database.connection.execute(
            "SELECT state FROM scan_sessions WHERE scan_session_id=?", (session,)
        ).fetchone()[0] == "STOPPED"


def test_resume_rejects_database_application_identity_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database_path))
    volume = actual_volume(source)
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        session = database.start_session(volume, config)
        database.finish(session, SessionState.STOPPED)
        database.connection.execute("PRAGMA application_id=0")
        with pytest.raises(ScanStateError, match="application identity"):
            database.resume_session(volume, str(source.resolve()))
