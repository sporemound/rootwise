"""Immutable inventory snapshot access for analytics."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

INVENTORY_APPLICATION_ID = 1_346_654_806


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotItem:
    kind: str
    relative_path: str
    parent_path: str | None
    name: str
    extension: str
    logical_bytes: int
    depth: int


class InventorySnapshot:
    def __init__(self, path: str | Path, session_id: str | None = None) -> None:
        self.path = Path(path).expanduser().resolve(strict=True)
        self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA query_only=ON")
            if self.connection.execute("PRAGMA application_id").fetchone()[0] != INVENTORY_APPLICATION_ID:
                raise SnapshotError("inventory application identity mismatch")
            if session_id is None:
                row = self.connection.execute(
                    "SELECT scan_session_id FROM scan_sessions WHERE state='COMPLETE' "
                    "ORDER BY finished_at DESC,scan_session_id DESC LIMIT 1"
                ).fetchone()
            else:
                row = self.connection.execute(
                    "SELECT scan_session_id FROM scan_sessions WHERE scan_session_id=? AND state='COMPLETE'",
                    (session_id,),
                ).fetchone()
            if row is None:
                raise SnapshotError("analytics requires a COMPLETE inventory session")
            self.session_id = str(row[0])
        except BaseException:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "InventorySnapshot":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def items(self) -> Iterator[SnapshotItem]:
        rows = self.connection.execute(
            "SELECT kind,relative_path,parent_path,name,extension,logical_bytes,depth FROM ("
            "SELECT 'directory' kind,relative_path,parent_path,name,'' extension,logical_bytes,depth "
            "FROM directories WHERE scan_session_id=? UNION ALL "
            "SELECT 'file' kind,relative_path,parent_path,name,extension,logical_bytes,depth "
            "FROM files WHERE scan_session_id=?) ORDER BY relative_path COLLATE BINARY,kind",
            (self.session_id, self.session_id),
        )
        for row in rows:
            yield SnapshotItem(**dict(row))

    def logical_digest(self) -> str:
        digest = hashlib.sha256()
        for item in self.items():
            payload = json.dumps(item.__dict__, sort_keys=True, separators=(",", ":"))
            digest.update(payload.encode("utf-8") + b"\n")
        return digest.hexdigest()
