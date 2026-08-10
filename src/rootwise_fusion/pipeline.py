"""Validate and fuse complete structural analysis with complete enrichment evidence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from rootwise_analytics.pipeline import ANALYSIS_APPLICATION_ID

ENRICHMENT_APPLICATION_ID = 1_346_654_811
FUSION_APPLICATION_ID = 1_346_654_812
CODE_VERSION = "0.10.0-alpha"
SCHEMA = """
PRAGMA application_id=1346654812;
CREATE TABLE fusion_runs (
 run_id TEXT PRIMARY KEY, analysis_path TEXT NOT NULL, analysis_run_id TEXT NOT NULL,
 evidence_path TEXT NOT NULL, evidence_run_id TEXT NOT NULL, scan_session_id TEXT NOT NULL,
 inventory_digest TEXT NOT NULL, input_digest TEXT NOT NULL, output_digest TEXT,
 evidence_level TEXT NOT NULL, state TEXT NOT NULL, selected_count INTEGER NOT NULL,
 duplicate_group_count INTEGER NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, error TEXT
);
CREATE TABLE fusion_stages (
 run_id TEXT NOT NULL, stage_name TEXT NOT NULL, state TEXT NOT NULL,
 input_digest TEXT NOT NULL, config_digest TEXT NOT NULL, output_digest TEXT NOT NULL,
 code_version TEXT NOT NULL, error TEXT, PRIMARY KEY(run_id,stage_name)
);
CREATE TABLE imported_file_evidence (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, evidence_level TEXT NOT NULL,
 algorithm TEXT NOT NULL, digest TEXT NOT NULL, logical_bytes INTEGER NOT NULL,
 modified_ns INTEGER, bytes_read INTEGER NOT NULL, PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE imported_duplicate_groups (
 run_id TEXT NOT NULL, group_id TEXT NOT NULL, evidence_level TEXT NOT NULL,
 algorithm TEXT NOT NULL, digest TEXT NOT NULL, logical_bytes INTEGER NOT NULL,
 evidence_status TEXT NOT NULL, member_count INTEGER NOT NULL,
 PRIMARY KEY(run_id,group_id)
);
CREATE TABLE imported_duplicate_members (
 run_id TEXT NOT NULL, group_id TEXT NOT NULL, relative_path TEXT NOT NULL,
 PRIMARY KEY(run_id,group_id,relative_path)
);
CREATE TABLE directory_evidence_features (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, observed_file_count INTEGER NOT NULL,
 observed_logical_bytes INTEGER NOT NULL, selected_file_count INTEGER NOT NULL,
 selected_logical_bytes INTEGER NOT NULL, candidate_member_count INTEGER NOT NULL,
 candidate_member_bytes INTEGER NOT NULL, confirmed_member_count INTEGER NOT NULL,
 confirmed_member_bytes INTEGER NOT NULL, evidence_coverage REAL NOT NULL,
 confirmed_member_ratio_of_selected REAL NOT NULL,
 PRIMARY KEY(run_id,relative_path)
);
"""


@dataclass(frozen=True)
class FusionResult:
    run_id: str
    state: str
    input_digest: str
    output_digest: str
    evidence_level: str
    selected_count: int
    duplicate_group_count: int
    directory_count: int


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _rows_digest(rows: list[tuple[object, ...]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")
    return digest.hexdigest()


def _table_rows(
    connection: sqlite3.Connection, query: str, parameters: tuple[str, ...]
) -> list[tuple[object, ...]]:
    return [tuple(row) for row in connection.execute(query, parameters)]


def _open(path: Path, application_id: int, label: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        if connection.execute("PRAGMA application_id").fetchone()[0] != application_id:
            raise ValueError(f"{label} database application identity mismatch")
    except BaseException:
        connection.close()
        raise
    return connection


def _analysis_snapshot(
    connection: sqlite3.Connection, run_id: str | None
) -> tuple[tuple[object, ...], list[tuple[object, ...]], list[tuple[object, ...]]]:
    if run_id is None:
        row = connection.execute(
            "SELECT run_id,inventory_path,scan_session_id,input_digest,output_digest,state "
            "FROM analysis_runs WHERE state='COMPLETE' "
            "ORDER BY finished_at DESC,run_id DESC LIMIT 1"
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT run_id,inventory_path,scan_session_id,input_digest,output_digest,state "
            "FROM analysis_runs WHERE run_id=?", (run_id,),
        ).fetchone()
    if row is None or row[5] != "COMPLETE" or row[4] is None:
        raise ValueError("fusion requires a COMPLETE analysis run")
    selected_run = str(row[0])
    stages = _table_rows(
        connection,
        "SELECT stage_name,state,input_digest,config_digest,output_digest,code_version,error "
        "FROM analysis_stages WHERE run_id=? ORDER BY stage_name",
        (selected_run,),
    )
    if {(str(item[0]), str(item[1])) for item in stages} != {
        ("roles", "COMPLETE"), ("directory_aggregates", "COMPLETE"),
        ("projects", "COMPLETE"), ("relationships", "COMPLETE"),
    }:
        raise ValueError("analysis prerequisite stages are incomplete or mismatched")
    role_rows = _table_rows(
        connection,
        "SELECT relative_path,role,confidence,rule_id,explanation,evidence_json "
        "FROM item_roles WHERE run_id=? ORDER BY relative_path",
        (selected_run,),
    )
    aggregate_rows = _table_rows(
        connection,
        "SELECT relative_path,recursive_bytes,file_count,directory_count,role_counts_json,"
        "role_coherence FROM directory_aggregates WHERE run_id=? ORDER BY relative_path",
        (selected_run,),
    )
    project_rows = _table_rows(
        connection,
        "SELECT relative_path,boundary_score,markers_json,rule_version FROM projects "
        "WHERE run_id=? ORDER BY relative_path",
        (selected_run,),
    )
    relationship_rows = _table_rows(
        connection,
        "SELECT source_kind,source_id,relationship_type,target_kind,target_id,evidence_json "
        "FROM relationships WHERE run_id=? ORDER BY source_kind,source_id,relationship_type,"
        "target_kind,target_id",
        (selected_run,),
    )
    logical_output = _digest([
        _rows_digest(role_rows), _rows_digest(aggregate_rows), _rows_digest(project_rows),
        _rows_digest(relationship_rows),
    ])
    if logical_output != str(row[4]):
        raise ValueError("analysis logical output digest mismatch")
    return tuple(row), stages, aggregate_rows


def _expected_algorithm(level: str) -> str:
    return {"D2": "BLAKE3-SAMPLED-V1", "D3": "BLAKE3", "D4": "SHA-256"}[level]


def _evidence_snapshot(
    connection: sqlite3.Connection, run_id: str | None
) -> tuple[
    tuple[object, ...], list[tuple[object, ...]], list[tuple[object, ...]],
    list[tuple[object, ...]], list[tuple[object, ...]],
]:
    if run_id is None:
        row = connection.execute(
            "SELECT run_id,inventory_path,scan_session_id,inventory_digest,selection_digest,"
            "evidence_level,state,output_digest,selected_count,completed_count FROM enrichment_runs "
            "WHERE state='COMPLETE' ORDER BY finished_at DESC,run_id DESC LIMIT 1"
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT run_id,inventory_path,scan_session_id,inventory_digest,selection_digest,"
            "evidence_level,state,output_digest,selected_count,completed_count FROM enrichment_runs "
            "WHERE run_id=?", (run_id,),
        ).fetchone()
    if row is None or row[6] != "COMPLETE" or row[7] is None:
        raise ValueError("fusion requires a COMPLETE enrichment run")
    if row[5] not in {"D2", "D3", "D4"} or row[8] != row[9]:
        raise ValueError("enrichment level or completion counts are invalid")
    selected_run = str(row[0])
    stages = _table_rows(
        connection,
        "SELECT stage_name,state,input_digest,config_digest,output_digest,code_version,error "
        "FROM enrichment_stages WHERE run_id=? ORDER BY stage_name",
        (selected_run,),
    )
    if {(str(item[0]), str(item[1])) for item in stages} != {
        ("selection", "COMPLETE"), ("read", "COMPLETE"), ("duplicates", "COMPLETE"),
    }:
        raise ValueError("enrichment prerequisite stages are incomplete or mismatched")
    file_rows = _table_rows(
        connection,
        "SELECT relative_path,evidence_level,algorithm,digest,logical_bytes,modified_ns,bytes_read,state "
        "FROM file_evidence WHERE run_id=? ORDER BY relative_path",
        (selected_run,),
    )
    if len(file_rows) != int(row[8]):
        raise ValueError("enrichment file evidence count mismatch")
    level = str(row[5])
    algorithm = _expected_algorithm(level)
    for item in file_rows:
        digest = str(item[3])
        if item[1] != level or item[2] != algorithm or item[7] != "COMPLETE":
            raise ValueError("file evidence level, algorithm, or state mismatch")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("file evidence digest is invalid")
    group_rows = _table_rows(
        connection,
        "SELECT group_id,evidence_level,algorithm,digest,logical_bytes,evidence_status,member_count "
        "FROM duplicate_groups WHERE run_id=? ORDER BY group_id",
        (selected_run,),
    )
    member_rows = _table_rows(
        connection,
        "SELECT group_id,relative_path FROM duplicate_members WHERE run_id=? "
        "ORDER BY group_id,relative_path",
        (selected_run,),
    )
    by_path = {str(item[0]): item for item in file_rows}
    group_ids = {str(group[0]) for group in group_rows}
    members_by_group: dict[str, list[str]] = {}
    for group_id, relative_path in member_rows:
        if str(group_id) not in group_ids:
            raise ValueError("duplicate member references an unknown group")
        members_by_group.setdefault(str(group_id), []).append(str(relative_path))
    expected_status = "CANDIDATE" if level == "D2" else "CONFIRMED"
    for group in group_rows:
        group_id = str(group[0])
        members = members_by_group.get(group_id, [])
        expected_group_id = _digest([
            level, algorithm, str(group[3]), _integer(group[4], "duplicate logical bytes")
        ])
        if group_id != expected_group_id or group[1] != level or group[2] != algorithm:
            raise ValueError("duplicate group identity or algorithm mismatch")
        if group[5] != expected_status or len(members) != _integer(
            group[6], "duplicate member count"
        ) or len(members) < 2:
            raise ValueError("duplicate group status or member count mismatch")
        if any(
            member not in by_path or str(by_path[member][3]) != str(group[3])
            or _integer(by_path[member][4], "file logical bytes") != _integer(
                group[4], "duplicate logical bytes"
            ) for member in members
        ):
            raise ValueError("duplicate group members do not match file evidence")
    evidence_digest = _rows_digest(file_rows)
    group_digest = _digest(group_rows)
    if _digest([evidence_digest, group_digest]) != str(row[7]):
        raise ValueError("enrichment logical output digest mismatch")
    stage_outputs = {str(item[0]): str(item[4]) for item in stages}
    if stage_outputs["selection"] != str(row[4]) or stage_outputs["read"] != evidence_digest or (
        stage_outputs["duplicates"] != group_digest
    ):
        raise ValueError("enrichment stage output digest mismatch")
    if connection.execute(
        "SELECT COUNT(*) FROM enrichment_errors WHERE run_id=?", (selected_run,),
    ).fetchone()[0]:
        raise ValueError("complete enrichment run contains recorded errors")
    return tuple(row), stages, file_rows, group_rows, member_rows


def _ancestors(relative_path: str) -> tuple[str, ...]:
    parts = relative_path.split("/")[:-1]
    return ("", *("/".join(parts[:index]) for index in range(1, len(parts) + 1)))


def _features(
    aggregates: list[tuple[object, ...]],
    file_rows: list[tuple[object, ...]],
    group_rows: list[tuple[object, ...]],
    member_rows: list[tuple[object, ...]],
) -> list[tuple[object, ...]]:
    directories = {
        str(row[0]): (
            _integer(row[2], "aggregate file count"),
            _integer(row[1], "aggregate logical bytes"),
        ) for row in aggregates
    }
    counters: dict[str, list[int]] = {path: [0, 0, 0, 0, 0, 0] for path in directories}
    status_by_group = {str(row[0]): str(row[5]) for row in group_rows}
    status_by_path = {
        str(relative_path): status_by_group[str(group_id)] for group_id, relative_path in member_rows
    }
    if len(status_by_path) != len(member_rows):
        raise ValueError("file evidence member appears in multiple duplicate groups")
    role_paths: set[str] = set()
    for row in file_rows:
        path = str(row[0])
        size = _integer(row[4], "file evidence logical bytes")
        role_paths.add(path)
        for directory in _ancestors(path):
            if directory not in counters:
                raise ValueError("file evidence path is absent from analysis directory aggregates")
            values = counters[directory]
            values[0] += 1
            values[1] += size
            if status_by_path.get(path) == "CANDIDATE":
                values[2] += 1
                values[3] += size
            elif status_by_path.get(path) == "CONFIRMED":
                values[4] += 1
                values[5] += size
    if len(role_paths) != len(file_rows):
        raise ValueError("file evidence paths are not unique")
    result: list[tuple[object, ...]] = []
    for path in sorted(directories):
        observed_count, observed_bytes = directories[path]
        selected_count, selected_bytes, candidate_count, candidate_bytes, confirmed_count, confirmed_bytes = (
            counters[path]
        )
        if selected_count > observed_count or selected_bytes > observed_bytes:
            raise ValueError("evidence coverage exceeds the analysis aggregate")
        coverage = selected_count / observed_count if observed_count else 0.0
        confirmed_ratio = confirmed_count / selected_count if selected_count else 0.0
        result.append((
            path, observed_count, observed_bytes, selected_count, selected_bytes,
            candidate_count, candidate_bytes, confirmed_count, confirmed_bytes,
            coverage, confirmed_ratio,
        ))
    return result


def _stage(
    connection: sqlite3.Connection, run_id: str, name: str, input_digest: str,
    config: object, output_digest: str,
) -> None:
    connection.execute(
        "INSERT INTO fusion_stages VALUES(?,?,?,?,?,?,?,NULL)",
        (run_id, name, "COMPLETE", input_digest, _digest(config), output_digest, CODE_VERSION),
    )


def run_fusion(
    analysis_path: str | Path,
    evidence_path: str | Path,
    fusion_path: str | Path,
    *,
    analysis_run_id: str | None = None,
    evidence_run_id: str | None = None,
) -> FusionResult:
    analysis = Path(analysis_path).expanduser().resolve(strict=True)
    evidence = Path(evidence_path).expanduser().resolve(strict=True)
    destination = Path(fusion_path).expanduser().resolve(strict=False)
    if len({analysis, evidence, destination}) != 3 or evidence.parent != analysis.parent or (
        destination.parent != analysis.parent
    ) or destination.exists():
        raise ValueError("analysis, evidence, and new fusion databases must be distinct siblings")
    analysis_db = _open(analysis, ANALYSIS_APPLICATION_ID, "analysis")
    evidence_db = _open(evidence, ENRICHMENT_APPLICATION_ID, "enrichment")
    try:
        analysis_run, analysis_stages, aggregates = _analysis_snapshot(
            analysis_db, analysis_run_id
        )
        evidence_run, evidence_stages, file_rows, group_rows, member_rows = _evidence_snapshot(
            evidence_db, evidence_run_id
        )
        analysis_inventory = Path(str(analysis_run[1])).resolve(strict=True)
        evidence_inventory = Path(str(evidence_run[1])).resolve(strict=True)
        if analysis_inventory != evidence_inventory or analysis_inventory.parent != analysis.parent:
            raise ValueError("analysis and enrichment inventory provenance does not match")
        if str(analysis_run[2]) != str(evidence_run[2]) or str(analysis_run[3]) != str(evidence_run[3]):
            raise ValueError("analysis and enrichment session or inventory digest mismatch")
        input_digest = _digest([
            str(analysis_run[3]), str(analysis_run[4]), str(evidence_run[4]), str(evidence_run[7]),
        ])
        features = _features(aggregates, file_rows, group_rows, member_rows)
    finally:
        analysis_db.close()
        evidence_db.close()
    run_id = str(uuid4())
    output = sqlite3.connect(destination)
    try:
        output.execute("PRAGMA journal_mode=DELETE")
        output.execute("PRAGMA synchronous=FULL")
        output.executescript(SCHEMA)
        output.execute(
            "INSERT INTO fusion_runs VALUES(?,?,?,?,?,?,?,?,NULL,?,'RUNNING',?,?,?,NULL,NULL)",
            (run_id, str(analysis), str(analysis_run[0]), str(evidence), str(evidence_run[0]),
             str(analysis_run[2]), str(analysis_run[3]), input_digest, str(evidence_run[5]),
             len(file_rows), len(group_rows), _utc()),
        )
        validation_digest = _digest([analysis_stages, evidence_stages])
        _stage(output, run_id, "validate", input_digest,
               {"analysis": CODE_VERSION, "enrichment_levels": ["D2", "D3", "D4"]},
               validation_digest)
        output.executemany(
            "INSERT INTO imported_file_evidence VALUES(?,?,?,?,?,?,?,?)",
            [(run_id, *row[:-1]) for row in file_rows],
        )
        output.executemany(
            "INSERT INTO imported_duplicate_groups VALUES(?,?,?,?,?,?,?,?)",
            [(run_id, *row) for row in group_rows],
        )
        output.executemany(
            "INSERT INTO imported_duplicate_members VALUES(?,?,?)",
            [(run_id, *row) for row in member_rows],
        )
        import_digest = _digest([file_rows, group_rows, member_rows])
        _stage(output, run_id, "import", validation_digest,
               {"D2": "CANDIDATE", "D3": "CONFIRMED", "D4": "CONFIRMED"}, import_digest)
        output.executemany(
            "INSERT INTO directory_evidence_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [(run_id, *row) for row in features],
        )
        feature_digest = _rows_digest([tuple(row) for row in features])
        _stage(output, run_id, "directory_features", import_digest,
               {"coverage_denominator": "analysis_observed_file_count",
                "confirmed_ratio_denominator": "selected_file_count"}, feature_digest)
        output_digest = _digest([validation_digest, import_digest, feature_digest])
        output.execute(
            "UPDATE fusion_runs SET output_digest=?,state='COMPLETE',finished_at=? WHERE run_id=?",
            (output_digest, _utc(), run_id),
        )
        output.commit()
        return FusionResult(
            run_id, "COMPLETE", input_digest, output_digest, str(evidence_run[5]),
            len(file_rows), len(group_rows), len(features),
        )
    except BaseException as exc:
        output.rollback()
        output.execute(
            "UPDATE fusion_runs SET state='FAILED',finished_at=?,error=? WHERE run_id=?",
            (_utc(), f"{type(exc).__name__}: {exc}", run_id),
        )
        output.commit()
        raise
    finally:
        output.close()
