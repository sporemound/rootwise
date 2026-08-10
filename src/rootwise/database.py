"""External SQLite inventory and persisted scan frontier."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .errors import ScanStateError
from .models import Observation, ScanConfig, SessionState, VolumeInfo
from .write_guard import WriteGuard


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA application_id = 1346654806;
CREATE TABLE IF NOT EXISTS volumes (
  volume_id INTEGER PRIMARY KEY,
  identity TEXT NOT NULL UNIQUE,
  mount_path TEXT NOT NULL,
  filesystem_type TEXT,
  device TEXT
);
CREATE TABLE IF NOT EXISTS scan_sessions (
  scan_session_id TEXT PRIMARY KEY,
  volume_id INTEGER NOT NULL REFERENCES volumes(volume_id),
  state TEXT NOT NULL CHECK(state IN ('RUNNING','COMPLETE','STOPPED','FAILED')),
  source_root TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  configuration_json TEXT NOT NULL,
  observed_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS directories (
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  relative_path TEXT NOT NULL,
  comparison_path TEXT NOT NULL,
  parent_path TEXT,
  name TEXT NOT NULL,
  entry_type TEXT NOT NULL,
  logical_bytes INTEGER NOT NULL,
  created_ns INTEGER,
  modified_ns INTEGER,
  accessed_ns INTEGER,
  attributes INTEGER NOT NULL,
  depth INTEGER NOT NULL,
  display_path TEXT NOT NULL,
  observation_status TEXT NOT NULL,
  PRIMARY KEY(scan_session_id, relative_path)
);
CREATE TABLE IF NOT EXISTS files (
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  relative_path TEXT NOT NULL,
  comparison_path TEXT NOT NULL,
  parent_path TEXT,
  name TEXT NOT NULL,
  extension TEXT NOT NULL,
  entry_type TEXT NOT NULL,
  logical_bytes INTEGER NOT NULL,
  created_ns INTEGER,
  modified_ns INTEGER,
  accessed_ns INTEGER,
  attributes INTEGER NOT NULL,
  depth INTEGER NOT NULL,
  display_path TEXT NOT NULL,
  observation_status TEXT NOT NULL,
  PRIMARY KEY(scan_session_id, relative_path)
);
CREATE TABLE IF NOT EXISTS scan_errors (
  error_id INTEGER PRIMARY KEY,
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  relative_path TEXT NOT NULL,
  operation TEXT NOT NULL,
  error_type TEXT NOT NULL,
  error_code INTEGER,
  message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_frontier (
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  relative_path TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('PENDING','SCANNING','DONE')),
  PRIMARY KEY(scan_session_id, relative_path)
);
CREATE INDEX IF NOT EXISTS frontier_next ON scan_frontier(scan_session_id, state, relative_path);
CREATE TABLE IF NOT EXISTS scan_events (
  event_id INTEGER PRIMARY KEY,
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  event_type TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canonical_exports (
  export_id INTEGER PRIMARY KEY,
  scan_session_id TEXT NOT NULL REFERENCES scan_sessions(scan_session_id),
  output_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  completed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS application_writes (
  write_id INTEGER PRIMARY KEY,
  scan_session_id TEXT,
  path TEXT NOT NULL,
  purpose TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class InventoryDatabase:
    def __init__(self, path: str | Path, guard: WriteGuard) -> None:
        self.path = guard.authorize(path)
        self.journal_path = guard.authorize_sqlite_journal(self.path)
        self.lease_stream = guard.open_database_lease(self.path)
        self._acquire_lease()
        try:
            self.connection = sqlite3.connect(self.path, timeout=30.0)
            guard.verify_existing(self.path)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA journal_mode = DELETE")
            self.connection.execute("PRAGMA synchronous = FULL")
            self.connection.execute("PRAGMA temp_store = MEMORY")
            self.connection.executescript(SCHEMA)
            self.connection.execute(
                "INSERT INTO application_writes(scan_session_id,path,purpose,recorded_at) VALUES(NULL,?,?,?)",
                (str(self.path), "inventory_database", utc_now()),
            )
            self.connection.commit()
        except BaseException:
            connection = getattr(self, "connection", None)
            if connection is not None:
                connection.close()
            self._release_lease()
            raise

    def _acquire_lease(self) -> None:
        try:
            self.lease_stream.seek(0)
            if self.lease_stream.read(1) == b"":
                self.lease_stream.seek(0)
                self.lease_stream.write(b"\0")
                self.lease_stream.flush()
            self.lease_stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.lease_stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                getattr(fcntl, "flock")(
                    self.lease_stream.fileno(),
                    getattr(fcntl, "LOCK_EX") | getattr(fcntl, "LOCK_NB"),
                )
        except OSError as exc:
            self.lease_stream.close()
            raise ScanStateError("inventory database is already leased by another process") from exc

    def _release_lease(self) -> None:
        if self.lease_stream.closed:
            return
        try:
            self.lease_stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.lease_stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                getattr(fcntl, "flock")(self.lease_stream.fileno(), getattr(fcntl, "LOCK_UN"))
        finally:
            self.lease_stream.close()

    def close(self) -> None:
        try:
            self.connection.close()
        finally:
            self._release_lease()

    def __enter__(self) -> "InventoryDatabase":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def start_session(self, volume: VolumeInfo, config: ScanConfig) -> str:
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO volumes(identity,mount_path,filesystem_type,device) VALUES(?,?,?,?)",
            (volume.identity, volume.mount_path, volume.filesystem_type, volume.device),
        )
        del cursor
        volume_id = self.connection.execute(
            "SELECT volume_id FROM volumes WHERE identity=?", (volume.identity,)
        ).fetchone()[0]
        session_id = str(uuid4())
        config_json = json.dumps(config.__dict__, sort_keys=True, separators=(",", ":"))
        self.connection.execute(
            "INSERT INTO scan_sessions(scan_session_id,volume_id,state,source_root,started_at,configuration_json) "
            "VALUES(?,?,?,?,?,?)",
            (
                session_id, volume_id, SessionState.RUNNING.value,
                str(Path(config.source).resolve(strict=True)), utc_now(), config_json,
            ),
        )
        self.connection.execute(
            "INSERT INTO scan_frontier(scan_session_id,relative_path,state) VALUES(?,?,?)",
            (session_id, "", "PENDING"),
        )
        self.connection.execute(
            "INSERT INTO scan_events(scan_session_id,event_type,detail_json,recorded_at) "
            "VALUES(?,?,?,?)",
            (session_id, "STARTED", "{}", utc_now()),
        )
        self.connection.commit()
        return session_id

    def resume_session(self, volume: VolumeInfo, source_root: str) -> str:
        self._validate_database_for_resume()
        row = self.connection.execute(
            "SELECT s.scan_session_id,s.state FROM scan_sessions s JOIN volumes v USING(volume_id) "
            "WHERE v.identity=? AND s.source_root=? AND s.state IN ('RUNNING','STOPPED','FAILED') "
            "ORDER BY s.started_at DESC LIMIT 1",
            (volume.identity, source_root),
        ).fetchone()
        if row is None:
            raise ScanStateError("no resumable session exists for source volume")
        session_id = str(row["scan_session_id"])
        previous_state = str(row["state"])
        with self.connection:
            self.connection.execute(
                "UPDATE scan_frontier SET state='PENDING' WHERE scan_session_id=? AND state='SCANNING'",
                (session_id,),
            )
            self.connection.execute(
                "UPDATE scan_sessions SET state='RUNNING',finished_at=NULL WHERE scan_session_id=?",
                (session_id,),
            )
            self.connection.execute(
                "INSERT INTO scan_events(scan_session_id,event_type,detail_json,recorded_at) "
                "VALUES(?,?,?,?)",
                (
                    session_id,
                    "RECOVERED_AFTER_CRASH" if previous_state == "RUNNING" else "RESUMED",
                    "{}",
                    utc_now(),
                ),
            )
        return session_id

    def _validate_database_for_resume(self) -> None:
        if self.connection.execute("PRAGMA application_id").fetchone()[0] != 1_346_654_806:
            raise ScanStateError("database application identity mismatch before resume")
        if self.connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ScanStateError("SQLite integrity check failed before resume")
        if self.connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ScanStateError("SQLite foreign-key check failed before resume")

    def next_directory(self, session_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT relative_path FROM scan_frontier WHERE scan_session_id=? AND state='PENDING' "
            "ORDER BY relative_path LIMIT 1",
            (session_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    def commit_directory(
        self,
        session_id: str,
        relative_path: str,
        observations: Iterable[Observation],
        child_directories: Iterable[str],
        errors: Iterable[tuple[str, str, str, int | None, str]],
        *,
        done: bool = True,
    ) -> int:
        rows = list(observations)
        error_rows = list(errors)
        with self.connection:
            self.connection.execute(
                "UPDATE scan_frontier SET state='SCANNING' WHERE scan_session_id=? AND relative_path=?",
                (session_id, relative_path),
            )
            for item in rows:
                table = "directories" if item.entry_type in {"DIRECTORY", "SYMLINK_DIRECTORY"} else "files"
                common = (
                    session_id, item.relative_path, item.comparison_path, item.parent_path,
                    item.name, item.entry_type,
                    item.logical_bytes, item.created_ns, item.modified_ns, item.accessed_ns,
                    item.attributes, item.depth, item.display_path, item.observation_status,
                )
                if table == "directories":
                    self.connection.execute(
                        "INSERT OR REPLACE INTO directories VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", common
                    )
                else:
                    self.connection.execute(
                        "INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        common[:5] + (item.extension,) + common[5:],
                    )
            self.connection.executemany(
                "INSERT OR IGNORE INTO scan_frontier(scan_session_id,relative_path,state) VALUES(?,?,'PENDING')",
                ((session_id, path) for path in child_directories),
            )
            self.connection.executemany(
                "INSERT INTO scan_errors(scan_session_id,relative_path,operation,error_type,error_code,message) "
                "VALUES(?,?,?,?,?,?)",
                ((session_id,) + row for row in error_rows),
            )
            if done:
                self.connection.execute(
                    "UPDATE scan_frontier SET state='DONE' WHERE scan_session_id=? AND relative_path=?",
                    (session_id, relative_path),
                )
            self.connection.execute(
                "UPDATE scan_sessions SET observed_count=observed_count+?,error_count=error_count+? "
                "WHERE scan_session_id=?",
                (len(rows), len(error_rows), session_id),
            )
        return len(rows)

    def finish(self, session_id: str, state: SessionState) -> None:
        current = self.connection.execute(
            "SELECT state FROM scan_sessions WHERE scan_session_id=?", (session_id,)
        ).fetchone()
        if current is None or current[0] != SessionState.RUNNING.value:
            raise ScanStateError("only a RUNNING session can finish")
        if state is SessionState.COMPLETE:
            pending = self.connection.execute(
                "SELECT COUNT(*) FROM scan_frontier WHERE scan_session_id=? AND state!='DONE'",
                (session_id,),
            ).fetchone()[0]
            if pending:
                raise ScanStateError("a session with unfinished frontier work cannot be COMPLETE")
        with self.connection:
            self.connection.execute(
                "UPDATE scan_sessions SET state=?,finished_at=?,"
                "observed_count=(SELECT COUNT(*) FROM files WHERE scan_session_id=?)+"
                "(SELECT COUNT(*) FROM directories WHERE scan_session_id=?),"
                "error_count=(SELECT COUNT(*) FROM scan_errors WHERE scan_session_id=?) "
                "WHERE scan_session_id=?",
                (state.value, utc_now(), session_id, session_id, session_id, session_id),
            )
            self.connection.execute(
                "INSERT INTO scan_events(scan_session_id,event_type,detail_json,recorded_at) "
                "VALUES(?,?,?,?)",
                (session_id, state.value, "{}", utc_now()),
            )

    def record_write(self, session_id: str | None, path: Path, purpose: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO application_writes(scan_session_id,path,purpose,recorded_at) VALUES(?,?,?,?)",
                (session_id, str(path), purpose, utc_now()),
            )

    def record_error(
        self,
        session_id: str,
        relative_path: str,
        operation: str,
        error_type: str,
        error_code: int | None,
        message: str,
    ) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO scan_errors(scan_session_id,relative_path,operation,error_type,error_code,message) "
                "VALUES(?,?,?,?,?,?)",
                (session_id, relative_path, operation, error_type, error_code, message),
            )

    def record_event(self, session_id: str, event_type: str, detail: dict[str, object]) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO scan_events(scan_session_id,event_type,detail_json,recorded_at) "
                "VALUES(?,?,?,?)",
                (session_id, event_type, json.dumps(detail, sort_keys=True, separators=(",", ":")), utc_now()),
            )
