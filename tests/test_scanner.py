from __future__ import annotations

from pathlib import Path

from paretodrive.database import InventoryDatabase
from paretodrive.models import ScanConfig, SessionState
from paretodrive.scanner import MetadataScanner

from .helpers import RecordingGuard, actual_volume, make_corpus


def test_metadata_scan_records_fixture_without_following_link(tmp_path: Path) -> None:
    source = make_corpus(tmp_path / "source")
    link = source / "link-outside"
    link_created = False
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
        link_created = True
    except OSError:
        pass
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database_path), 100_000, 3, 0)
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        session, state = MetadataScanner(source, actual_volume(source), database, config).run()
        assert state is SessionState.COMPLETE
        files = database.connection.execute(
            "SELECT COUNT(*) FROM files WHERE scan_session_id=?", (session,)
        ).fetchone()[0]
        assert files == 15 + int(link_created)
        if link_created:
            kind = database.connection.execute(
                "SELECT entry_type FROM files WHERE scan_session_id=? AND name='link-outside'",
                (session,),
            ).fetchone()[0]
            assert kind == "SYMLINK"
        assert database.connection.execute(
            "SELECT COUNT(*) FROM scan_frontier WHERE scan_session_id=? AND state!='DONE'", (session,)
        ).fetchone()[0] == 0


def test_same_size_candidates_are_not_content_classified(tmp_path: Path) -> None:
    source = make_corpus(tmp_path / "source")
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database_path), 100_000, 4, 0)
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        session, _ = MetadataScanner(source, actual_volume(source), database, config).run()
        rows = database.connection.execute(
            "SELECT name,logical_bytes,observation_status FROM files WHERE scan_session_id=? "
            "AND extension='.wav' ORDER BY name", (session,)
        ).fetchall()
        assert [(row[1], row[2]) for row in rows] == [(4, "OBSERVED"), (4, "OBSERVED")]
