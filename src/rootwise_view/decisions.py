"""Separate, revision-checked, append-audited user decision storage."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

DECISION_APPLICATION_ID = 1_346_654_807
DECISIONS = (
    "KEEP",
    "PROTECT",
    "ARCHIVE_ELIGIBLE",
    "REBUILDABLE",
    "NOT_REBUILDABLE",
    "PROJECT_BOUNDARY",
    "NOT_A_PROJECT",
    "EXCLUDE_FROM_ANALYSIS",
    "UNKNOWN",
)

SCHEMA = """
PRAGMA application_id=1346654807;
CREATE TABLE IF NOT EXISTS current_decisions (
  scan_session_id TEXT NOT NULL,
  relative_path TEXT NOT NULL,
  decision TEXT NOT NULL,
  note TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(scan_session_id, relative_path)
);
CREATE TABLE IF NOT EXISTS decision_events (
  event_id INTEGER PRIMARY KEY,
  scan_session_id TEXT NOT NULL,
  relative_path TEXT NOT NULL,
  previous_decision TEXT,
  decision TEXT NOT NULL,
  note TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  recorded_at TEXT NOT NULL,
  UNIQUE(scan_session_id, relative_path, revision)
);
CREATE INDEX IF NOT EXISTS decision_events_subject
ON decision_events(scan_session_id, relative_path, revision);
"""


class DecisionConflictError(RuntimeError):
    """A decision changed after the caller read it or lacks an explicit revision."""


@dataclass(frozen=True)
class DecisionRecord:
    scan_session_id: str
    relative_path: str
    decision: str
    note: str
    revision: int
    recorded_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_subject(session_id: str, relative_path: str) -> str:
    if not session_id or len(session_id) > 128 or "\x00" in session_id:
        raise ValueError("scan session ID is invalid")
    normalized = relative_path.replace("\\", "/")
    if "\x00" in normalized or normalized.startswith("/"):
        raise ValueError("decision subject must be a relative inventory path")
    parts = PurePosixPath(normalized).parts
    if any(part in {".", ".."} for part in parts):
        raise ValueError("decision subject must be a normalized relative inventory path")
    return "/".join(parts) if normalized else ""


class DecisionStore:
    def __init__(self, path: str | Path, *, inventory_path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        inventory = Path(inventory_path).expanduser().resolve(strict=True)
        if self.path == inventory:
            raise ValueError("decision database must be distinct from the inventory database")
        if self.path.parent != inventory.parent:
            raise ValueError(
                "decision database must remain in the inventory database's external directory"
            )
        self.path.parent.resolve(strict=True)
        existed = self.path.exists()
        self._connection = sqlite3.connect(self.path, timeout=30.0)
        self._connection.row_factory = sqlite3.Row
        try:
            application_id = self._connection.execute("PRAGMA application_id").fetchone()[0]
            if existed and application_id != DECISION_APPLICATION_ID:
                raise ValueError("decision database application identity mismatch")
            self._connection.execute("PRAGMA journal_mode=DELETE")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.executescript(SCHEMA)
            self._connection.commit()
        except BaseException:
            self._connection.close()
            raise

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "DecisionStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def current(self, session_id: str, relative_path: str) -> DecisionRecord | None:
        subject = _validate_subject(session_id, relative_path)
        row = self._connection.execute(
            "SELECT scan_session_id,relative_path,decision,note,revision,updated_at AS recorded_at "
            "FROM current_decisions WHERE scan_session_id=? AND relative_path=?",
            (session_id, subject),
        ).fetchone()
        return None if row is None else DecisionRecord(**dict(row))

    def history(self, session_id: str, relative_path: str) -> list[DecisionRecord]:
        subject = _validate_subject(session_id, relative_path)
        rows = self._connection.execute(
            "SELECT scan_session_id,relative_path,decision,note,revision,recorded_at "
            "FROM decision_events WHERE scan_session_id=? AND relative_path=? ORDER BY revision",
            (session_id, subject),
        )
        return [DecisionRecord(**dict(row)) for row in rows]

    def set_decision(
        self,
        session_id: str,
        relative_path: str,
        decision: str,
        *,
        note: str = "",
        expected_revision: int | None = None,
    ) -> DecisionRecord:
        subject = _validate_subject(session_id, relative_path)
        if decision not in DECISIONS:
            raise ValueError(f"unsupported decision: {decision}")
        if len(note) > 4_000 or "\x00" in note:
            raise ValueError("decision note must contain at most 4000 characters and no NUL")
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            current = self._connection.execute(
                "SELECT decision,revision FROM current_decisions "
                "WHERE scan_session_id=? AND relative_path=?",
                (session_id, subject),
            ).fetchone()
            if current is None:
                if expected_revision not in {None, 0}:
                    raise DecisionConflictError("new decision expected revision must be 0 or omitted")
                previous = None
                revision = 1
            else:
                revision = int(current["revision"]) + 1
                if expected_revision != current["revision"]:
                    raise DecisionConflictError(
                        f"decision update requires expected revision {current['revision']}"
                    )
                previous = str(current["decision"])
            recorded_at = _utc_now()
            self._connection.execute(
                "INSERT INTO current_decisions VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(scan_session_id,relative_path) DO UPDATE SET "
                "decision=excluded.decision,note=excluded.note,revision=excluded.revision,"
                "updated_at=excluded.updated_at",
                (session_id, subject, decision, note, revision, recorded_at),
            )
            self._connection.execute(
                "INSERT INTO decision_events(scan_session_id,relative_path,previous_decision,"
                "decision,note,revision,recorded_at) VALUES(?,?,?,?,?,?,?)",
                (session_id, subject, previous, decision, note, revision, recorded_at),
            )
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return DecisionRecord(session_id, subject, decision, note, revision, recorded_at)
