from __future__ import annotations

from pathlib import Path

from rootwise.database import InventoryDatabase
from rootwise.models import ScanConfig
from rootwise.scanner import MetadataScanner

from .helpers import RecordingGuard, actual_volume


class MeasuringDatabase(InventoryDatabase):
    maximum_batch = 0

    def commit_directory(self, session_id, relative_path, observations, child_directories, errors, *, done=True):
        observations = list(observations)
        errors = list(errors)
        self.maximum_batch = max(self.maximum_batch, len(observations) + len(errors))
        return super().commit_directory(
            session_id, relative_path, observations, child_directories, errors, done=done
        )


def test_database_batches_remain_bounded_as_file_count_grows(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for index in range(2000):
        (source / f"item-{index:04}.txt").touch()
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database_path), 1_000_000, 17, 0)
    with MeasuringDatabase(database_path, RecordingGuard(tmp_path)) as database:
        MetadataScanner(source, actual_volume(source), database, config).run()
        assert database.maximum_batch <= 17
