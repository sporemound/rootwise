from __future__ import annotations

from pathlib import Path

import pytest

from rootwise.database import InventoryDatabase
from rootwise.models import ScanConfig
from rootwise.scanner import MetadataScanner

from .helpers import RecordingGuard, actual_volume


def test_fatal_scanner_error_is_structured_and_session_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database_path), 100_000, 2, 0)
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        scanner = MetadataScanner(source, actual_volume(source), database, config)

        def fail(*_args: object) -> None:
            raise OSError(5, "synthetic scanner failure")

        monkeypatch.setattr(scanner, "_scan_directory", fail)
        with pytest.raises(OSError, match="synthetic scanner failure"):
            scanner.run()
        state = database.connection.execute("SELECT state FROM scan_sessions").fetchone()[0]
        error = database.connection.execute(
            "SELECT operation,error_type,error_code,message FROM scan_errors"
        ).fetchone()
        assert state == "FAILED"
        assert tuple(error) == ("scanner", "OSError", 5, "[Errno 5] synthetic scanner failure")
