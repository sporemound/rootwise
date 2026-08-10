"""Validate a contiguous longitudinal chain and derive ordinal temporal features."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from paretodrive_longitudinal.pipeline import LONGITUDINAL_APPLICATION_ID

HISTORY_APPLICATION_ID = 1_346_654_815
CODE_VERSION = "0.13.0-alpha"
SCHEMA_ID = "paretodrive-longitudinal-chain-v1"
SCHEMA = """
PRAGMA application_id=1346654815;
CREATE TABLE history_runs (
 run_id TEXT PRIMARY KEY, chain_manifest_path TEXT NOT NULL, manifest_digest TEXT NOT NULL,
 input_digest TEXT NOT NULL, output_digest TEXT, state TEXT NOT NULL,
 snapshot_count INTEGER NOT NULL, transition_count INTEGER NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, error TEXT
);
CREATE TABLE history_stages (
 run_id TEXT NOT NULL, stage_name TEXT NOT NULL, state TEXT NOT NULL,
 input_digest TEXT NOT NULL, config_digest TEXT NOT NULL, output_digest TEXT NOT NULL,
 code_version TEXT NOT NULL, error TEXT, PRIMARY KEY(run_id,stage_name)
);
CREATE TABLE history_links (
 run_id TEXT NOT NULL, transition_ordinal INTEGER NOT NULL, longitudinal_path TEXT NOT NULL,
 longitudinal_run_id TEXT NOT NULL, longitudinal_output_digest TEXT NOT NULL,
 baseline_session_id TEXT NOT NULL, current_session_id TEXT NOT NULL,
 PRIMARY KEY(run_id,transition_ordinal)
);
CREATE TABLE file_history_features (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, first_observed_snapshot INTEGER NOT NULL,
 last_observed_snapshot INTEGER NOT NULL, observed_snapshot_count INTEGER NOT NULL,
 appearance_count INTEGER NOT NULL, disappearance_count INTEGER NOT NULL,
 metadata_change_count INTEGER NOT NULL, metadata_unchanged_count INTEGER NOT NULL,
 longest_stable_transition_run INTEGER NOT NULL, observation_ratio REAL NOT NULL,
 ambiguous_transition_count INTEGER NOT NULL, current_observation_state TEXT NOT NULL,
 PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE directory_history_features (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, covered_transition_count INTEGER NOT NULL,
 total_added_count INTEGER NOT NULL, total_removed_count INTEGER NOT NULL,
 total_metadata_changed_count INTEGER NOT NULL, total_ambiguous_count INTEGER NOT NULL,
 cumulative_logical_bytes_delta INTEGER NOT NULL, mean_churn_ratio REAL NOT NULL,
 maximum_churn_ratio REAL NOT NULL, PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE project_history_features (
 run_id TEXT NOT NULL, project_id TEXT NOT NULL, covered_transition_count INTEGER NOT NULL,
 active_transition_count INTEGER NOT NULL, appearance_count INTEGER NOT NULL,
 disappearance_count INTEGER NOT NULL, total_changed_file_count INTEGER NOT NULL,
 total_ambiguous_file_count INTEGER NOT NULL, activity_ratio REAL NOT NULL,
 current_observation_state TEXT NOT NULL, PRIMARY KEY(run_id,project_id)
);
"""


@dataclass(frozen=True)
class Link:
    path: Path
    run_id: str
    output_digest: str
    baseline_analysis_path: str
    baseline_analysis_run_id: str
    current_analysis_path: str
    current_analysis_run_id: str
    baseline_session_id: str
    current_session_id: str
    file_changes: list[tuple[object, ...]]
    directory_changes: list[tuple[object, ...]]
    project_nodes: list[tuple[object, ...]]


@dataclass(frozen=True)
class HistoryResult:
    run_id: str
    state: str
    input_digest: str
    output_digest: str
    snapshot_count: int
    transition_count: int
    file_count: int
    directory_count: int
    project_count: int


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _rows_digest(rows: Sequence[tuple[object, ...]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")
    return digest.hexdigest()


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 500:
        raise ValueError(f"{label} must be a non-empty bounded string")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _real(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _open(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        if connection.execute("PRAGMA application_id").fetchone()[0] != LONGITUDINAL_APPLICATION_ID:
            raise ValueError("history input is not a longitudinal database")
    except BaseException:
        connection.close()
        raise
    return connection


def _read_link(path: Path, requested_run: str, requested_digest: str) -> Link:
    connection = _open(path)
    try:
        run = connection.execute(
            "SELECT run_id,baseline_analysis_path,baseline_analysis_run_id,current_analysis_path,"
            "current_analysis_run_id,baseline_session_id,current_session_id,output_digest,state "
            "FROM longitudinal_runs WHERE run_id=?", (requested_run,),
        ).fetchone()
        if run is None or run[7] is None or run[8] != "COMPLETE":
            raise ValueError("history requires a COMPLETE longitudinal run")
        if str(run[7]) != requested_digest:
            raise ValueError("chain manifest longitudinal output digest mismatch")
        stage_rows = [tuple(row) for row in connection.execute(
            "SELECT stage_name,state,output_digest FROM longitudinal_stages WHERE run_id=? "
            "ORDER BY stage_name", (requested_run,),
        )]
        if {(str(row[0]), str(row[1])) for row in stage_rows} != {
            ("validate", "COMPLETE"), ("file_changes", "COMPLETE"),
            ("directory_changes", "COMPLETE"), ("project_graph", "COMPLETE"),
        }:
            raise ValueError("longitudinal prerequisite stages are incomplete or mismatched")
        file_changes = [tuple(row) for row in connection.execute(
            "SELECT relative_path,change_type,confidence_state,baseline_logical_bytes,"
            "current_logical_bytes,baseline_modified_ns,current_modified_ns,baseline_attributes,"
            "current_attributes FROM file_changes WHERE run_id=? ORDER BY relative_path",
            (requested_run,),
        )]
        directory_changes = [tuple(row) for row in connection.execute(
            "SELECT relative_path,added_count,removed_count,metadata_changed_count,"
            "metadata_unchanged_count,ambiguous_count,logical_bytes_delta,churn_ratio "
            "FROM directory_change_features WHERE run_id=? ORDER BY relative_path",
            (requested_run,),
        )]
        project_nodes = [tuple(row) for row in connection.execute(
            "SELECT project_id,relative_path,temporal_state,changed_file_count,"
            "ambiguous_file_count,current_file_count FROM project_nodes WHERE run_id=? "
            "ORDER BY project_id", (requested_run,),
        )]
        edges = [tuple(row) for row in connection.execute(
            "SELECT source_id,target_id,relationship_type,directed,confidence,evidence_json "
            "FROM project_edges WHERE run_id=? ORDER BY source_id,target_id,relationship_type",
            (requested_run,),
        )]
        graph_features = [tuple(row) for row in connection.execute(
            "SELECT project_id,degree,component_id,dependency_in_degree,dependency_out_degree,"
            "dependency_evidence_coverage FROM project_graph_features WHERE run_id=? "
            "ORDER BY project_id", (requested_run,),
        )]
        stored = {str(row[0]): str(row[2]) for row in stage_rows}
        recomputed = {
            "file_changes": _rows_digest(file_changes),
            "directory_changes": _rows_digest(directory_changes),
            "project_graph": _digest([project_nodes, edges, graph_features]),
        }
        for stage, digest in recomputed.items():
            if stored[stage] != digest:
                raise ValueError(f"longitudinal {stage} logical digest mismatch")
        if _digest([
            stored["validate"], stored["file_changes"],
            stored["directory_changes"], stored["project_graph"],
        ]) != requested_digest:
            raise ValueError("longitudinal logical output digest mismatch")
        return Link(
            path, str(run[0]), requested_digest, str(run[1]), str(run[2]), str(run[3]),
            str(run[4]), str(run[5]), str(run[6]), file_changes, directory_changes,
            project_nodes,
        )
    finally:
        connection.close()


def validate_longitudinal_link(
    path: str | Path, run_id: str, output_digest: str
) -> Link:
    """Independently validate and return one complete longitudinal link."""
    return _read_link(Path(path).expanduser().resolve(strict=True), run_id, output_digest)


def _load_chain(manifest: Path, output: Path) -> tuple[str, list[Link]]:
    raw = manifest.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"schema", "created_at", "label", "links"}:
        raise ValueError("history chain manifest keys do not match the required schema")
    if value["schema"] != SCHEMA_ID:
        raise ValueError("history chain manifest schema mismatch")
    if raw != _canonical(value) + b"\n":
        raise ValueError("history chain manifest must use canonical JSON encoding")
    _string(value["created_at"], "created_at")
    _string(value["label"], "label")
    items = value["links"]
    if not isinstance(items, list) or len(items) < 2 or len(items) > 10_000:
        raise ValueError("history chain requires between 2 and 10000 transitions")
    links: list[Link] = []
    seen_paths: set[Path] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"database", "run_id", "output_digest"}:
            raise ValueError("history chain link keys do not match the required schema")
        database_name = _string(item["database"], "database")
        if Path(database_name).name != database_name or "/" in database_name or "\\" in database_name:
            raise ValueError("history chain database must be a sibling filename")
        path = (manifest.parent / database_name).resolve(strict=True)
        if path.parent != manifest.parent or path == output or path in seen_paths:
            raise ValueError("history chain databases must be unique input siblings")
        seen_paths.add(path)
        links.append(_read_link(
            path, _string(item["run_id"], "run_id"),
            _string(item["output_digest"], "output_digest"),
        ))
    for previous, current in zip(links, links[1:], strict=False):
        same_analysis = (
            Path(previous.current_analysis_path).resolve()
            == Path(current.baseline_analysis_path).resolve()
            and previous.current_analysis_run_id == current.baseline_analysis_run_id
        )
        if previous.current_session_id != current.baseline_session_id or not same_analysis:
            raise ValueError("longitudinal links do not form a contiguous snapshot chain")
    return hashlib.sha256(raw).hexdigest(), links


def _file_features(links: list[Link]) -> list[tuple[object, ...]]:
    changes = [{str(row[0]): row for row in link.file_changes} for link in links]
    paths = sorted(set().union(*(set(item) for item in changes)))
    result: list[tuple[object, ...]] = []
    for path in paths:
        states: list[str] = []
        appearances = disappearances = changed = unchanged = ambiguous = 0
        stable_run = longest_stable = 0
        for ordinal, mapping in enumerate(changes):
            row = mapping.get(path)
            kind = None if row is None else str(row[1])
            is_ambiguous = row is not None and row[2] == "AMBIGUOUS_ERROR_REGION"
            if kind == "ADDED":
                before = "AMBIGUOUS_NOT_OBSERVED" if is_ambiguous else "NOT_OBSERVED"
                after = "OBSERVED"
            elif kind == "REMOVED":
                before = "OBSERVED"
                after = "AMBIGUOUS_NOT_OBSERVED" if is_ambiguous else "NOT_OBSERVED"
            elif kind in ("METADATA_CHANGED", "METADATA_UNCHANGED"):
                before = after = "OBSERVED"
            elif kind is None:
                before = after = "NOT_OBSERVED"
            else:
                raise ValueError("unsupported longitudinal file change type")
            if ordinal == 0:
                states.append(before)
            elif states[-1] != before:
                if states[-1] == "AMBIGUOUS_NOT_OBSERVED":
                    states[-1] = before
                elif before != "AMBIGUOUS_NOT_OBSERVED":
                    raise ValueError(
                        "file observation state is inconsistent across contiguous transitions"
                    )
            states.append(after)
            if kind == "ADDED" and not is_ambiguous:
                appearances += 1
            elif kind == "REMOVED" and not is_ambiguous:
                disappearances += 1
            elif kind == "METADATA_CHANGED":
                changed += 1
            elif kind == "METADATA_UNCHANGED":
                unchanged += 1
            if is_ambiguous:
                ambiguous += 1
            if kind == "METADATA_UNCHANGED":
                stable_run += 1
                longest_stable = max(longest_stable, stable_run)
            else:
                stable_run = 0
        observed = [index for index, state in enumerate(states) if state == "OBSERVED"]
        if not observed:
            raise ValueError("history file path was never observed")
        result.append((
            path, observed[0], observed[-1], len(observed), appearances, disappearances,
            changed, unchanged, longest_stable, len(observed) / len(states), ambiguous,
            states[-1],
        ))
    return result


def _directory_features(links: list[Link]) -> list[tuple[object, ...]]:
    by_path: dict[str, list[tuple[object, ...]]] = {}
    for link in links:
        for row in link.directory_changes:
            by_path.setdefault(str(row[0]), []).append(row)
    result: list[tuple[object, ...]] = []
    for path in sorted(by_path):
        rows = by_path[path]
        churn = [_real(row[7], "directory churn ratio") for row in rows]
        result.append((
            path, len(rows), sum(_integer(row[1], "added count") for row in rows),
            sum(_integer(row[2], "removed count") for row in rows),
            sum(_integer(row[3], "metadata changed count") for row in rows),
            sum(_integer(row[5], "ambiguous count") for row in rows),
            sum(_integer(row[6], "logical bytes delta") for row in rows),
            sum(churn) / len(churn), max(churn),
        ))
    return result


def _project_features(links: list[Link]) -> list[tuple[object, ...]]:
    by_path: dict[str, list[tuple[int, tuple[object, ...]]]] = {}
    for ordinal, link in enumerate(links):
        for row in link.project_nodes:
            by_path.setdefault(str(row[0]), []).append((ordinal, row))
    result: list[tuple[object, ...]] = []
    last_ordinal = len(links) - 1
    for project in sorted(by_path):
        indexed = by_path[project]
        rows = [item[1] for item in indexed]
        active = sum(_integer(row[3], "project changed file count") > 0 for row in rows)
        latest = next((row for ordinal, row in reversed(indexed) if ordinal == last_ordinal), None)
        current_state = (
            "OBSERVED" if latest is not None and str(latest[2]) != "REMOVED"
            else "NOT_OBSERVED"
        )
        result.append((
            project, len(rows), active, sum(str(row[2]) == "ADDED" for row in rows),
            sum(str(row[2]) == "REMOVED" for row in rows),
            sum(_integer(row[3], "project changed file count") for row in rows),
            sum(_integer(row[4], "project ambiguous file count") for row in rows),
            active / len(rows), current_state,
        ))
    return result


def _stage(
    connection: sqlite3.Connection, run_id: str, name: str, input_digest: str,
    config: object, output_digest: str,
) -> None:
    connection.execute(
        "INSERT INTO history_stages VALUES(?,?,?,?,?,?,?,NULL)",
        (run_id, name, "COMPLETE", input_digest, _digest(config), output_digest, CODE_VERSION),
    )


def run_history_analysis(
    chain_manifest_path: str | Path, output_path: str | Path
) -> HistoryResult:
    manifest = Path(chain_manifest_path).expanduser().resolve(strict=True)
    destination = Path(output_path).expanduser().resolve(strict=False)
    if destination.parent != manifest.parent or destination == manifest or destination.exists():
        raise ValueError("chain manifest and new output must be distinct siblings")
    manifest_digest, links = _load_chain(manifest, destination)
    input_digest = _digest([manifest_digest, [link.output_digest for link in links]])
    files = _file_features(links)
    directories = _directory_features(links)
    projects = _project_features(links)
    run_id = str(uuid4())
    database = sqlite3.connect(destination)
    try:
        database.execute("PRAGMA journal_mode=DELETE")
        database.execute("PRAGMA synchronous=FULL")
        database.executescript(SCHEMA)
        database.execute(
            "INSERT INTO history_runs VALUES(?,?,?,?,NULL,'RUNNING',?,?,?,NULL,NULL)",
            (run_id, str(manifest), manifest_digest, input_digest, len(links) + 1,
             len(links), _utc()),
        )
        link_rows = [(
            ordinal, str(link.path), link.run_id, link.output_digest,
            link.baseline_session_id, link.current_session_id,
        ) for ordinal, link in enumerate(links)]
        database.executemany(
            "INSERT INTO history_links VALUES(?,?,?,?,?,?,?)",
            [(run_id, *row) for row in link_rows],
        )
        validation_digest = _rows_digest(link_rows)
        _stage(database, run_id, "validate_chain", input_digest,
               {"minimum_transitions": 2, "contiguous": True}, validation_digest)
        database.executemany(
            "INSERT INTO file_history_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(run_id, *row) for row in files],
        )
        file_digest = _rows_digest(files)
        _stage(database, run_id, "file_history", validation_digest,
               {"rename_inference": False, "time_axis": "snapshot_ordinal"}, file_digest)
        database.executemany(
            "INSERT INTO directory_history_features VALUES(?,?,?,?,?,?,?,?,?,?)",
            [(run_id, *row) for row in directories],
        )
        database.executemany(
            "INSERT INTO project_history_features VALUES(?,?,?,?,?,?,?,?,?,?)",
            [(run_id, *row) for row in projects],
        )
        aggregate_digest = _digest([directories, projects])
        _stage(database, run_id, "aggregate_history", file_digest,
               {"activity_implies_value": False, "churn_implies_value": False}, aggregate_digest)
        output_digest = _digest([validation_digest, file_digest, aggregate_digest])
        database.execute(
            "UPDATE history_runs SET output_digest=?,state='COMPLETE',finished_at=? WHERE run_id=?",
            (output_digest, _utc(), run_id),
        )
        database.commit()
        return HistoryResult(
            run_id, "COMPLETE", input_digest, output_digest, len(links) + 1, len(links),
            len(files), len(directories), len(projects),
        )
    except BaseException as exc:
        database.rollback()
        database.execute(
            "UPDATE history_runs SET state='FAILED',finished_at=?,error=? WHERE run_id=?",
            (_utc(), f"{type(exc).__name__}: {exc}", run_id),
        )
        database.commit()
        raise
    finally:
        database.close()
