from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from paretodrive.database import InventoryDatabase
from paretodrive.models import ScanConfig, SessionState

from .helpers import RecordingGuard, fake_volume


def test_abrupt_process_exit_rolls_back_partial_transaction(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database_path))
    volume = fake_volume()
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        session = database.start_session(volume, config)

    environment = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC")
        if key in os.environ
    }
    environment.update({"PYTHONHASHSEED": "0", "TZ": "UTC", "PYTHONUTF8": "1"})
    completed = subprocess.run(
        [sys.executable, "-m", "tests.helpers_crash_worker", str(database_path), session],
        cwd=Path(__file__).parents[1], env=environment, capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert completed.returncode == 17
    assert completed.stdout == "CRASH_TRANSACTION_READY\n"
    assert completed.stderr == ""
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        assert database.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert database.connection.execute(
            "SELECT COUNT(*) FROM scan_errors WHERE operation='crash_probe'"
        ).fetchone()[0] == 0
        assert database.resume_session(volume, str(source.resolve())) == session
        assert database.connection.execute(
            "SELECT event_type FROM scan_events WHERE scan_session_id=? ORDER BY event_id DESC LIMIT 1",
            (session,),
        ).fetchone()[0] == "RECOVERED_AFTER_CRASH"
        database.finish(session, SessionState.STOPPED)
