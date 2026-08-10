"""Bounded, query-only access to completed Rootwise inventories."""

from __future__ import annotations

import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

INVENTORY_APPLICATION_ID = 1_346_654_806


class InventoryReadError(RuntimeError):
    """The supplied inventory is incompatible or not safe to present as a snapshot."""


@dataclass(frozen=True)
class SessionSummary:
    scan_session_id: str
    state: str
    source_root: str
    started_at: str
    finished_at: str | None
    observed_count: int
    error_count: int


@dataclass(frozen=True)
class InventoryItem:
    kind: str
    relative_path: str
    parent_path: str | None
    name: str
    extension: str
    logical_bytes: int
    modified_ns: int | None
    depth: int
    display_path: str
    observation_status: str


class InventoryReader:
    """Open one scanner database read-only and expose fixed, parameterized queries."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=True)
        if not self.path.is_file():
            raise InventoryReadError(f"inventory is not a file: {self.path}")
        self._connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA query_only=ON")
            self._validate()
        except BaseException:
            self._connection.close()
            raise

    @property
    def query_only(self) -> bool:
        return bool(self._connection.execute("PRAGMA query_only").fetchone()[0])

    def _validate(self) -> None:
        application_id = self._connection.execute("PRAGMA application_id").fetchone()[0]
        if application_id != INVENTORY_APPLICATION_ID:
            raise InventoryReadError("inventory database application identity mismatch")
        required = {"scan_sessions", "files", "directories", "volumes"}
        present = {
            str(row[0])
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?,?,?,?)",
                tuple(sorted(required)),
            )
        }
        if present != required:
            raise InventoryReadError("inventory database schema is incomplete")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "InventoryReader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def sessions(self) -> list[SessionSummary]:
        rows = self._connection.execute(
            "SELECT scan_session_id,state,source_root,started_at,finished_at,"
            "observed_count,error_count FROM scan_sessions ORDER BY started_at,scan_session_id"
        )
        return [SessionSummary(**dict(row)) for row in rows]

    def latest_complete_session(self) -> str:
        row = self._connection.execute(
            "SELECT scan_session_id FROM scan_sessions WHERE state='COMPLETE' "
            "ORDER BY finished_at DESC,started_at DESC,scan_session_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise InventoryReadError("inventory has no COMPLETE scan session")
        return str(row[0])

    def _require_complete(self, session_id: str) -> None:
        row = self._connection.execute(
            "SELECT state FROM scan_sessions WHERE scan_session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            raise InventoryReadError("scan session does not exist")
        if row[0] != "COMPLETE":
            raise InventoryReadError("viewer search requires a COMPLETE scan session")

    def search(
        self,
        session_id: str,
        query: str = "",
        *,
        kind: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[InventoryItem]:
        if isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        if isinstance(offset, bool) or offset < 0:
            raise ValueError("offset must be nonnegative")
        if kind not in {None, "file", "directory"}:
            raise ValueError("kind must be file, directory, or omitted")
        self._require_complete(session_id)
        normalized = unicodedata.normalize("NFC", query.strip())
        escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        rows = self._connection.execute(
            "WITH items AS ("
            "SELECT scan_session_id,'directory' AS kind,relative_path,comparison_path,parent_path,"
            "name,'' AS extension,logical_bytes,modified_ns,depth,display_path,observation_status "
            "FROM directories UNION ALL "
            "SELECT scan_session_id,'file' AS kind,relative_path,comparison_path,parent_path,"
            "name,extension,logical_bytes,modified_ns,depth,display_path,observation_status FROM files"
            ") SELECT kind,relative_path,parent_path,name,extension,logical_bytes,modified_ns,depth,"
            "display_path,observation_status FROM items WHERE scan_session_id=? "
            "AND comparison_path LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "AND (? IS NULL OR kind=?) "
            "ORDER BY comparison_path COLLATE NOCASE,kind,relative_path COLLATE BINARY LIMIT ? OFFSET ?",
            (session_id, pattern, kind, kind, limit, offset),
        )
        return [InventoryItem(**dict(row)) for row in rows]

    def item(self, session_id: str, relative_path: str) -> InventoryItem | None:
        self._require_complete(session_id)
        row = self._connection.execute(
            "SELECT 'directory' AS kind,relative_path,parent_path,name,'' AS extension,logical_bytes,"
            "modified_ns,depth,display_path,observation_status FROM directories "
            "WHERE scan_session_id=? AND relative_path=? UNION ALL "
            "SELECT 'file' AS kind,relative_path,parent_path,name,extension,logical_bytes,modified_ns,"
            "depth,display_path,observation_status FROM files "
            "WHERE scan_session_id=? AND relative_path=? LIMIT 1",
            (session_id, relative_path, session_id, relative_path),
        ).fetchone()
        return None if row is None else InventoryItem(**dict(row))
