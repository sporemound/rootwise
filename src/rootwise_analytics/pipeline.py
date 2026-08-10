"""Materialize deterministic 0.4 structural analysis with stage provenance."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .roles import RULE_VERSION, RoleResult, classify
from .snapshot import InventorySnapshot
from .structure import PROJECT_RULE_VERSION, aggregate, projects

ANALYSIS_APPLICATION_ID = 1_346_654_808
CODE_VERSION = "0.4.0-alpha"
SCHEMA = """
PRAGMA application_id=1346654808;
CREATE TABLE analysis_runs (
  run_id TEXT PRIMARY KEY, inventory_path TEXT NOT NULL, scan_session_id TEXT NOT NULL,
  input_digest TEXT NOT NULL, output_digest TEXT, state TEXT NOT NULL, started_at TEXT NOT NULL,
  finished_at TEXT, error TEXT
);
CREATE TABLE analysis_stages (
  run_id TEXT NOT NULL, stage_name TEXT NOT NULL, state TEXT NOT NULL,
  input_digest TEXT NOT NULL, config_digest TEXT NOT NULL, output_digest TEXT NOT NULL,
  code_version TEXT NOT NULL, error TEXT, PRIMARY KEY(run_id,stage_name)
);
CREATE TABLE item_roles (
  run_id TEXT NOT NULL, relative_path TEXT NOT NULL, role TEXT NOT NULL, confidence REAL NOT NULL,
  rule_id TEXT NOT NULL, explanation TEXT NOT NULL, evidence_json TEXT NOT NULL,
  PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE directory_aggregates (
  run_id TEXT NOT NULL, relative_path TEXT NOT NULL, recursive_bytes INTEGER NOT NULL,
  file_count INTEGER NOT NULL, directory_count INTEGER NOT NULL, role_counts_json TEXT NOT NULL,
  role_coherence REAL NOT NULL, PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE projects (
  run_id TEXT NOT NULL, relative_path TEXT NOT NULL, boundary_score INTEGER NOT NULL,
  markers_json TEXT NOT NULL, rule_version TEXT NOT NULL, PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE relationships (
  run_id TEXT NOT NULL, source_kind TEXT NOT NULL, source_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL, target_kind TEXT NOT NULL, target_id TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  PRIMARY KEY(run_id,source_kind,source_id,relationship_type,target_kind,target_id)
);
"""


@dataclass(frozen=True)
class AnalysisResult:
    run_id: str
    state: str
    input_digest: str
    output_digest: str
    role_count: int
    directory_count: int
    project_count: int
    relationship_count: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rows_digest(connection: sqlite3.Connection, query: str, parameters: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for row in connection.execute(query, parameters):
        digest.update(json.dumps(tuple(row), separators=(",", ":")).encode("utf-8") + b"\n")
    return digest.hexdigest()


def _stage(
    connection: sqlite3.Connection,
    run_id: str,
    name: str,
    input_digest: str,
    config: object,
    output_digest: str,
) -> None:
    connection.execute(
        "INSERT INTO analysis_stages VALUES(?,?,?,?,?,?,?,NULL)",
        (run_id, name, "COMPLETE", input_digest, _digest(config), output_digest, CODE_VERSION),
    )


def run_analysis(
    inventory_path: str | Path,
    analysis_path: str | Path,
    *,
    session_id: str | None = None,
) -> AnalysisResult:
    inventory = Path(inventory_path).expanduser().resolve(strict=True)
    destination = Path(analysis_path).expanduser().resolve(strict=False)
    if destination == inventory:
        raise ValueError("analysis database must be distinct from inventory")
    if destination.parent != inventory.parent:
        raise ValueError("analysis database must remain in the inventory's external directory")
    if destination.exists():
        raise ValueError("analysis database must not already exist")
    run_id = str(uuid4())
    with InventorySnapshot(inventory, session_id) as snapshot:
        input_digest = snapshot.logical_digest()
        items = list(snapshot.items())
        connection = sqlite3.connect(destination)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT INTO analysis_runs VALUES(?,?,?,?,NULL,?,?,NULL,NULL)",
                (run_id, str(inventory), snapshot.session_id, input_digest, "RUNNING", _utc_now()),
            )
            connection.commit()

            roles: dict[str, RoleResult] = {}
            for item in items:
                if item.kind != "file":
                    continue
                role_result = classify(item)
                roles[item.relative_path] = role_result
                connection.execute(
                    "INSERT INTO item_roles VALUES(?,?,?,?,?,?,?)",
                    (run_id, item.relative_path, role_result.role, role_result.confidence,
                     role_result.rule_id, role_result.explanation,
                     json.dumps(role_result.evidence, separators=(",", ":"))),
                )
            roles_digest = _rows_digest(
                connection,
                "SELECT relative_path,role,confidence,rule_id,explanation,evidence_json "
                "FROM item_roles WHERE run_id=? ORDER BY relative_path",
                (run_id,),
            )
            _stage(connection, run_id, "roles", input_digest, {"rule_version": RULE_VERSION}, roles_digest)

            aggregates = aggregate(items, roles)
            for path, aggregate_result in sorted(aggregates.items()):
                connection.execute(
                    "INSERT INTO directory_aggregates VALUES(?,?,?,?,?,?,?)",
                    (run_id, path, aggregate_result.recursive_bytes, aggregate_result.file_count,
                     aggregate_result.directory_count, json.dumps(aggregate_result.roles,
                     sort_keys=True, separators=(",", ":")), aggregate_result.role_coherence),
                )
            aggregate_digest = _rows_digest(
                connection,
                "SELECT relative_path,recursive_bytes,file_count,directory_count,role_counts_json,"
                "role_coherence FROM directory_aggregates WHERE run_id=? ORDER BY relative_path",
                (run_id,),
            )
            _stage(connection, run_id, "directory_aggregates", roles_digest,
                   {"algorithm": "bottom-up-ancestors-v1"}, aggregate_digest)

            found_projects = projects(items)
            for path, (score, markers) in sorted(found_projects.items()):
                connection.execute(
                    "INSERT INTO projects VALUES(?,?,?,?,?)",
                    (run_id, path, score, json.dumps(markers, separators=(",", ":")),
                     PROJECT_RULE_VERSION),
                )
            project_digest = _rows_digest(
                connection,
                "SELECT relative_path,boundary_score,markers_json,rule_version FROM projects "
                "WHERE run_id=? ORDER BY relative_path",
                (run_id,),
            )
            _stage(connection, run_id, "projects", input_digest,
                   {"rule_version": PROJECT_RULE_VERSION, "threshold": 4}, project_digest)

            project_paths = sorted(found_projects)
            relationship_count = 0
            for project in project_paths:
                parent = next(
                    (candidate for candidate in sorted(project_paths, key=len, reverse=True)
                     if candidate != project and project.startswith(candidate + "/")), None
                )
                if parent is not None:
                    connection.execute(
                        "INSERT INTO relationships VALUES(?,?,?,?,?,?,?)",
                        (run_id, "project", parent, "NESTED_PROJECT", "project", project,
                         '{"basis":"path ancestry"}'),
                    )
                    relationship_count += 1
                for role, count in sorted(aggregates.get(project, aggregates[""]).roles.items()):
                    connection.execute(
                        "INSERT INTO relationships VALUES(?,?,?,?,?,?,?)",
                        (run_id, "project", project, "HAS_ROLE", "role", role,
                         json.dumps({"observed_files": count}, separators=(",", ":"))),
                    )
                    relationship_count += 1
            relationship_digest = _rows_digest(
                connection,
                "SELECT source_kind,source_id,relationship_type,target_kind,target_id,evidence_json "
                "FROM relationships WHERE run_id=? ORDER BY source_kind,source_id,relationship_type,"
                "target_kind,target_id",
                (run_id,),
            )
            _stage(connection, run_id, "relationships", project_digest,
                   {"structural_only": True}, relationship_digest)
            output_digest = _digest(
                [roles_digest, aggregate_digest, project_digest, relationship_digest]
            )
            connection.execute(
                "UPDATE analysis_runs SET output_digest=?,state='COMPLETE',finished_at=? WHERE run_id=?",
                (output_digest, _utc_now(), run_id),
            )
            connection.commit()
            return AnalysisResult(
                run_id, "COMPLETE", input_digest, output_digest, len(roles), len(aggregates),
                len(found_projects), relationship_count,
            )
        except BaseException as exc:
            connection.rollback()
            try:
                connection.execute(
                    "UPDATE analysis_runs SET state='FAILED',finished_at=?,error=? WHERE run_id=?",
                    (_utc_now(), f"{type(exc).__name__}: {exc}", run_id),
                )
                connection.commit()
            finally:
                connection.close()
            raise
        finally:
            if connection:
                connection.close()
