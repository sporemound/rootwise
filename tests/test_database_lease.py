from __future__ import annotations

from pathlib import Path

import pytest

from paretodrive.database import InventoryDatabase
from paretodrive.errors import ScanStateError

from .helpers import RecordingGuard


def test_second_database_process_boundary_is_exclusively_leased(tmp_path: Path) -> None:
    database_path = tmp_path / "inventory.db"
    first = InventoryDatabase(database_path, RecordingGuard(tmp_path))
    try:
        with pytest.raises(ScanStateError, match="already leased"):
            InventoryDatabase(database_path, RecordingGuard(tmp_path))
    finally:
        first.close()
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)):
        pass
