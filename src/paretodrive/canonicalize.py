"""Streaming deterministic NDJSON export for completed inventory sessions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .database import InventoryDatabase, utc_now
from .errors import ScanStateError
from .write_guard import WriteGuard


def _timestamp(ns: int | None) -> str | None:
    if ns is None:
        return None
    return datetime.fromtimestamp(ns / 1_000_000_000, timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _line(record: dict[str, object]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def export_canonical(
    database: InventoryDatabase,
    guard: WriteGuard,
    session_id: str,
    output: str | Path,
) -> tuple[str, int]:
    connection = database.connection
    connection.execute("BEGIN")
    try:
        _validate_snapshot(connection, session_id)
        digest = hashlib.sha256()
        count = 0
        with guard.open_new_binary(output) as (destination, stream):
            header = _line({"record_type": "session", "schema": 1, "status": "COMPLETE"})
            stream.write(header)
            digest.update(header)
            count += 1
            for table, record_type in (("directories", "directory"), ("files", "file")):
                columns = (
                    "relative_path,comparison_path,parent_path,name,entry_type,logical_bytes,"
                    "created_ns,modified_ns,accessed_ns,attributes,depth,display_path,observation_status"
                )
                if table == "files":
                    columns = columns.replace("name,entry_type", "name,extension,entry_type")
                query = (
                    f"SELECT {columns} FROM {table} WHERE scan_session_id=? "
                    "ORDER BY relative_path COLLATE BINARY"
                )
                for row in connection.execute(query, (session_id,)):
                    record = dict(row)
                    record["record_type"] = record_type
                    for field in ("created_ns", "modified_ns", "accessed_ns"):
                        record[field.removesuffix("_ns") + "_time"] = _timestamp(record.pop(field))
                    encoded = _line(record)
                    stream.write(encoded)
                    digest.update(encoded)
                    count += 1
            for row in connection.execute(
                "SELECT relative_path,operation,error_type,error_code,message FROM scan_errors "
                "WHERE scan_session_id=? ORDER BY relative_path,operation,error_id",
                (session_id,),
            ):
                record = dict(row)
                record["record_type"] = "error"
                encoded = _line(record)
                stream.write(encoded)
                digest.update(encoded)
                count += 1
        hexadecimal = digest.hexdigest()
        database.connection.execute(
            "INSERT INTO canonical_exports(scan_session_id,output_path,sha256,record_count,completed_at) "
            "VALUES(?,?,?,?,?)",
            (session_id, str(destination), hexadecimal, count, utc_now()),
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    database.record_write(session_id, destination, "canonical_ndjson")
    return hexadecimal, count


def _validate_snapshot(connection: sqlite3.Connection, session_id: str) -> None:
    if connection.execute("PRAGMA application_id").fetchone()[0] != 1_346_654_806:
        raise ScanStateError("database application identity mismatch")
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ScanStateError("SQLite integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ScanStateError("SQLite foreign-key consistency check failed")
    session = connection.execute(
        "SELECT state,observed_count,error_count FROM scan_sessions WHERE scan_session_id=?",
        (session_id,),
    ).fetchone()
    if session is None or session[0] != "COMPLETE":
        raise ScanStateError("canonical export requires a COMPLETE session")
    unfinished = connection.execute(
        "SELECT COUNT(*) FROM scan_frontier WHERE scan_session_id=? AND state!='DONE'",
        (session_id,),
    ).fetchone()[0]
    observed = connection.execute(
        "SELECT (SELECT COUNT(*) FROM files WHERE scan_session_id=?)+"
        "(SELECT COUNT(*) FROM directories WHERE scan_session_id=?)",
        (session_id, session_id),
    ).fetchone()[0]
    errors = connection.execute(
        "SELECT COUNT(*) FROM scan_errors WHERE scan_session_id=?", (session_id,)
    ).fetchone()[0]
    if unfinished or observed != session[1] or errors != session[2]:
        raise ScanStateError("completed session consistency validation failed")


def open_read_only(path: str | Path) -> sqlite3.Connection:
    uri = Path(path).resolve(strict=True).as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection
