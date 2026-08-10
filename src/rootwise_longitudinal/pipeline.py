"""Deterministic longitudinal metadata comparison and conservative project graph."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from rootwise_analytics.pipeline import ANALYSIS_APPLICATION_ID
from rootwise_analytics.snapshot import INVENTORY_APPLICATION_ID

LONGITUDINAL_APPLICATION_ID = 1_346_654_813
CODE_VERSION = "0.11.0-alpha"
SCHEMA = """
PRAGMA application_id=1346654813;
CREATE TABLE longitudinal_runs (
 run_id TEXT PRIMARY KEY, baseline_analysis_path TEXT NOT NULL,
 baseline_analysis_run_id TEXT NOT NULL, current_analysis_path TEXT NOT NULL,
 current_analysis_run_id TEXT NOT NULL, baseline_session_id TEXT NOT NULL,
 current_session_id TEXT NOT NULL, input_digest TEXT NOT NULL, output_digest TEXT,
 state TEXT NOT NULL, shared_extension_threshold REAL NOT NULL,
 dependency_evidence_coverage REAL NOT NULL, started_at TEXT NOT NULL,
 finished_at TEXT, error TEXT
);
CREATE TABLE longitudinal_stages (
 run_id TEXT NOT NULL, stage_name TEXT NOT NULL, state TEXT NOT NULL,
 input_digest TEXT NOT NULL, config_digest TEXT NOT NULL, output_digest TEXT NOT NULL,
 code_version TEXT NOT NULL, error TEXT, PRIMARY KEY(run_id,stage_name)
);
CREATE TABLE file_changes (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, change_type TEXT NOT NULL,
 confidence_state TEXT NOT NULL, baseline_logical_bytes INTEGER,
 current_logical_bytes INTEGER, baseline_modified_ns INTEGER, current_modified_ns INTEGER,
 baseline_attributes INTEGER, current_attributes INTEGER,
 PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE directory_change_features (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, added_count INTEGER NOT NULL,
 removed_count INTEGER NOT NULL, metadata_changed_count INTEGER NOT NULL,
 metadata_unchanged_count INTEGER NOT NULL, ambiguous_count INTEGER NOT NULL,
 logical_bytes_delta INTEGER NOT NULL, churn_ratio REAL NOT NULL,
 PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE project_nodes (
 run_id TEXT NOT NULL, project_id TEXT NOT NULL, relative_path TEXT NOT NULL,
 temporal_state TEXT NOT NULL, changed_file_count INTEGER NOT NULL,
 ambiguous_file_count INTEGER NOT NULL, current_file_count INTEGER NOT NULL,
 PRIMARY KEY(run_id,project_id)
);
CREATE TABLE project_edges (
 run_id TEXT NOT NULL, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
 relationship_type TEXT NOT NULL, directed INTEGER NOT NULL, confidence REAL NOT NULL,
 evidence_json TEXT NOT NULL,
 PRIMARY KEY(run_id,source_id,target_id,relationship_type)
);
CREATE TABLE project_graph_features (
 run_id TEXT NOT NULL, project_id TEXT NOT NULL, degree INTEGER NOT NULL,
 component_id TEXT NOT NULL, dependency_in_degree INTEGER NOT NULL,
 dependency_out_degree INTEGER NOT NULL, dependency_evidence_coverage REAL NOT NULL,
 PRIMARY KEY(run_id,project_id)
);
"""


@dataclass(frozen=True)
class FileObservation:
    relative_path: str
    parent_path: str
    extension: str
    logical_bytes: int
    modified_ns: int | None
    attributes: int


@dataclass(frozen=True)
class Snapshot:
    analysis_path: Path
    analysis_run_id: str
    analysis_input_digest: str
    analysis_output_digest: str
    inventory_path: Path
    session_id: str
    source_root: str
    volume_identity: str
    files: dict[str, FileObservation]
    errors: tuple[str, ...]
    directories: tuple[str, ...]
    projects: tuple[str, ...]
    relationships: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class LongitudinalResult:
    run_id: str
    state: str
    input_digest: str
    output_digest: str
    file_change_count: int
    project_count: int
    edge_count: int


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _rows_digest(rows: list[tuple[object, ...]] | tuple[tuple[object, ...], ...]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")
    return digest.hexdigest()


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _optional_integer(value: object, label: str) -> int | None:
    return None if value is None else _integer(value, label)


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


def _table_rows(
    connection: sqlite3.Connection, query: str, parameters: tuple[str, ...]
) -> list[tuple[object, ...]]:
    return [tuple(row) for row in connection.execute(query, parameters)]


def _inventory_digest(connection: sqlite3.Connection, session_id: str) -> str:
    digest = hashlib.sha256()
    names = ("kind", "relative_path", "parent_path", "name", "extension", "logical_bytes", "depth")
    rows = connection.execute(
        "SELECT kind,relative_path,parent_path,name,extension,logical_bytes,depth FROM ("
        "SELECT 'directory' kind,relative_path,parent_path,name,'' extension,logical_bytes,depth "
        "FROM directories WHERE scan_session_id=? UNION ALL "
        "SELECT 'file' kind,relative_path,parent_path,name,extension,logical_bytes,depth "
        "FROM files WHERE scan_session_id=?) ORDER BY relative_path COLLATE BINARY,kind",
        (session_id, session_id),
    )
    for row in rows:
        payload = json.dumps(dict(zip(names, row, strict=True)), sort_keys=True, separators=(",", ":"))
        digest.update(payload.encode("utf-8") + b"\n")
    return digest.hexdigest()


def _load_snapshot(path: Path, requested_run_id: str | None) -> Snapshot:
    analysis = _open(path, ANALYSIS_APPLICATION_ID, "analysis")
    try:
        if requested_run_id is None:
            run = analysis.execute(
                "SELECT run_id,inventory_path,scan_session_id,input_digest,output_digest,state "
                "FROM analysis_runs WHERE state='COMPLETE' "
                "ORDER BY finished_at DESC,run_id DESC LIMIT 1"
            ).fetchone()
        else:
            run = analysis.execute(
                "SELECT run_id,inventory_path,scan_session_id,input_digest,output_digest,state "
                "FROM analysis_runs WHERE run_id=?", (requested_run_id,),
            ).fetchone()
        if run is None or run[5] != "COMPLETE" or run[4] is None:
            raise ValueError("longitudinal analysis requires a COMPLETE analysis run")
        run_id = str(run[0])
        stages = _table_rows(
            analysis,
            "SELECT stage_name,state FROM analysis_stages WHERE run_id=? ORDER BY stage_name",
            (run_id,),
        )
        if set(stages) != {
            ("roles", "COMPLETE"), ("directory_aggregates", "COMPLETE"),
            ("projects", "COMPLETE"), ("relationships", "COMPLETE"),
        }:
            raise ValueError("analysis prerequisite stages are incomplete or mismatched")
        role_rows = _table_rows(
            analysis,
            "SELECT relative_path,role,confidence,rule_id,explanation,evidence_json "
            "FROM item_roles WHERE run_id=? ORDER BY relative_path",
            (run_id,),
        )
        aggregate_rows = _table_rows(
            analysis,
            "SELECT relative_path,recursive_bytes,file_count,directory_count,role_counts_json,"
            "role_coherence FROM directory_aggregates WHERE run_id=? ORDER BY relative_path",
            (run_id,),
        )
        project_rows = _table_rows(
            analysis,
            "SELECT relative_path,boundary_score,markers_json,rule_version FROM projects "
            "WHERE run_id=? ORDER BY relative_path",
            (run_id,),
        )
        relationship_rows = _table_rows(
            analysis,
            "SELECT source_kind,source_id,relationship_type,target_kind,target_id,evidence_json "
            "FROM relationships WHERE run_id=? ORDER BY source_kind,source_id,relationship_type,"
            "target_kind,target_id",
            (run_id,),
        )
        output_digest = _digest([
            _rows_digest(role_rows), _rows_digest(aggregate_rows), _rows_digest(project_rows),
            _rows_digest(relationship_rows),
        ])
        if output_digest != str(run[4]):
            raise ValueError("analysis logical output digest mismatch")
        inventory_path = Path(str(run[1])).resolve(strict=True)
        if inventory_path.parent != path.parent:
            raise ValueError("recorded inventory escaped the external database directory")
        session_id = str(run[2])
        analysis_input_digest = str(run[3])
        analysis_output_digest = str(run[4])
    finally:
        analysis.close()
    inventory = _open(inventory_path, INVENTORY_APPLICATION_ID, "inventory")
    try:
        session = inventory.execute(
            "SELECT s.source_root,s.state,v.identity FROM scan_sessions s "
            "JOIN volumes v USING(volume_id) WHERE s.scan_session_id=?", (session_id,),
        ).fetchone()
        if session is None or session[1] != "COMPLETE":
            raise ValueError("analysis records a non-complete inventory session")
        if _inventory_digest(inventory, session_id) != analysis_input_digest:
            raise ValueError("inventory logical digest does not match the analysis input")
        files: dict[str, FileObservation] = {}
        for row in inventory.execute(
            "SELECT relative_path,parent_path,extension,logical_bytes,modified_ns,attributes,"
            "entry_type,observation_status FROM files WHERE scan_session_id=? "
            "ORDER BY relative_path COLLATE BINARY", (session_id,),
        ):
            if row[6] != "FILE" or row[7] != "OBSERVED":
                continue
            observation = FileObservation(
                str(row[0]), str(row[1] or ""), str(row[2]),
                _integer(row[3], "file logical bytes"),
                _optional_integer(row[4], "file modification timestamp"),
                _integer(row[5], "file attributes"),
            )
            files[observation.relative_path] = observation
        errors = tuple(str(row[0]) for row in inventory.execute(
            "SELECT relative_path FROM scan_errors WHERE scan_session_id=? ORDER BY relative_path",
            (session_id,),
        ))
    finally:
        inventory.close()
    return Snapshot(
        path, run_id, analysis_input_digest, analysis_output_digest, inventory_path, session_id,
        str(session[0]), str(session[2]), files, errors,
        tuple(str(row[0]) for row in aggregate_rows),
        tuple(str(row[0]) for row in project_rows), tuple(relationship_rows),
    )


def _under(path: str, root: str) -> bool:
    return root == "" or path == root or path.startswith(root + "/")


def _error_intersects(path: str, errors: tuple[str, ...]) -> bool:
    return any(_under(path, error) or _under(error, path) for error in errors)


def _file_changes(
    baseline: Snapshot, current: Snapshot
) -> list[tuple[object, ...]]:
    changes: list[tuple[object, ...]] = []
    for path in sorted(set(baseline.files) | set(current.files)):
        before = baseline.files.get(path)
        after = current.files.get(path)
        if before is None and after is not None:
            change_type = "ADDED"
            confidence = (
                "AMBIGUOUS_ERROR_REGION" if _error_intersects(path, baseline.errors)
                else "OBSERVED_CURRENT"
            )
        elif before is not None and after is None:
            change_type = "REMOVED"
            confidence = (
                "AMBIGUOUS_ERROR_REGION" if _error_intersects(path, current.errors)
                else "OBSERVED_BASELINE"
            )
        elif before is not None and after is not None:
            changed = (
                before.logical_bytes, before.modified_ns, before.attributes
            ) != (after.logical_bytes, after.modified_ns, after.attributes)
            change_type = "METADATA_CHANGED" if changed else "METADATA_UNCHANGED"
            confidence = "OBSERVED_BOTH"
        else:
            raise AssertionError("union path lacks both observations")
        changes.append((
            path, change_type, confidence,
            None if before is None else before.logical_bytes,
            None if after is None else after.logical_bytes,
            None if before is None else before.modified_ns,
            None if after is None else after.modified_ns,
            None if before is None else before.attributes,
            None if after is None else after.attributes,
        ))
    return changes


def _ancestors(path: str) -> tuple[str, ...]:
    parts = path.split("/")[:-1]
    return ("", *("/".join(parts[:index]) for index in range(1, len(parts) + 1)))


def _directory_changes(
    baseline: Snapshot, current: Snapshot, changes: list[tuple[object, ...]]
) -> list[tuple[object, ...]]:
    directories = sorted(set(baseline.directories) | set(current.directories))
    counters = {path: [0, 0, 0, 0, 0, 0] for path in directories}
    for row in changes:
        path, change_type, confidence = str(row[0]), str(row[1]), str(row[2])
        before_bytes = 0 if row[3] is None else _integer(row[3], "baseline change bytes")
        after_bytes = 0 if row[4] is None else _integer(row[4], "current change bytes")
        for directory in _ancestors(path):
            if directory not in counters:
                raise ValueError("file change path is absent from directory aggregates")
            values = counters[directory]
            if change_type == "ADDED":
                values[0] += 1
            elif change_type == "REMOVED":
                values[1] += 1
            elif change_type == "METADATA_CHANGED":
                values[2] += 1
            else:
                values[3] += 1
            if confidence == "AMBIGUOUS_ERROR_REGION":
                values[4] += 1
            values[5] += after_bytes - before_bytes
    result: list[tuple[object, ...]] = []
    for path in directories:
        added, removed, changed, unchanged, ambiguous, byte_delta = counters[path]
        denominator = added + removed + changed + unchanged
        churn = (added + removed + changed) / denominator if denominator else 0.0
        result.append((
            path, added, removed, changed, unchanged, ambiguous, byte_delta, churn,
        ))
    return result


def _assigned_project(path: str, projects: tuple[str, ...]) -> str | None:
    return next(
        (project for project in sorted(projects, key=lambda item: (-len(item), item))
         if _under(path, project)),
        None,
    )


def _project_graph(
    baseline: Snapshot,
    current: Snapshot,
    changes: list[tuple[object, ...]],
    shared_extension_threshold: float,
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]], list[tuple[object, ...]]]:
    all_projects = sorted(set(baseline.projects) | set(current.projects))
    current_files_by_project: dict[str, list[FileObservation]] = {
        project: [] for project in current.projects
    }
    for observation in current.files.values():
        project = _assigned_project(observation.relative_path, current.projects)
        if project is not None:
            current_files_by_project[project].append(observation)
    change_counts = {project: [0, 0] for project in all_projects}
    for change in changes:
        path = str(change[0])
        if change[1] == "METADATA_UNCHANGED":
            continue
        projects = current.projects if change[1] != "REMOVED" else baseline.projects
        project = _assigned_project(path, projects)
        if project is not None:
            change_counts[project][0] += 1
            if change[2] == "AMBIGUOUS_ERROR_REGION":
                change_counts[project][1] += 1
    nodes: list[tuple[object, ...]] = [(
        project,
        project,
        "RETAINED" if project in baseline.projects and project in current.projects else (
            "ADDED" if project in current.projects else "REMOVED"
        ),
        change_counts[project][0],
        change_counts[project][1],
        len(current_files_by_project.get(project, [])),
    ) for project in all_projects]
    edges: list[tuple[object, ...]] = []
    for relationship in current.relationships:
        if relationship[0] == "project" and relationship[2] == "NESTED_PROJECT" and (
            relationship[3] == "project"
        ):
            edges.append((
                str(relationship[1]), str(relationship[4]), "NESTED_PROJECT", 1, 1.0,
                json.dumps({"basis": "validated-analysis-relationship"}, separators=(",", ":")),
            ))
    extension_sets = {
        project: {item.extension.casefold() for item in observations if item.extension}
        for project, observations in current_files_by_project.items()
    }
    current_projects = sorted(current.projects)
    for index, left in enumerate(current_projects):
        for right in current_projects[index + 1:]:
            shared = sorted(extension_sets[left] & extension_sets[right])
            union = extension_sets[left] | extension_sets[right]
            similarity = len(shared) / len(union) if union else 0.0
            if shared and similarity >= shared_extension_threshold:
                edges.append((
                    left, right, "SHARED_EXTENSION_PROFILE", 0, similarity,
                    json.dumps({
                        "shared_extensions": shared,
                        "jaccard": similarity,
                        "dependency_claim": False,
                    }, sort_keys=True, separators=(",", ":")),
                ))
    edges.sort(key=lambda row: (str(row[0]), str(row[1]), str(row[2])))
    adjacency: dict[str, set[str]] = {project: set() for project in all_projects}
    for source, target, *_ in edges:
        adjacency[str(source)].add(str(target))
        adjacency[str(target)].add(str(source))
    component_by_project: dict[str, str] = {}
    for start in all_projects:
        if start in component_by_project:
            continue
        pending = [start]
        members: list[str] = []
        while pending:
            item = pending.pop()
            if item in members:
                continue
            members.append(item)
            pending.extend(sorted(adjacency[item] - set(members), reverse=True))
        component_id = _digest(sorted(members))[:16]
        component_by_project.update({member: component_id for member in members})
    features: list[tuple[object, ...]] = [(
        project, len(adjacency[project]), component_by_project[project], 0, 0, 0.0,
    ) for project in all_projects]
    return nodes, edges, features


def _stage(
    connection: sqlite3.Connection, run_id: str, name: str, input_digest: str,
    config: object, output_digest: str,
) -> None:
    connection.execute(
        "INSERT INTO longitudinal_stages VALUES(?,?,?,?,?,?,?,NULL)",
        (run_id, name, "COMPLETE", input_digest, _digest(config), output_digest, CODE_VERSION),
    )


def run_longitudinal(
    baseline_analysis_path: str | Path,
    current_analysis_path: str | Path,
    output_path: str | Path,
    *,
    baseline_analysis_run_id: str | None = None,
    current_analysis_run_id: str | None = None,
    shared_extension_threshold: float = 0.5,
) -> LongitudinalResult:
    if not 0.0 <= shared_extension_threshold <= 1.0:
        raise ValueError("shared extension threshold must be in [0,1]")
    baseline_path = Path(baseline_analysis_path).expanduser().resolve(strict=True)
    current_path = Path(current_analysis_path).expanduser().resolve(strict=True)
    destination = Path(output_path).expanduser().resolve(strict=False)
    if len({baseline_path, current_path, destination}) != 3 or any(
        path.parent != baseline_path.parent for path in (current_path, destination)
    ) or destination.exists():
        raise ValueError("baseline, current, and new output databases must be distinct siblings")
    baseline = _load_snapshot(baseline_path, baseline_analysis_run_id)
    current = _load_snapshot(current_path, current_analysis_run_id)
    if baseline.session_id == current.session_id:
        raise ValueError("longitudinal analysis requires two distinct inventory sessions")
    if baseline.source_root != current.source_root or baseline.volume_identity != current.volume_identity:
        raise ValueError("longitudinal snapshots must describe the same source root and volume")
    changes = _file_changes(baseline, current)
    directories = _directory_changes(baseline, current, changes)
    nodes, edges, graph_features = _project_graph(
        baseline, current, changes, shared_extension_threshold
    )
    input_digest = _digest([
        baseline.analysis_input_digest, baseline.analysis_output_digest,
        current.analysis_input_digest, current.analysis_output_digest,
    ])
    run_id = str(uuid4())
    output = sqlite3.connect(destination)
    try:
        output.execute("PRAGMA journal_mode=DELETE")
        output.execute("PRAGMA synchronous=FULL")
        output.executescript(SCHEMA)
        output.execute(
            "INSERT INTO longitudinal_runs VALUES(?,?,?,?,?,?,?,?,NULL,'RUNNING',?,0.0,?,NULL,NULL)",
            (run_id, str(baseline_path), baseline.analysis_run_id, str(current_path),
             current.analysis_run_id, baseline.session_id, current.session_id, input_digest,
             shared_extension_threshold, _utc()),
        )
        validation_digest = _digest([
            baseline.inventory_path.name, baseline.analysis_input_digest,
            current.inventory_path.name, current.analysis_input_digest,
        ])
        _stage(output, run_id, "validate", input_digest,
               {"same_source_root": True, "same_volume_identity": True}, validation_digest)
        output.executemany(
            "INSERT INTO file_changes VALUES(?,?,?,?,?,?,?,?,?,?)",
            [(run_id, *row) for row in changes],
        )
        change_digest = _rows_digest(changes)
        _stage(output, run_id, "file_changes", validation_digest,
               {"unchanged_semantics": "metadata-only"}, change_digest)
        output.executemany(
            "INSERT INTO directory_change_features VALUES(?,?,?,?,?,?,?,?,?)",
            [(run_id, *row) for row in directories],
        )
        directory_digest = _rows_digest(directories)
        _stage(output, run_id, "directory_changes", change_digest,
               {"churn_denominator": "union-observed-files"}, directory_digest)
        output.executemany(
            "INSERT INTO project_nodes VALUES(?,?,?,?,?,?,?)",
            [(run_id, *row) for row in nodes],
        )
        output.executemany(
            "INSERT INTO project_edges VALUES(?,?,?,?,?,?,?)",
            [(run_id, *row) for row in edges],
        )
        output.executemany(
            "INSERT INTO project_graph_features VALUES(?,?,?,?,?,?,?)",
            [(run_id, *row) for row in graph_features],
        )
        graph_digest = _digest([nodes, edges, graph_features])
        _stage(output, run_id, "project_graph", directory_digest,
               {"shared_extension_threshold": shared_extension_threshold,
                "shared_extensions_imply_dependency": False,
                "dependency_evidence_coverage": 0.0}, graph_digest)
        output_digest = _digest([validation_digest, change_digest, directory_digest, graph_digest])
        output.execute(
            "UPDATE longitudinal_runs SET output_digest=?,state='COMPLETE',finished_at=? "
            "WHERE run_id=?", (output_digest, _utc(), run_id),
        )
        output.commit()
        return LongitudinalResult(
            run_id, "COMPLETE", input_digest, output_digest, len(changes), len(nodes), len(edges)
        )
    except BaseException as exc:
        output.rollback()
        output.execute(
            "UPDATE longitudinal_runs SET state='FAILED',finished_at=?,error=? WHERE run_id=?",
            (_utc(), f"{type(exc).__name__}: {exc}", run_id),
        )
        output.commit()
        raise
    finally:
        output.close()
