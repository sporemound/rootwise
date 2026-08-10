"""Join independently validated evidence dimensions without reranking or scoring them."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from paretodrive_analytics.pipeline import ANALYSIS_APPLICATION_ID
from paretodrive_analytics.ranking_pipeline import RANKING_APPLICATION_ID
from paretodrive_dependency.pipeline import DEPENDENCY_APPLICATION_ID
from paretodrive_fusion.pipeline import FUSION_APPLICATION_ID
from paretodrive_history.pipeline import HISTORY_APPLICATION_ID, validate_longitudinal_link

SYNTHESIS_APPLICATION_ID = 1_346_654_816
CODE_VERSION = "0.14.0-alpha"
SCHEMA = """
PRAGMA application_id=1346654816;
CREATE TABLE synthesis_runs (
 run_id TEXT PRIMARY KEY, ranking_path TEXT NOT NULL, ranking_run_id TEXT NOT NULL,
 fusion_path TEXT NOT NULL, fusion_run_id TEXT NOT NULL,
 dependency_path TEXT NOT NULL, dependency_run_id TEXT NOT NULL,
 history_path TEXT NOT NULL, history_run_id TEXT NOT NULL,
 analysis_path TEXT NOT NULL, analysis_run_id TEXT NOT NULL, scan_session_id TEXT NOT NULL,
 input_digest TEXT NOT NULL, output_digest TEXT, state TEXT NOT NULL,
 candidate_count INTEGER NOT NULL, signal_count INTEGER NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, error TEXT
);
CREATE TABLE synthesis_stages (
 run_id TEXT NOT NULL, stage_name TEXT NOT NULL, state TEXT NOT NULL,
 input_digest TEXT NOT NULL, config_digest TEXT NOT NULL, output_digest TEXT NOT NULL,
 code_version TEXT NOT NULL, error TEXT, PRIMARY KEY(run_id,stage_name)
);
CREATE TABLE candidate_evidence (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, project_id TEXT,
 enrichment_coverage REAL NOT NULL, selected_file_count INTEGER NOT NULL,
 candidate_duplicate_member_count INTEGER NOT NULL,
 confirmed_duplicate_member_count INTEGER NOT NULL,
 confirmed_member_ratio_of_selected REAL NOT NULL,
 dependency_evidence_state TEXT NOT NULL, dependency_in_degree INTEGER NOT NULL,
 dependency_out_degree INTEGER NOT NULL, relationship_degree INTEGER NOT NULL,
 dependency_pagerank REAL NOT NULL, dependency_cut_risk INTEGER NOT NULL,
 history_covered_transition_count INTEGER NOT NULL,
 history_total_ambiguous_count INTEGER NOT NULL, history_mean_churn_ratio REAL NOT NULL,
 history_maximum_churn_ratio REAL NOT NULL, project_activity_ratio REAL,
 project_history_ambiguous_count INTEGER,
 PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE review_signals (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, signal_type TEXT NOT NULL,
 evidence_json TEXT NOT NULL, PRIMARY KEY(run_id,relative_path,signal_type)
);
"""


@dataclass(frozen=True)
class InputSnapshot:
    path: Path
    run_id: str
    output_digest: str
    stages: dict[str, str]


@dataclass(frozen=True)
class RankingSnapshot(InputSnapshot):
    analysis_path: Path
    analysis_run_id: str
    analysis_input_digest: str
    candidates: list[str]


@dataclass(frozen=True)
class FusionSnapshot(InputSnapshot):
    analysis_path: Path
    analysis_run_id: str
    scan_session_id: str
    features: dict[str, tuple[object, ...]]


@dataclass(frozen=True)
class DependencySnapshot(InputSnapshot):
    longitudinal_path: Path
    longitudinal_run_id: str
    longitudinal_output_digest: str
    features: dict[str, tuple[object, ...]]


@dataclass(frozen=True)
class HistorySnapshot(InputSnapshot):
    latest_longitudinal_path: Path
    latest_longitudinal_run_id: str
    latest_longitudinal_output_digest: str
    latest_session_id: str
    directories: dict[str, tuple[object, ...]]
    projects: dict[str, tuple[object, ...]]


@dataclass(frozen=True)
class SynthesisResult:
    run_id: str
    state: str
    input_digest: str
    output_digest: str
    candidate_count: int
    signal_count: int


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


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _real(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _producer_weight(value: object, label: str) -> int | float:
    number = _real(value, label)
    return 0 if number == 0 else number


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


def _stage_map(
    connection: sqlite3.Connection, table: str, run_id: str, expected: set[str]
) -> dict[str, str]:
    rows = [tuple(row) for row in connection.execute(
        f"SELECT stage_name,state,output_digest FROM {table} WHERE run_id=? ORDER BY stage_name",
        (run_id,),
    )]
    if {(str(row[0]), str(row[1])) for row in rows} != {
        (name, "COMPLETE") for name in expected
    }:
        raise ValueError(f"{table} prerequisite stages are incomplete or mismatched")
    return {str(row[0]): str(row[2]) for row in rows}


def _read_ranking(path: Path) -> RankingSnapshot:
    connection = _open(path, RANKING_APPLICATION_ID, "ranking")
    try:
        run = connection.execute(
            "SELECT run_id,analysis_path,analysis_run_id,input_digest,output_digest,state "
            "FROM ranking_runs WHERE state='COMPLETE' "
            "ORDER BY finished_at DESC,run_id DESC LIMIT 1"
        ).fetchone()
        if run is None or run[4] is None or run[5] != "COMPLETE":
            raise ValueError("synthesis requires a COMPLETE ranking run")
        run_id = str(run[0])
        stages = _stage_map(connection, "ranking_stages", run_id,
                            {"materialize", "objectives", "pareto", "review"})
        feature_rows = [tuple(row) for row in connection.execute(
            "SELECT relative_path,cohort,recursive_bytes,file_count,preservation_ratio,"
            "unknown_ratio,role_coherence,is_project FROM directory_features WHERE run_id=? "
            "ORDER BY relative_path", (run_id,),
        )]
        objective_rows = [tuple(row) for row in connection.execute(
            "SELECT relative_path,objective_name,low,point,high,confidence "
            "FROM objective_intervals WHERE run_id=? ORDER BY relative_path,objective_name",
            (run_id,),
        )]
        pareto_rows = [tuple(row) for row in connection.execute(
            "SELECT relative_path,cohort,pareto_rank FROM pareto_results WHERE run_id=? "
            "ORDER BY relative_path", (run_id,),
        )]
        review_rows = [tuple(row) for row in connection.execute(
            "SELECT review_order,relative_path,priority,reason FROM review_queue WHERE run_id=? "
            "ORDER BY review_order", (run_id,),
        )]
        recomputed = {
            "materialize": _rows_digest(feature_rows), "objectives": _rows_digest(objective_rows),
            "pareto": _rows_digest(pareto_rows), "review": _rows_digest(review_rows),
        }
        if recomputed != stages or _digest([
            stages["materialize"], stages["objectives"], stages["pareto"], stages["review"]
        ]) != str(run[4]):
            raise ValueError("ranking logical output digest mismatch")
        analysis = Path(str(run[1])).resolve(strict=True)
        if analysis.parent != path.parent:
            raise ValueError("ranking analysis path escaped the external database directory")
        return RankingSnapshot(
            path, run_id, str(run[4]), stages, analysis, str(run[2]), str(run[3]),
            [str(row[0]) for row in feature_rows],
        )
    finally:
        connection.close()


def _read_fusion(path: Path) -> FusionSnapshot:
    connection = _open(path, FUSION_APPLICATION_ID, "fusion")
    try:
        run = connection.execute(
            "SELECT run_id,analysis_path,analysis_run_id,scan_session_id,output_digest,state "
            "FROM fusion_runs WHERE state='COMPLETE' ORDER BY finished_at DESC,run_id DESC LIMIT 1"
        ).fetchone()
        if run is None or run[4] is None or run[5] != "COMPLETE":
            raise ValueError("synthesis requires a COMPLETE fusion run")
        run_id = str(run[0])
        stages = _stage_map(connection, "fusion_stages", run_id,
                            {"validate", "import", "directory_features"})
        file_rows_without_state = [tuple(row) for row in connection.execute(
            "SELECT relative_path,evidence_level,algorithm,digest,logical_bytes,modified_ns,"
            "bytes_read FROM imported_file_evidence WHERE run_id=? ORDER BY relative_path",
            (run_id,),
        )]
        file_rows = [(*row, "COMPLETE") for row in file_rows_without_state]
        group_rows = [tuple(row) for row in connection.execute(
            "SELECT group_id,evidence_level,algorithm,digest,logical_bytes,evidence_status,"
            "member_count FROM imported_duplicate_groups WHERE run_id=? ORDER BY group_id",
            (run_id,),
        )]
        member_rows = [tuple(row) for row in connection.execute(
            "SELECT group_id,relative_path FROM imported_duplicate_members WHERE run_id=? "
            "ORDER BY group_id,relative_path", (run_id,),
        )]
        feature_rows = [tuple(row) for row in connection.execute(
            "SELECT relative_path,observed_file_count,observed_logical_bytes,selected_file_count,"
            "selected_logical_bytes,candidate_member_count,candidate_member_bytes,"
            "confirmed_member_count,confirmed_member_bytes,evidence_coverage,"
            "confirmed_member_ratio_of_selected FROM directory_evidence_features WHERE run_id=? "
            "ORDER BY relative_path", (run_id,),
        )]
        import_digest = _digest([file_rows, group_rows, member_rows])
        feature_digest = _rows_digest(feature_rows)
        if stages["import"] != import_digest or stages["directory_features"] != feature_digest or (
            _digest([stages["validate"], import_digest, feature_digest]) != str(run[4])
        ):
            raise ValueError("fusion logical output digest mismatch")
        analysis = Path(str(run[1])).resolve(strict=True)
        if analysis.parent != path.parent:
            raise ValueError("fusion analysis path escaped the external database directory")
        return FusionSnapshot(
            path, run_id, str(run[4]), stages, analysis, str(run[2]), str(run[3]),
            {str(row[0]): row for row in feature_rows},
        )
    finally:
        connection.close()


def _read_dependency(path: Path) -> DependencySnapshot:
    connection = _open(path, DEPENDENCY_APPLICATION_ID, "dependency")
    try:
        run = connection.execute(
            "SELECT run_id,longitudinal_path,longitudinal_run_id,longitudinal_output_digest,"
            "output_digest,state FROM dependency_runs WHERE state='COMPLETE' "
            "ORDER BY finished_at DESC,run_id DESC LIMIT 1"
        ).fetchone()
        if run is None or run[4] is None or run[5] != "COMPLETE":
            raise ValueError("synthesis requires a COMPLETE dependency run")
        run_id = str(run[0])
        stages = _stage_map(connection, "dependency_stages", run_id,
                            {"validate", "import_evidence", "graph_features"})
        evaluated = [str(row[0]) for row in connection.execute(
            "SELECT project_id FROM evaluated_projects WHERE run_id=? ORDER BY project_id",
            (run_id,),
        )]
        edges = [tuple(row) for row in connection.execute(
            "SELECT evidence_id,source_project,target_project,relationship_type,directed,confidence,"
            "evidence_reference FROM dependency_edges WHERE run_id=? ORDER BY evidence_id",
            (run_id,),
        )]
        persisted_features = [tuple(row) for row in connection.execute(
            "SELECT project_id,evidence_state,dependency_in_degree,dependency_out_degree,"
            "relationship_degree,weighted_dependency_in,weighted_dependency_out,pagerank,"
            "dependency_cut_risk,component_id FROM dependency_graph_features WHERE run_id=? "
            "ORDER BY project_id", (run_id,),
        )]
        features = [(
            str(row[0]), str(row[1]), _integer(row[2], "dependency in degree"),
            _integer(row[3], "dependency out degree"),
            _integer(row[4], "relationship degree"),
            _producer_weight(row[5], "weighted dependency in"),
            _producer_weight(row[6], "weighted dependency out"),
            _real(row[7], "dependency pagerank"),
            _integer(row[8], "dependency cut risk"), str(row[9]),
        ) for row in persisted_features]
        imported = _digest([evaluated, edges])
        graph = _rows_digest(features)
        if stages["import_evidence"] != imported or stages["graph_features"] != graph or (
            _digest([stages["validate"], imported, graph]) != str(run[4])
        ):
            raise ValueError("dependency logical output digest mismatch")
        longitudinal = Path(str(run[1])).resolve(strict=True)
        if longitudinal.parent != path.parent:
            raise ValueError("dependency longitudinal path escaped the external database directory")
        return DependencySnapshot(
            path, run_id, str(run[4]), stages, longitudinal, str(run[2]), str(run[3]),
            {str(row[0]): row for row in features},
        )
    finally:
        connection.close()


def _read_history(path: Path) -> HistorySnapshot:
    connection = _open(path, HISTORY_APPLICATION_ID, "history")
    try:
        run = connection.execute(
            "SELECT run_id,output_digest,state FROM history_runs WHERE state='COMPLETE' "
            "ORDER BY finished_at DESC,run_id DESC LIMIT 1"
        ).fetchone()
        if run is None or run[1] is None or run[2] != "COMPLETE":
            raise ValueError("synthesis requires a COMPLETE history run")
        run_id = str(run[0])
        stages = _stage_map(connection, "history_stages", run_id,
                            {"validate_chain", "file_history", "aggregate_history"})
        links = [tuple(row) for row in connection.execute(
            "SELECT transition_ordinal,longitudinal_path,longitudinal_run_id,"
            "longitudinal_output_digest,baseline_session_id,current_session_id "
            "FROM history_links WHERE run_id=? ORDER BY transition_ordinal", (run_id,),
        )]
        files = [tuple(row) for row in connection.execute(
            "SELECT relative_path,first_observed_snapshot,last_observed_snapshot,"
            "observed_snapshot_count,appearance_count,disappearance_count,metadata_change_count,"
            "metadata_unchanged_count,longest_stable_transition_run,observation_ratio,"
            "ambiguous_transition_count,current_observation_state FROM file_history_features "
            "WHERE run_id=? ORDER BY relative_path", (run_id,),
        )]
        directories = [tuple(row) for row in connection.execute(
            "SELECT relative_path,covered_transition_count,total_added_count,total_removed_count,"
            "total_metadata_changed_count,total_ambiguous_count,cumulative_logical_bytes_delta,"
            "mean_churn_ratio,maximum_churn_ratio FROM directory_history_features WHERE run_id=? "
            "ORDER BY relative_path", (run_id,),
        )]
        projects = [tuple(row) for row in connection.execute(
            "SELECT project_id,covered_transition_count,active_transition_count,appearance_count,"
            "disappearance_count,total_changed_file_count,total_ambiguous_file_count,activity_ratio,"
            "current_observation_state FROM project_history_features WHERE run_id=? ORDER BY project_id",
            (run_id,),
        )]
        link_digest, file_digest = _rows_digest(links), _rows_digest(files)
        aggregate_digest = _digest([directories, projects])
        if stages != {
            "validate_chain": link_digest, "file_history": file_digest,
            "aggregate_history": aggregate_digest,
        } or _digest([link_digest, file_digest, aggregate_digest]) != str(run[1]):
            raise ValueError("history logical output digest mismatch")
        if not links:
            raise ValueError("history contains no longitudinal links")
        latest = links[-1]
        longitudinal = Path(str(latest[1])).resolve(strict=True)
        if longitudinal.parent != path.parent:
            raise ValueError("history longitudinal path escaped the external database directory")
        return HistorySnapshot(
            path, run_id, str(run[1]), stages, longitudinal, str(latest[2]), str(latest[3]),
            str(latest[5]),
            {str(row[0]): row for row in directories}, {str(row[0]): row for row in projects},
        )
    finally:
        connection.close()


def _analysis_session(path: Path, run_id: str, ranking_input_digest: str) -> str:
    connection = _open(path, ANALYSIS_APPLICATION_ID, "analysis")
    try:
        row = connection.execute(
            "SELECT scan_session_id,input_digest,output_digest,state FROM analysis_runs "
            "WHERE run_id=?", (run_id,),
        ).fetchone()
        if row is None or row[2] is None or row[3] != "COMPLETE":
            raise ValueError("synthesis analysis lineage is incomplete")
        stages = _stage_map(connection, "analysis_stages", run_id,
                            {"roles", "directory_aggregates", "projects", "relationships"})
        role_rows = [tuple(item) for item in connection.execute(
            "SELECT relative_path,role,confidence,rule_id,explanation,evidence_json "
            "FROM item_roles WHERE run_id=? ORDER BY relative_path", (run_id,),
        )]
        aggregate_rows = [tuple(item) for item in connection.execute(
            "SELECT relative_path,recursive_bytes,file_count,directory_count,role_counts_json,"
            "role_coherence FROM directory_aggregates WHERE run_id=? ORDER BY relative_path",
            (run_id,),
        )]
        project_rows = [tuple(item) for item in connection.execute(
            "SELECT relative_path,boundary_score,markers_json,rule_version FROM projects "
            "WHERE run_id=? ORDER BY relative_path", (run_id,),
        )]
        relationship_rows = [tuple(item) for item in connection.execute(
            "SELECT source_kind,source_id,relationship_type,target_kind,target_id,evidence_json "
            "FROM relationships WHERE run_id=? ORDER BY source_kind,source_id,relationship_type,"
            "target_kind,target_id", (run_id,),
        )]
        recomputed = {
            "roles": _rows_digest(role_rows),
            "directory_aggregates": _rows_digest(aggregate_rows),
            "projects": _rows_digest(project_rows),
            "relationships": _rows_digest(relationship_rows),
        }
        output_digest = _digest([
            recomputed["roles"], recomputed["directory_aggregates"],
            recomputed["projects"], recomputed["relationships"],
        ])
        if recomputed != stages or output_digest != str(row[2]) or (
            _digest([str(row[1]), output_digest]) != ranking_input_digest
        ):
            raise ValueError("analysis logical output or ranking input digest mismatch")
        return str(row[0])
    finally:
        connection.close()


def _longitudinal_current(
    path: Path, run_id: str, output_digest: str
) -> tuple[Path, str, str, str]:
    link = validate_longitudinal_link(path, run_id, output_digest)
    return (
        Path(link.current_analysis_path).resolve(strict=True), link.current_analysis_run_id,
        link.current_session_id, link.output_digest,
    )


def _assigned_project(path: str, projects: Sequence[str]) -> str | None:
    return next((project for project in sorted(projects, key=lambda item: (-len(item), item))
                 if path == project or path.startswith(project + "/")), None)


def _join(
    ranking: RankingSnapshot, fusion: FusionSnapshot, dependency: DependencySnapshot,
    history: HistorySnapshot,
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    rows: list[tuple[object, ...]] = []
    signals: list[tuple[object, ...]] = []
    projects = sorted(dependency.features)
    for path in ranking.candidates:
        fusion_row = fusion.features.get(path)
        history_row = history.directories.get(path)
        if fusion_row is None or history_row is None:
            raise ValueError("evidence inputs do not cover every ranking candidate directory")
        project = _assigned_project(path, projects)
        dependency_row = None if project is None else dependency.features[project]
        project_history = None if project is None else history.projects.get(project)
        if project is not None and project_history is None:
            raise ValueError("history does not cover a dependency project")
        evidence_state = "NO_PROJECT_CONTEXT" if dependency_row is None else str(dependency_row[1])
        row = (
            path, project, _real(fusion_row[9], "enrichment coverage"),
            _integer(fusion_row[3], "selected file count"),
            _integer(fusion_row[5], "candidate duplicate member count"),
            _integer(fusion_row[7], "confirmed duplicate member count"),
            _real(fusion_row[10], "confirmed member ratio"), evidence_state,
            0 if dependency_row is None else _integer(dependency_row[2], "dependency in degree"),
            0 if dependency_row is None else _integer(dependency_row[3], "dependency out degree"),
            0 if dependency_row is None else _integer(dependency_row[4], "relationship degree"),
            0.0 if dependency_row is None else _real(dependency_row[7], "dependency pagerank"),
            0 if dependency_row is None else _integer(dependency_row[8], "dependency cut risk"),
            _integer(history_row[1], "history covered transitions"),
            _integer(history_row[5], "history ambiguous count"),
            _real(history_row[7], "history mean churn"),
            _real(history_row[8], "history maximum churn"),
            None if project_history is None else _real(project_history[7], "project activity ratio"),
            None if project_history is None else _integer(project_history[6], "project ambiguity"),
        )
        rows.append(row)
        evidence: list[tuple[str, object]] = []
        if row[2] < 1.0:
            evidence.append(("ENRICHMENT_PARTIAL_COVERAGE", {"coverage": row[2]}))
        if row[5] > 0:
            evidence.append(("CONFIRMED_DUPLICATE_MEMBERS", {
                "confirmed_member_count": row[5], "coverage": row[2],
            }))
        if project is not None and evidence_state != "EVALUATED":
            evidence.append(("DEPENDENCY_NOT_EVALUATED", {"project_id": project}))
        if row[12] > 0:
            evidence.append(("DEPENDENCY_CUT_RISK", {
                "project_id": project, "component_split_count": row[12],
            }))
        project_ambiguity = 0 if row[18] is None else int(row[18])
        if row[14] > 0 or project_ambiguity > 0:
            evidence.append(("HISTORY_AMBIGUITY", {
                "directory_ambiguous_count": row[14],
                "project_ambiguous_count": project_ambiguity,
            }))
        if row[16] > 0:
            evidence.append(("HISTORY_CHURN_OBSERVED", {
                "mean_churn_ratio": row[15], "maximum_churn_ratio": row[16],
            }))
        signals.extend((path, name, json.dumps(value, sort_keys=True, separators=(",", ":")))
                       for name, value in evidence)
    signals.sort(key=lambda item: (str(item[0]), str(item[1])))
    return rows, signals


def _record_stage(
    connection: sqlite3.Connection, run_id: str, name: str, input_digest: str,
    config: object, output_digest: str,
) -> None:
    connection.execute(
        "INSERT INTO synthesis_stages VALUES(?,?,?,?,?,?,?,NULL)",
        (run_id, name, "COMPLETE", input_digest, _digest(config), output_digest, CODE_VERSION),
    )


def run_synthesis(
    ranking_path: str | Path, fusion_path: str | Path, dependency_path: str | Path,
    history_path: str | Path, output_path: str | Path,
) -> SynthesisResult:
    inputs = [Path(item).expanduser().resolve(strict=True) for item in (
        ranking_path, fusion_path, dependency_path, history_path
    )]
    destination = Path(output_path).expanduser().resolve(strict=False)
    if len(set(inputs + [destination])) != 5 or any(
        path.parent != inputs[0].parent for path in [*inputs[1:], destination]
    ) or destination.exists():
        raise ValueError("ranking, fusion, dependency, history, and new output must be distinct siblings")
    ranking = _read_ranking(inputs[0])
    fusion = _read_fusion(inputs[1])
    dependency = _read_dependency(inputs[2])
    history = _read_history(inputs[3])
    if ranking.analysis_path != fusion.analysis_path or (
        ranking.analysis_run_id != fusion.analysis_run_id
    ):
        raise ValueError("ranking and fusion analysis lineage mismatch")
    analysis_session = _analysis_session(
        ranking.analysis_path, ranking.analysis_run_id, ranking.analysis_input_digest
    )
    dependency_current = _longitudinal_current(
        dependency.longitudinal_path, dependency.longitudinal_run_id,
        dependency.longitudinal_output_digest,
    )
    history_current = _longitudinal_current(
        history.latest_longitudinal_path, history.latest_longitudinal_run_id,
        history.latest_longitudinal_output_digest,
    )
    if dependency.longitudinal_path != history.latest_longitudinal_path or (
        dependency.longitudinal_run_id != history.latest_longitudinal_run_id
    ) or dependency_current != history_current:
        raise ValueError("dependency and history latest longitudinal lineage mismatch")
    if dependency_current[0] != ranking.analysis_path or dependency_current[1] != (
        ranking.analysis_run_id
    ) or dependency_current[2] != analysis_session or fusion.scan_session_id != analysis_session or (
        history.latest_session_id != analysis_session
    ):
        raise ValueError("evidence inputs do not resolve to the ranking analysis session")
    rows, signals = _join(ranking, fusion, dependency, history)
    input_digest = _digest([
        ranking.output_digest, fusion.output_digest, dependency.output_digest, history.output_digest,
    ])
    run_id = str(uuid4())
    database = sqlite3.connect(destination)
    try:
        database.execute("PRAGMA journal_mode=DELETE")
        database.execute("PRAGMA synchronous=FULL")
        database.executescript(SCHEMA)
        database.execute(
            "INSERT INTO synthesis_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,'RUNNING',?,?,?,NULL,NULL)",
            (run_id, str(ranking.path), ranking.run_id, str(fusion.path), fusion.run_id,
             str(dependency.path), dependency.run_id, str(history.path), history.run_id,
             str(ranking.analysis_path), ranking.analysis_run_id, analysis_session, input_digest,
             len(rows), len(signals), _utc()),
        )
        validation_digest = _digest([
            ranking.stages, fusion.stages, dependency.stages, history.stages,
            dependency_current[3],
        ])
        _record_stage(database, run_id, "validate", input_digest,
                      {"shared_analysis_session": True}, validation_digest)
        database.executemany(
            "INSERT INTO candidate_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(run_id, *row) for row in rows],
        )
        join_digest = _rows_digest(rows)
        _record_stage(database, run_id, "join_evidence", validation_digest, {
            "coverage_extrapolation": False, "composite_score": False,
            "pareto_rank_mutation": False,
        }, join_digest)
        database.executemany(
            "INSERT INTO review_signals VALUES(?,?,?,?)",
            [(run_id, *row) for row in signals],
        )
        signal_digest = _rows_digest(signals)
        _record_stage(database, run_id, "review_signals", join_digest,
                      {"combined_priority": False}, signal_digest)
        output_digest = _digest([validation_digest, join_digest, signal_digest])
        database.execute(
            "UPDATE synthesis_runs SET output_digest=?,state='COMPLETE',finished_at=? WHERE run_id=?",
            (output_digest, _utc(), run_id),
        )
        database.commit()
        return SynthesisResult(
            run_id, "COMPLETE", input_digest, output_digest, len(rows), len(signals)
        )
    except BaseException as exc:
        database.rollback()
        database.execute(
            "UPDATE synthesis_runs SET state='FAILED',finished_at=?,error=? WHERE run_id=?",
            (_utc(), f"{type(exc).__name__}: {exc}", run_id),
        )
        database.commit()
        raise
    finally:
        database.close()
