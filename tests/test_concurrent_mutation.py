from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest
import rootwise.scanner as scanner_module
from rootwise.database import InventoryDatabase
from rootwise.models import ScanConfig, SessionState
from rootwise.scanner import MetadataScanner

from .helpers import RecordingGuard, actual_volume


class _DeletingEntry:
    def __init__(self, entry: os.DirEntry[str]) -> None:
        self._entry = entry
        self.name = entry.name

    @property
    def path(self) -> str:
        target = Path(self._entry.path)
        if target.is_dir():
            target.rmdir()
        else:
            target.unlink()
        return self._entry.path

    def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
        return self._entry.stat(follow_symlinks=follow_symlinks)

    def is_symlink(self) -> bool:
        return self._entry.is_symlink()


class _DeletingScandir:
    def __init__(self, inner: Any, target: str) -> None:
        self._inner = inner
        self._target = target
        self._iterator: Any = None

    def __enter__(self) -> _DeletingScandir:
        self._iterator = self._inner.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return self._inner.__exit__(exc_type, exc, traceback)

    def __iter__(self) -> _DeletingScandir:
        return self

    def __next__(self) -> os.DirEntry[str] | _DeletingEntry:
        entry = next(self._iterator)
        return _DeletingEntry(entry) if entry.name == self._target else entry


@pytest.mark.parametrize("target_kind", ["file", "directory"])
def test_entry_deleted_after_enumeration_is_error_not_observation(
    tmp_path: Path, monkeypatch: Any, target_kind: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    target = source / f"concurrent-{target_kind}"
    if target_kind == "directory":
        target.mkdir()
    else:
        target.write_bytes(b"delete after enumeration\n")
    stable = source / "stable.bin"
    stable.write_bytes(b"stable\n")
    original_scandir = scanner_module.os.scandir

    def deleting_scandir(path: Any) -> _DeletingScandir:
        return _DeletingScandir(original_scandir(path), target.name)

    monkeypatch.setattr(scanner_module.os, "scandir", deleting_scandir)
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database_path), 100_000, 25, 0)
    with InventoryDatabase(database_path, RecordingGuard(tmp_path)) as database:
        session, state = MetadataScanner(
            source, actual_volume(source), database, config
        ).run()
        observed = {
            str(row[0]) for row in database.connection.execute(
                "SELECT relative_path FROM files WHERE scan_session_id=?", (session,)
            )
        }
        errors = database.connection.execute(
            "SELECT relative_path,operation,error_type,error_code FROM scan_errors "
            "WHERE scan_session_id=?",
            (session,),
        ).fetchall()
    assert state is SessionState.COMPLETE
    assert stable.name in observed
    assert target.name not in observed
    assert [tuple(row) for row in errors] == [
        (target.name, "stat", "FileNotFoundError", 2)
    ]
