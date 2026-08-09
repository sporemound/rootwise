"""Fail-closed, bounded D2/D3/D4 enrichment over an explicit file selection."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from paretodrive.models import VolumeInfo
from paretodrive.volume import resolve_volume, validate_distinct_volumes

from .reader import InventoryFile, RateLimiter, ReadPolicy, hash_file
from .selection import Selection, load_selection

ENRICHMENT_APPLICATION_ID = 1_346_654_811
CODE_VERSION = "0.7.0-alpha"
SCHEMA = """
PRAGMA application_id=1346654811;
CREATE TABLE enrichment_runs (
 run_id TEXT PRIMARY KEY, inventory_path TEXT NOT NULL, source_root TEXT NOT NULL,
 scan_session_id TEXT NOT NULL, inventory_digest TEXT NOT NULL, selection_digest TEXT NOT NULL,
 evidence_level TEXT NOT NULL, state TEXT NOT NULL, output_digest TEXT,
 blake3_version TEXT NOT NULL, policy_json TEXT NOT NULL, selected_count INTEGER NOT NULL,
 completed_count INTEGER NOT NULL, bytes_read INTEGER NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, error TEXT
);
CREATE TABLE enrichment_stages (
 run_id TEXT NOT NULL, stage_name TEXT NOT NULL, state TEXT NOT NULL,
 input_digest TEXT NOT NULL, config_digest TEXT NOT NULL, output_digest TEXT NOT NULL,
 code_version TEXT NOT NULL, error TEXT, PRIMARY KEY(run_id,stage_name)
);
CREATE TABLE file_evidence (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, evidence_level TEXT NOT NULL,
 algorithm TEXT NOT NULL, digest TEXT NOT NULL, logical_bytes INTEGER NOT NULL,
 modified_ns INTEGER, bytes_read INTEGER NOT NULL, state TEXT NOT NULL,
 PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE duplicate_groups (
 run_id TEXT NOT NULL, group_id TEXT NOT NULL, evidence_level TEXT NOT NULL,
 algorithm TEXT NOT NULL, digest TEXT NOT NULL, logical_bytes INTEGER NOT NULL,
 evidence_status TEXT NOT NULL, member_count INTEGER NOT NULL,
 PRIMARY KEY(run_id,group_id)
);
CREATE TABLE duplicate_members (
 run_id TEXT NOT NULL, group_id TEXT NOT NULL, relative_path TEXT NOT NULL,
 PRIMARY KEY(run_id,group_id,relative_path)
);
CREATE TABLE enrichment_errors (
 error_id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, relative_path TEXT NOT NULL,
 error_type TEXT NOT NULL, message TEXT NOT NULL
);
"""

VolumeResolver = Callable[[str | os.PathLike[str]], VolumeInfo]


@dataclass(frozen=True)
class EnrichmentResult:
    run_id: str
    state: str
    input_digest: str
    output_digest: str | None
    selected_count: int
    completed_count: int
    bytes_read: int
    duplicate_group_count: int


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _inventory_digest(connection: sqlite3.Connection, session_id: str) -> str:
    digest = hashlib.sha256()
    rows = connection.execute(
        "SELECT kind,relative_path,parent_path,name,extension,logical_bytes,depth FROM ("
        "SELECT 'directory' kind,relative_path,parent_path,name,'' extension,logical_bytes,depth "
        "FROM directories WHERE scan_session_id=? UNION ALL "
        "SELECT 'file' kind,relative_path,parent_path,name,extension,logical_bytes,depth "
        "FROM files WHERE scan_session_id=?) ORDER BY relative_path COLLATE BINARY,kind",
        (session_id, session_id),
    )
    names = ("kind", "relative_path", "parent_path", "name", "extension", "logical_bytes", "depth")
    for row in rows:
        payload = json.dumps(dict(zip(names, row, strict=True)), sort_keys=True, separators=(",", ":"))
        digest.update(payload.encode("utf-8") + b"\n")
    return digest.hexdigest()


def _stage(
    connection: sqlite3.Connection,
    run_id: str,
    name: str,
    state: str,
    input_digest: str,
    config: object,
    output_digest: str,
    error: str | None = None,
) -> None:
    connection.execute(
        "INSERT INTO enrichment_stages VALUES(?,?,?,?,?,?,?,?)",
        (run_id, name, state, input_digest, _digest(config), output_digest, CODE_VERSION, error),
    )


def _evidence_digest(connection: sqlite3.Connection, run_id: str) -> str:
    digest = hashlib.sha256()
    for row in connection.execute(
        "SELECT relative_path,evidence_level,algorithm,digest,logical_bytes,modified_ns,bytes_read,state "
        "FROM file_evidence WHERE run_id=? ORDER BY relative_path", (run_id,),
    ):
        digest.update(json.dumps(tuple(row), separators=(",", ":")).encode("utf-8") + b"\n")
    return digest.hexdigest()


def _group_duplicates(
    connection: sqlite3.Connection, run_id: str, selection: Selection
) -> tuple[int, str]:
    groups = list(connection.execute(
        "SELECT algorithm,digest,logical_bytes,COUNT(*) FROM file_evidence "
        "WHERE run_id=? AND state='COMPLETE' GROUP BY algorithm,digest,logical_bytes "
        "HAVING COUNT(*)>=2 ORDER BY algorithm,digest,logical_bytes", (run_id,),
    ))
    for algorithm, digest, size, count in groups:
        group_id = _digest([selection.evidence_level, str(algorithm), str(digest), int(size)])
        status = "CANDIDATE" if selection.evidence_level == "D2" else "CONFIRMED"
        connection.execute("INSERT INTO duplicate_groups VALUES(?,?,?,?,?,?,?,?)", (
            run_id, group_id, selection.evidence_level, str(algorithm), str(digest), int(size),
            status, int(count),
        ))
        connection.executemany("INSERT INTO duplicate_members VALUES(?,?,?)", [
            (run_id, group_id, str(row[0])) for row in connection.execute(
                "SELECT relative_path FROM file_evidence WHERE run_id=? AND algorithm=? "
                "AND digest=? AND logical_bytes=? ORDER BY relative_path",
                (run_id, algorithm, digest, size),
            )
        ])
    group_digest = _digest([tuple(row) for row in connection.execute(
        "SELECT group_id,evidence_level,algorithm,digest,logical_bytes,evidence_status,member_count "
        "FROM duplicate_groups WHERE run_id=? ORDER BY group_id", (run_id,),
    )])
    return len(groups), group_digest


def run_enrichment(
    inventory_path: str | Path,
    source_root: str | Path,
    selection_path: str | Path,
    evidence_path: str | Path,
    *,
    allow_content_read: bool = False,
    read_policy: ReadPolicy | None = None,
    maximum_files: int = 10_000,
    stop_after: int | None = None,
    volume_resolver: VolumeResolver = resolve_volume,
) -> EnrichmentResult:
    if not allow_content_read:
        raise PermissionError("content reading requires explicit allow_content_read acknowledgement")
    if maximum_files < 1 or stop_after is not None and stop_after < 1:
        raise ValueError("file and cancellation bounds must be positive")
    inventory = Path(inventory_path).expanduser().resolve(strict=True)
    source = Path(source_root).expanduser().resolve(strict=True)
    destination = Path(evidence_path).expanduser().resolve(strict=False)
    selection_file = Path(selection_path).expanduser().resolve(strict=True)
    if destination.exists() or destination.parent != inventory.parent:
        raise ValueError("evidence database must be a new file beside the inventory database")
    if destination in {inventory, selection_file} or source == destination:
        raise ValueError("source, inventory, selection, and evidence paths must be distinct")
    source_volume = volume_resolver(source)
    destination_volume = volume_resolver(destination.parent)
    validate_distinct_volumes(source_volume, destination_volume)
    policy = read_policy or ReadPolicy()
    policy.validate()
    selection = load_selection(selection_file, maximum_files=maximum_files)

    input_db = sqlite3.connect(inventory.as_uri() + "?mode=ro", uri=True)
    input_db.execute("PRAGMA query_only=ON")
    input_db.execute("BEGIN")
    try:
        if input_db.execute("PRAGMA application_id").fetchone()[0] != 1_346_654_806:
            raise ValueError("inventory database application identity mismatch")
        session = input_db.execute(
            "SELECT s.source_root,v.identity FROM scan_sessions s JOIN volumes v USING(volume_id) "
            "WHERE s.scan_session_id=? AND s.state='COMPLETE'", (selection.scan_session_id,),
        ).fetchone()
        if session is None:
            raise ValueError("enrichment requires the selected COMPLETE inventory session")
        if Path(str(session[0])).resolve(strict=True) != source:
            raise ValueError("source root does not match the selected inventory session")
        if str(session[1]) != source_volume.identity:
            raise ValueError("source volume identity no longer matches the inventory")
        inventory_digest = _inventory_digest(input_db, selection.scan_session_id)
        if inventory_digest != selection.inventory_digest:
            raise ValueError("selection inventory digest does not match the immutable snapshot")
        files: list[InventoryFile] = []
        for relative_path in selection.paths:
            row = input_db.execute(
                "SELECT logical_bytes,modified_ns,entry_type,observation_status FROM files "
                "WHERE scan_session_id=? AND relative_path=?",
                (selection.scan_session_id, relative_path),
            ).fetchone()
            if row is None or row[2] != "FILE" or row[3] != "OBSERVED":
                raise ValueError(f"selected path is not an observed regular file: {relative_path}")
            files.append(InventoryFile(relative_path, int(row[0]),
                                       None if row[1] is None else int(row[1])))

        run_id = str(uuid4())
        input_digest = _digest([inventory_digest, selection.manifest_digest])
        output = sqlite3.connect(destination)
        try:
            output.execute("PRAGMA journal_mode=DELETE")
            output.execute("PRAGMA synchronous=FULL")
            output.executescript(SCHEMA)
            output.execute(
                "INSERT INTO enrichment_runs VALUES(?,?,?,?,?,?,?,'RUNNING',NULL,?,?,?,?,?,?,NULL,NULL)",
                (run_id, str(inventory), str(source), selection.scan_session_id, inventory_digest,
                 selection.manifest_digest, selection.evidence_level,
                 importlib.metadata.version("blake3"), json.dumps(asdict(policy), sort_keys=True),
                 len(files), 0, 0, _utc()),
            )
            _stage(output, run_id, "selection", "COMPLETE", input_digest,
                   {"maximum_files": maximum_files}, selection.manifest_digest)
            output.commit()
            limiter = RateLimiter(policy.maximum_bytes_per_second)
            completed = 0
            total_bytes_read = 0
            for item in files:
                algorithm, digest, bytes_read = hash_file(
                    source, item, selection.evidence_level, policy, limiter
                )
                output.execute("INSERT INTO file_evidence VALUES(?,?,?,?,?,?,?,?,?)", (
                    run_id, item.relative_path, selection.evidence_level, algorithm, digest,
                    item.logical_bytes, item.modified_ns, bytes_read, "COMPLETE",
                ))
                completed += 1
                total_bytes_read += bytes_read
                output.execute(
                    "UPDATE enrichment_runs SET completed_count=?,bytes_read=? WHERE run_id=?",
                    (completed, total_bytes_read, run_id),
                )
                output.commit()
                if stop_after is not None and completed >= stop_after and completed < len(files):
                    evidence_digest = _evidence_digest(output, run_id)
                    _stage(output, run_id, "read", "STOPPED", selection.manifest_digest,
                           asdict(policy), evidence_digest, "operator stop_after reached")
                    output.execute(
                        "UPDATE enrichment_runs SET state='STOPPED',output_digest=?,finished_at=? "
                        "WHERE run_id=?", (evidence_digest, _utc(), run_id),
                    )
                    output.commit()
                    return EnrichmentResult(
                        run_id, "STOPPED", input_digest, evidence_digest, len(files), completed,
                        total_bytes_read, 0,
                    )
            evidence_digest = _evidence_digest(output, run_id)
            _stage(output, run_id, "read", "COMPLETE", selection.manifest_digest,
                   asdict(policy), evidence_digest)
            group_count, group_digest = _group_duplicates(output, run_id, selection)
            _stage(output, run_id, "duplicates", "COMPLETE", evidence_digest,
                   {"D2": "CANDIDATE", "D3": "CONFIRMED", "D4": "CONFIRMED"}, group_digest)
            output_digest = _digest([evidence_digest, group_digest])
            output.execute(
                "UPDATE enrichment_runs SET state='COMPLETE',output_digest=?,finished_at=? "
                "WHERE run_id=?", (output_digest, _utc(), run_id),
            )
            output.commit()
            return EnrichmentResult(
                run_id, "COMPLETE", input_digest, output_digest, len(files), completed,
                total_bytes_read, group_count,
            )
        except (KeyboardInterrupt, SystemExit):
            output.rollback()
            output.execute(
                "UPDATE enrichment_runs SET state='STOPPED',finished_at=?,error=? WHERE run_id=?",
                (_utc(), "operator interruption", run_id),
            )
            output.commit()
            raise
        except BaseException as exc:
            output.rollback()
            output.execute(
                "INSERT INTO enrichment_errors(run_id,relative_path,error_type,message) "
                "VALUES(?,?,?,?)", (run_id, "", type(exc).__name__, str(exc)),
            )
            output.execute(
                "UPDATE enrichment_runs SET state='FAILED',finished_at=?,error=? WHERE run_id=?",
                (_utc(), f"{type(exc).__name__}: {exc}", run_id),
            )
            output.commit()
            raise
        finally:
            output.close()
    finally:
        input_db.close()
