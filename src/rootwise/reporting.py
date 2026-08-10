"""Minimal read-only inventory report reader."""

from __future__ import annotations

from pathlib import Path

from .canonicalize import open_read_only


def session_report(database: str | Path) -> list[dict[str, object]]:
    with open_read_only(database) as connection:
        rows = connection.execute(
            "SELECT scan_session_id,state,started_at,finished_at,observed_count,error_count "
            "FROM scan_sessions ORDER BY started_at"
        )
        return [dict(row) for row in rows]

