"""Validate explicit project evidence and calculate a conservative dependency graph."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from rootwise_longitudinal.pipeline import LONGITUDINAL_APPLICATION_ID

DEPENDENCY_APPLICATION_ID = 1_346_654_814
CODE_VERSION = "0.12.0-alpha"
SCHEMA_ID = "rootwise-project-dependency-evidence-v1"
RELATIONSHIP_TYPES = {
    "DEPENDS_ON", "REFERENCES", "GENERATED_FROM", "EXPORTS_TO", "SHARES_ASSETS_WITH",
}
DIRECTED_TYPES = {"DEPENDS_ON", "REFERENCES", "GENERATED_FROM", "EXPORTS_TO"}
SCHEMA = """
PRAGMA application_id=1346654814;
CREATE TABLE dependency_runs (
 run_id TEXT PRIMARY KEY, longitudinal_path TEXT NOT NULL,
 longitudinal_run_id TEXT NOT NULL, evidence_manifest_path TEXT NOT NULL,
 longitudinal_output_digest TEXT NOT NULL, manifest_digest TEXT NOT NULL,
 input_digest TEXT NOT NULL, output_digest TEXT, state TEXT NOT NULL,
 project_count INTEGER NOT NULL, evaluated_project_count INTEGER NOT NULL,
 dependency_evidence_coverage REAL NOT NULL, started_at TEXT NOT NULL,
 finished_at TEXT, error TEXT
);
CREATE TABLE dependency_stages (
 run_id TEXT NOT NULL, stage_name TEXT NOT NULL, state TEXT NOT NULL,
 input_digest TEXT NOT NULL, config_digest TEXT NOT NULL, output_digest TEXT NOT NULL,
 code_version TEXT NOT NULL, error TEXT, PRIMARY KEY(run_id,stage_name)
);
CREATE TABLE evaluated_projects (
 run_id TEXT NOT NULL, project_id TEXT NOT NULL, PRIMARY KEY(run_id,project_id)
);
CREATE TABLE dependency_edges (
 run_id TEXT NOT NULL, evidence_id TEXT NOT NULL, source_project TEXT NOT NULL,
 target_project TEXT NOT NULL, relationship_type TEXT NOT NULL, directed INTEGER NOT NULL,
 confidence REAL NOT NULL, evidence_reference TEXT NOT NULL,
 PRIMARY KEY(run_id,evidence_id),
 UNIQUE(run_id,source_project,target_project,relationship_type)
);
CREATE TABLE dependency_graph_features (
 run_id TEXT NOT NULL, project_id TEXT NOT NULL, evidence_state TEXT NOT NULL,
 dependency_in_degree INTEGER NOT NULL, dependency_out_degree INTEGER NOT NULL,
 relationship_degree INTEGER NOT NULL, weighted_dependency_in REAL NOT NULL,
 weighted_dependency_out REAL NOT NULL, pagerank REAL NOT NULL,
 dependency_cut_risk INTEGER NOT NULL, component_id TEXT NOT NULL,
 PRIMARY KEY(run_id,project_id)
);
"""


@dataclass(frozen=True)
class EvidenceEdge:
    evidence_id: str
    source: str
    target: str
    relationship_type: str
    confidence: float
    evidence_reference: str


@dataclass(frozen=True)
class DependencyResult:
    run_id: str
    state: str
    input_digest: str
    output_digest: str
    project_count: int
    evaluated_project_count: int
    edge_count: int
    dependency_evidence_coverage: float


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _rows_digest(rows: list[tuple[object, ...]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")
    return digest.hexdigest()


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 500:
        raise ValueError(f"{label} must be a non-empty bounded string")
    return value


def _open_longitudinal(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        if connection.execute("PRAGMA application_id").fetchone()[0] != LONGITUDINAL_APPLICATION_ID:
            raise ValueError("longitudinal database application identity mismatch")
    except BaseException:
        connection.close()
        raise
    return connection


def _read_longitudinal(
    path: Path, requested_run_id: str | None
) -> tuple[str, str, list[str]]:
    connection = _open_longitudinal(path)
    try:
        if requested_run_id is None:
            run = connection.execute(
                "SELECT run_id,output_digest,state FROM longitudinal_runs WHERE state='COMPLETE' "
                "ORDER BY finished_at DESC,run_id DESC LIMIT 1"
            ).fetchone()
        else:
            run = connection.execute(
                "SELECT run_id,output_digest,state FROM longitudinal_runs WHERE run_id=?",
                (requested_run_id,),
            ).fetchone()
        if run is None or run[1] is None or run[2] != "COMPLETE":
            raise ValueError("dependency analysis requires a COMPLETE longitudinal run")
        run_id, recorded_output = str(run[0]), str(run[1])
        stage_rows = [tuple(row) for row in connection.execute(
            "SELECT stage_name,state,output_digest FROM longitudinal_stages WHERE run_id=? "
            "ORDER BY stage_name", (run_id,),
        )]
        if {(str(row[0]), str(row[1])) for row in stage_rows} != {
            ("validate", "COMPLETE"), ("file_changes", "COMPLETE"),
            ("directory_changes", "COMPLETE"), ("project_graph", "COMPLETE"),
        }:
            raise ValueError("longitudinal prerequisite stages are incomplete or mismatched")
        queries = {
            "file_changes": "SELECT relative_path,change_type,confidence_state,baseline_logical_bytes,current_logical_bytes,baseline_modified_ns,current_modified_ns,baseline_attributes,current_attributes FROM file_changes WHERE run_id=? ORDER BY relative_path",
            "directory_changes": "SELECT relative_path,added_count,removed_count,metadata_changed_count,metadata_unchanged_count,ambiguous_count,logical_bytes_delta,churn_ratio FROM directory_change_features WHERE run_id=? ORDER BY relative_path",
        }
        recomputed: dict[str, str] = {}
        for name, query in queries.items():
            rows = [tuple(row) for row in connection.execute(query, (run_id,))]
            recomputed[name] = _rows_digest(rows)
        nodes = [tuple(row) for row in connection.execute(
            "SELECT project_id,relative_path,temporal_state,changed_file_count,ambiguous_file_count,current_file_count FROM project_nodes WHERE run_id=? ORDER BY project_id",
            (run_id,),
        )]
        edges = [tuple(row) for row in connection.execute(
            "SELECT source_id,target_id,relationship_type,directed,confidence,evidence_json FROM project_edges WHERE run_id=? ORDER BY source_id,target_id,relationship_type",
            (run_id,),
        )]
        features = [tuple(row) for row in connection.execute(
            "SELECT project_id,degree,component_id,dependency_in_degree,dependency_out_degree,dependency_evidence_coverage FROM project_graph_features WHERE run_id=? ORDER BY project_id",
            (run_id,),
        )]
        recomputed["project_graph"] = _digest([nodes, edges, features])
        stored = {str(row[0]): str(row[2]) for row in stage_rows}
        for name, value in recomputed.items():
            if stored[name] != value:
                raise ValueError(f"longitudinal {name} logical digest mismatch")
        calculated_output = _digest([
            stored["validate"], stored["file_changes"],
            stored["directory_changes"], stored["project_graph"],
        ])
        if calculated_output != recorded_output:
            raise ValueError("longitudinal logical output digest mismatch")
        projects = sorted(str(row[0]) for row in nodes if str(row[2]) != "REMOVED")
        return run_id, recorded_output, projects
    finally:
        connection.close()


def _load_manifest(
    path: Path, run_id: str, output_digest: str, projects: list[str]
) -> tuple[str, list[str], list[EvidenceEdge]]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {
        "schema", "longitudinal_run_id", "longitudinal_output_digest", "producer",
        "created_at", "evaluated_projects", "relationships",
    }:
        raise ValueError("evidence manifest keys do not match the required schema")
    if value["schema"] != SCHEMA_ID:
        raise ValueError("evidence manifest schema mismatch")
    if raw != _canonical(value) + b"\n":
        raise ValueError("evidence manifest must use canonical JSON encoding")
    if value["longitudinal_run_id"] != run_id or value["longitudinal_output_digest"] != output_digest:
        raise ValueError("evidence manifest longitudinal binding mismatch")
    _require_string(value["producer"], "producer")
    _require_string(value["created_at"], "created_at")
    evaluated_value = value["evaluated_projects"]
    if not isinstance(evaluated_value, list):
        raise ValueError("evaluated_projects must be a sorted list")
    evaluated = [_require_string(item, "evaluated project") for item in evaluated_value]
    if evaluated != sorted(set(evaluated)):
        raise ValueError("evaluated_projects must be sorted and unique")
    if not set(evaluated) <= set(projects):
        raise ValueError("evidence manifest evaluates an unknown or removed project")
    relationships = value["relationships"]
    if not isinstance(relationships, list):
        raise ValueError("relationships must be a list")
    parsed: list[EvidenceEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for item in relationships:
        if not isinstance(item, dict) or set(item) != {
            "evidence_id", "source_project", "target_project", "relationship_type",
            "confidence", "evidence_reference",
        }:
            raise ValueError("relationship keys do not match the required schema")
        evidence_id = _require_string(item["evidence_id"], "evidence_id")
        source = _require_string(item["source_project"], "source_project")
        target = _require_string(item["target_project"], "target_project")
        relationship_type = _require_string(item["relationship_type"], "relationship_type")
        reference = _require_string(item["evidence_reference"], "evidence_reference")
        confidence = item["confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise ValueError("relationship confidence must be numeric in [0,1]")
        if relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError("unsupported project relationship type")
        if source == target or source not in evaluated or target not in evaluated:
            raise ValueError("relationship endpoints must be distinct evaluated projects")
        if relationship_type == "SHARES_ASSETS_WITH" and source > target:
            raise ValueError("undirected relationship endpoints must be canonically ordered")
        key = (source, target, relationship_type)
        if key in seen_edges:
            raise ValueError("duplicate project relationship")
        seen_edges.add(key)
        parsed.append(EvidenceEdge(evidence_id, source, target, relationship_type, float(confidence), reference))
    if [edge.evidence_id for edge in parsed] != sorted({edge.evidence_id for edge in parsed}):
        raise ValueError("relationships must have sorted unique evidence IDs")
    return hashlib.sha256(raw).hexdigest(), evaluated, parsed


def _components(projects: list[str], adjacency: dict[str, set[str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for start in projects:
        if start in result:
            continue
        pending = [start]
        members: set[str] = set()
        while pending:
            item = pending.pop()
            if item in members:
                continue
            members.add(item)
            pending.extend(sorted(adjacency[item] - members, reverse=True))
        identifier = _digest(sorted(members))[:16]
        result.update({member: identifier for member in members})
    return result


def _component_count(members: set[str], adjacency: dict[str, set[str]]) -> int:
    remaining = set(members)
    count = 0
    while remaining:
        count += 1
        pending = [min(remaining)]
        while pending:
            item = pending.pop()
            if item not in remaining:
                continue
            remaining.remove(item)
            pending.extend(sorted(adjacency[item] & remaining, reverse=True))
    return count


def _graph_features(
    projects: list[str], evaluated: list[str], edges: list[EvidenceEdge]
) -> list[tuple[object, ...]]:
    adjacency: dict[str, set[str]] = {project: set() for project in projects}
    incoming: dict[str, list[EvidenceEdge]] = {project: [] for project in projects}
    outgoing: dict[str, list[EvidenceEdge]] = {project: [] for project in projects}
    relation_neighbors: dict[str, set[str]] = {project: set() for project in projects}
    for edge in edges:
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)
        relation_neighbors[edge.source].add(edge.target)
        relation_neighbors[edge.target].add(edge.source)
        if edge.relationship_type == "DEPENDS_ON":
            outgoing[edge.source].append(edge)
            incoming[edge.target].append(edge)
    components = _components(projects, adjacency)
    count = len(projects)
    ranks = {project: (1.0 / count if count else 0.0) for project in projects}
    for _ in range(100):
        dangling = sum(ranks[project] for project in projects if not outgoing[project])
        updated = {project: (0.15 / count if count else 0.0) + 0.85 * dangling / count for project in projects}
        for source in projects:
            if outgoing[source]:
                share = 0.85 * ranks[source] / len(outgoing[source])
                for edge in outgoing[source]:
                    updated[edge.target] += share
        if max((abs(updated[item] - ranks[item]) for item in projects), default=0.0) < 1e-12:
            ranks = updated
            break
        ranks = updated
    evaluated_set = set(evaluated)
    rows: list[tuple[object, ...]] = []
    for project in projects:
        component_members = {item for item in projects if components[item] == components[project]}
        baseline = _component_count(component_members, adjacency)
        without = component_members - {project}
        cut_risk = max(0, _component_count(without, adjacency) - baseline) if without else 0
        rows.append((
            project, "EVALUATED" if project in evaluated_set else "NOT_EVALUATED",
            len(incoming[project]), len(outgoing[project]), len(relation_neighbors[project]),
            sum(edge.confidence for edge in incoming[project]),
            sum(edge.confidence for edge in outgoing[project]), ranks[project], cut_risk,
            components[project],
        ))
    return rows


def _stage(
    connection: sqlite3.Connection, run_id: str, name: str, input_digest: str,
    config: object, output_digest: str,
) -> None:
    connection.execute(
        "INSERT INTO dependency_stages VALUES(?,?,?,?,?,?,?,NULL)",
        (run_id, name, "COMPLETE", input_digest, _digest(config), output_digest, CODE_VERSION),
    )


def run_dependency_analysis(
    longitudinal_path: str | Path,
    evidence_manifest_path: str | Path,
    output_path: str | Path,
    *,
    longitudinal_run_id: str | None = None,
) -> DependencyResult:
    longitudinal = Path(longitudinal_path).expanduser().resolve(strict=True)
    manifest = Path(evidence_manifest_path).expanduser().resolve(strict=True)
    output_path_value = Path(output_path).expanduser().resolve(strict=False)
    if len({longitudinal, manifest, output_path_value}) != 3 or any(
        path.parent != longitudinal.parent for path in (manifest, output_path_value)
    ) or output_path_value.exists():
        raise ValueError("longitudinal, manifest, and new output must be distinct siblings")
    selected_run, longitudinal_digest, projects = _read_longitudinal(
        longitudinal, longitudinal_run_id
    )
    manifest_digest, evaluated, edges = _load_manifest(
        manifest, selected_run, longitudinal_digest, projects
    )
    features = _graph_features(projects, evaluated, edges)
    coverage = len(evaluated) / len(projects) if projects else 0.0
    input_digest = _digest([longitudinal_digest, manifest_digest])
    run_id = str(uuid4())
    database = sqlite3.connect(output_path_value)
    try:
        database.execute("PRAGMA journal_mode=DELETE")
        database.execute("PRAGMA synchronous=FULL")
        database.executescript(SCHEMA)
        database.execute(
            "INSERT INTO dependency_runs VALUES(?,?,?,?,?,?,?,NULL,'RUNNING',?,?,?,?,NULL,NULL)",
            (run_id, str(longitudinal), selected_run, str(manifest), longitudinal_digest,
             manifest_digest, input_digest, len(projects), len(evaluated), coverage, _utc()),
        )
        validate_digest = _digest([selected_run, longitudinal_digest, projects])
        _stage(database, run_id, "validate", input_digest,
               {"schema": SCHEMA_ID, "missing_evidence_semantics": "unknown"}, validate_digest)
        database.executemany(
            "INSERT INTO evaluated_projects VALUES(?,?)",
            [(run_id, project) for project in evaluated],
        )
        edge_rows = [(
            edge.evidence_id, edge.source, edge.target, edge.relationship_type,
            int(edge.relationship_type in DIRECTED_TYPES), edge.confidence,
            edge.evidence_reference,
        ) for edge in edges]
        database.executemany(
            "INSERT INTO dependency_edges VALUES(?,?,?,?,?,?,?,?)",
            [(run_id, *row) for row in edge_rows],
        )
        import_digest = _digest([evaluated, edge_rows])
        _stage(database, run_id, "import_evidence", validate_digest,
               {"relationship_types": sorted(RELATIONSHIP_TYPES)}, import_digest)
        database.executemany(
            "INSERT INTO dependency_graph_features VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            [(run_id, *row) for row in features],
        )
        graph_digest = _rows_digest(features)
        _stage(database, run_id, "graph_features", import_digest,
               {"pagerank_damping": 0.85, "dependency_relation": "DEPENDS_ON"}, graph_digest)
        output_digest = _digest([validate_digest, import_digest, graph_digest])
        database.execute(
            "UPDATE dependency_runs SET output_digest=?,state='COMPLETE',finished_at=? WHERE run_id=?",
            (output_digest, _utc(), run_id),
        )
        database.commit()
        return DependencyResult(
            run_id, "COMPLETE", input_digest, output_digest, len(projects), len(evaluated),
            len(edges), coverage,
        )
    except BaseException as exc:
        database.rollback()
        database.execute(
            "UPDATE dependency_runs SET state='FAILED',finished_at=?,error=? WHERE run_id=?",
            (_utc(), f"{type(exc).__name__}: {exc}", run_id),
        )
        database.commit()
        raise
    finally:
        database.close()
