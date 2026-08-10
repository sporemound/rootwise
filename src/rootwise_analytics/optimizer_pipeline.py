"""Proposal-only Stage 0.6 pipeline over immutable ranking and decision snapshots."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .exact_optimizer import ExactFrontierLimit, exact_tree_frontier
from .optimizer_moea import evolutionary_proposals
from .plan_models import Candidate, PlanPolicy, ValidatedPlan
from .plan_validation import validate_plan

PLAN_APPLICATION_ID = 1_346_654_810
CODE_VERSION = "0.6.0-alpha"
DEPENDENCIES = {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "pymoo")}
SCHEMA = """
PRAGMA application_id=1346654810;
CREATE TABLE plan_runs (
 run_id TEXT PRIMARY KEY, ranking_path TEXT NOT NULL, ranking_run_id TEXT NOT NULL,
 decisions_path TEXT NOT NULL, scan_session_id TEXT NOT NULL,
 input_digest TEXT NOT NULL, decisions_digest TEXT NOT NULL, output_digest TEXT,
 state TEXT NOT NULL, configuration_json TEXT NOT NULL, dependencies_json TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, error TEXT
);
CREATE TABLE plan_stages (
 run_id TEXT NOT NULL, stage_name TEXT NOT NULL, state TEXT NOT NULL,
 input_digest TEXT NOT NULL, config_digest TEXT NOT NULL, output_digest TEXT NOT NULL,
 code_version TEXT NOT NULL, error TEXT, PRIMARY KEY(run_id,stage_name)
);
CREATE TABLE candidate_groups (
 run_id TEXT NOT NULL, candidate_id TEXT NOT NULL, relative_path TEXT NOT NULL,
 parent_id TEXT, recursive_bytes INTEGER NOT NULL, file_count INTEGER NOT NULL,
 eligible INTEGER NOT NULL, protected INTEGER NOT NULL, preservation_risk REAL NOT NULL,
 incoherence REAL NOT NULL, PRIMARY KEY(run_id,candidate_id)
);
CREATE TABLE proposed_plans (
 run_id TEXT NOT NULL, plan_id TEXT NOT NULL, sources_json TEXT NOT NULL,
 labels_json TEXT NOT NULL, objectives_json TEXT NOT NULL, validated INTEGER NOT NULL,
 approval_state TEXT NOT NULL, PRIMARY KEY(run_id,plan_id)
);
CREATE TABLE plan_actions (
 run_id TEXT NOT NULL, plan_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
 action TEXT NOT NULL, PRIMARY KEY(run_id,plan_id,candidate_id)
);
CREATE TABLE proposed_archives (
 run_id TEXT NOT NULL, plan_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
 proposed_name TEXT NOT NULL, PRIMARY KEY(run_id,plan_id,candidate_id),
 UNIQUE(run_id,plan_id,proposed_name)
);
"""


@dataclass(frozen=True)
class OptimizationResult:
    run_id: str
    state: str
    input_digest: str
    output_digest: str
    candidate_count: int
    eligible_count: int
    validated_plan_count: int


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _table_digest(connection: sqlite3.Connection, query: str, run_id: str) -> str:
    digest = hashlib.sha256()
    for row in connection.execute(query, (run_id,)):
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
        "INSERT INTO plan_stages VALUES(?,?,?,?,?,?,?,NULL)",
        (run_id, name, "COMPLETE", input_digest, _digest(config), output_digest, CODE_VERSION),
    )


def _parent_ids(paths: list[str]) -> dict[str, str | None]:
    available = set(paths)
    result: dict[str, str | None] = {}
    for path in paths:
        parts = path.split("/")
        parent = next((
            "/".join(parts[:index]) for index in range(len(parts) - 1, 0, -1)
            if "/".join(parts[:index]) in available
        ), None)
        result[path] = parent
    return result


def _dominates(left: ValidatedPlan, right: ValidatedPlan) -> bool:
    a = left.metrics.values()
    b = right.metrics.values()
    return all(x <= y for x, y in zip(a, b, strict=True)) and any(
        x < y for x, y in zip(a, b, strict=True)
    )


def _reduce(
    plans: dict[str, tuple[ValidatedPlan, set[str]]], limit: int = 12
) -> list[tuple[ValidatedPlan, tuple[str, ...], tuple[str, ...]]]:
    front: list[tuple[ValidatedPlan, set[str]]] = []
    for plan_id, value in plans.items():
        if not any(
            other_id != plan_id and _dominates(other[0], value[0])
            for other_id, other in plans.items()
        ):
            front.append(value)
    if not front:
        return []
    objectives = [value[0].metrics.values() for value in front]
    labels: dict[str, set[str]] = {value[0].plan_id: set() for value in front}
    selectors: dict[str, Callable[[tuple[float, ...]], tuple[float, ...]]] = {
        "safest": lambda values: (values[2], values[3], values[4]),
        "lowest-temporary-space": lambda values: (values[3], values[2]),
        "fewest-archives": lambda values: (values[4], values[3]),
        "greatest-potential-recovery": lambda values: (values[0], values[2]),
        "lowest-incoherence": lambda values: (values[5], values[2]),
    }
    chosen: list[str] = []
    for label, selector in selectors.items():
        index = min(range(len(front)), key=lambda item: selector(objectives[item]))
        plan_id = front[index][0].plan_id
        labels[plan_id].add(label)
        if plan_id not in chosen:
            chosen.append(plan_id)
    minima = [min(values[index] for values in objectives) for index in range(6)]
    maxima = [max(values[index] for values in objectives) for index in range(6)]
    knee_index = min(range(len(front)), key=lambda item: math.sqrt(sum(
        ((objectives[item][index] - minima[index]) / max(maxima[index] - minima[index], 1.0)) ** 2
        for index in range(6)
    )))
    knee = front[knee_index][0].plan_id
    labels[knee].add("knee-compromise")
    if knee not in chosen:
        chosen.append(knee)
    chosen.extend(sorted(
        value[0].plan_id for value in front if value[0].plan_id not in chosen
    )[:max(0, limit - len(chosen))])
    by_id = {value[0].plan_id: value for value in front}
    return [
        (by_id[plan_id][0], tuple(sorted(by_id[plan_id][1])), tuple(sorted(labels[plan_id])))
        for plan_id in chosen[:limit]
    ]


def run_optimization(
    ranking_path: str | Path,
    decisions_path: str | Path,
    plans_path: str | Path,
    *,
    maximum_archive_bytes: int,
    destination_available_bytes: int,
    destination_safety_margin: float = 0.15,
    generations: int = 20,
    max_frontier_states: int = 5_000,
) -> OptimizationResult:
    ranking = Path(ranking_path).expanduser().resolve(strict=True)
    decisions = Path(decisions_path).expanduser().resolve(strict=True)
    destination = Path(plans_path).expanduser().resolve(strict=False)
    if len({ranking, decisions, destination}) != 3 or any(
        path.parent != ranking.parent for path in (decisions, destination)
    ) or destination.exists():
        raise ValueError("ranking, decisions, and new plans databases must be distinct siblings")
    policy = PlanPolicy(
        maximum_archive_bytes, destination_available_bytes, destination_safety_margin
    )
    if policy.maximum_archive_bytes <= 0 or policy.destination_available_bytes < 0:
        raise ValueError("optimizer capacity limits are invalid")
    if not 0.0 <= policy.destination_safety_margin < 1.0:
        raise ValueError("destination safety margin must be in [0,1)")
    if generations < 1 or max_frontier_states < 1:
        raise ValueError("optimizer search budgets must be positive")

    ranking_db = sqlite3.connect(ranking.as_uri() + "?mode=ro", uri=True)
    decisions_db = sqlite3.connect(decisions.as_uri() + "?mode=ro", uri=True)
    ranking_db.execute("PRAGMA query_only=ON")
    decisions_db.execute("PRAGMA query_only=ON")
    ranking_db.execute("BEGIN")
    decisions_db.execute("BEGIN")
    try:
        if ranking_db.execute("PRAGMA application_id").fetchone()[0] != 1_346_654_809:
            raise ValueError("ranking database application identity mismatch")
        if decisions_db.execute("PRAGMA application_id").fetchone()[0] != 1_346_654_807:
            raise ValueError("decision database application identity mismatch")
        ranking_run = ranking_db.execute(
            "SELECT run_id,analysis_path,analysis_run_id,input_digest,output_digest "
            "FROM ranking_runs WHERE state='COMPLETE' ORDER BY finished_at DESC,run_id DESC LIMIT 1"
        ).fetchone()
        if ranking_run is None or ranking_run[4] is None:
            raise ValueError("optimization requires a COMPLETE 0.5 ranking run")
        ranking_stages = {tuple(row) for row in ranking_db.execute(
            "SELECT stage_name,state FROM ranking_stages WHERE run_id=?", (str(ranking_run[0]),)
        )}
        if ranking_stages != {
            ("materialize", "COMPLETE"), ("objectives", "COMPLETE"),
            ("pareto", "COMPLETE"), ("review", "COMPLETE"),
        }:
            raise ValueError("ranking prerequisite stages are incomplete or mismatched")
        analysis = Path(str(ranking_run[1])).resolve(strict=True)
        if analysis.parent != ranking.parent:
            raise ValueError("recorded analysis path escaped the external database directory")
        analysis_db = sqlite3.connect(analysis.as_uri() + "?mode=ro", uri=True)
        analysis_db.execute("PRAGMA query_only=ON")
        analysis_db.execute("BEGIN")
        try:
            analysis_run = analysis_db.execute(
                "SELECT scan_session_id,state FROM analysis_runs WHERE run_id=?",
                (str(ranking_run[2]),),
            ).fetchone()
            if analysis_run is None or analysis_run[1] != "COMPLETE":
                raise ValueError("recorded analysis run is not COMPLETE")
            analysis_stages = {tuple(row) for row in analysis_db.execute(
                "SELECT stage_name,state FROM analysis_stages WHERE run_id=?",
                (str(ranking_run[2]),),
            )}
            if analysis_stages != {
                ("roles", "COMPLETE"), ("directory_aggregates", "COMPLETE"),
                ("projects", "COMPLETE"), ("relationships", "COMPLETE"),
            }:
                raise ValueError("analysis prerequisite stages are incomplete or mismatched")
            scan_session_id = str(analysis_run[0])
        finally:
            analysis_db.close()
        decision_rows = list(decisions_db.execute(
            "SELECT relative_path,decision,revision,updated_at FROM current_decisions "
            "WHERE scan_session_id=? ORDER BY relative_path", (scan_session_id,),
        ))
        decision_map = {str(row[0]): str(row[1]) for row in decision_rows}
        decisions_digest = _digest([tuple(row) for row in decision_rows])
        ranking_run_id = str(ranking_run[0])
        features = list(ranking_db.execute(
            "SELECT relative_path,recursive_bytes,file_count FROM directory_features "
            "WHERE run_id=? ORDER BY relative_path", (ranking_run_id,),
        ))
        intervals = {(str(row[0]), str(row[1])): float(row[2]) for row in ranking_db.execute(
            "SELECT relative_path,objective_name,point FROM objective_intervals WHERE run_id=?",
            (ranking_run_id,),
        )}
    finally:
        ranking_db.close()
        decisions_db.close()
    paths = [str(row[0]) for row in features]
    parents = _parent_ids(paths)
    protected_decisions = {"KEEP", "PROTECT", "NOT_REBUILDABLE"}
    candidates = [Candidate(
        path,
        path,
        parents[path],
        int(row[1]),
        int(row[2]),
        decision_map.get(path) == "ARCHIVE_ELIGIBLE",
        decision_map.get(path) in protected_decisions,
        intervals[(path, "preservation_risk")],
        intervals[(path, "incoherence")],
    ) for row, path in zip(features, paths, strict=True)]
    if not candidates or not any(candidate.eligible for candidate in candidates):
        raise ValueError("optimization requires at least one explicitly ARCHIVE_ELIGIBLE directory")
    input_digest = _digest([str(ranking_run[3]), str(ranking_run[4]), decisions_digest])
    configuration = {
        **asdict(policy), "generations": generations, "seeds": [0, 1, 2],
        "max_frontier_states": max_frontier_states,
    }
    run_id = str(uuid4())
    output = sqlite3.connect(destination)
    try:
        output.execute("PRAGMA journal_mode=DELETE")
        output.execute("PRAGMA synchronous=FULL")
        output.executescript(SCHEMA)
        output.execute(
            "INSERT INTO plan_runs VALUES(?,?,?,?,?,?,?,NULL,'RUNNING',?,?,?,NULL,NULL)",
            (run_id, str(ranking), ranking_run_id, str(decisions), scan_session_id,
             input_digest, decisions_digest, json.dumps(configuration, sort_keys=True),
             json.dumps(DEPENDENCIES, sort_keys=True), _utc()),
        )
        output.commit()
        for candidate in candidates:
            output.execute("INSERT INTO candidate_groups VALUES(?,?,?,?,?,?,?,?,?,?)", (
                run_id, candidate.candidate_id, candidate.relative_path, candidate.parent_id,
                candidate.recursive_bytes, candidate.file_count, int(candidate.eligible),
                int(candidate.protected), candidate.preservation_risk, candidate.incoherence,
            ))
        candidate_digest = _table_digest(output,
            "SELECT candidate_id,relative_path,parent_id,recursive_bytes,file_count,eligible,"
            "protected,preservation_risk,incoherence FROM candidate_groups WHERE run_id=? "
            "ORDER BY candidate_id", run_id)
        _stage(output, run_id, "candidates", input_digest,
               {"eligibility": "explicit-decisions-only"}, candidate_digest)

        try:
            exact = exact_tree_frontier(
                candidates, policy, max_frontier_states=max_frontier_states
            )
            exact_digest = _digest([plan.plan_id for plan in exact])
            _stage(output, run_id, "exact", candidate_digest,
                   {"max_frontier_states": max_frontier_states}, exact_digest)
        except ExactFrontierLimit as exc:
            exact = []
            exact_digest = _digest([])
            output.execute(
                "INSERT INTO plan_stages VALUES(?,?,?,?,?,?,?,?)",
                (run_id, "exact", "SKIPPED_LIMIT", candidate_digest,
                 _digest({"max_frontier_states": max_frontier_states}), exact_digest,
                 CODE_VERSION, str(exc)),
            )
        evolved = evolutionary_proposals(candidates, policy, generations=generations)
        nsga = [item for item in evolved if item.source.startswith("NSGA3")]
        rnsga = [item for item in evolved if item.source.startswith("RNSGA3")]
        nsga_digest = _digest([(item.source, item.plan.plan_id) for item in nsga])
        _stage(output, run_id, "nsga3", candidate_digest,
               {"generations": generations, "seeds": [0, 1, 2]}, nsga_digest)
        rnsga_digest = _digest([(item.source, item.plan.plan_id) for item in rnsga])
        _stage(output, run_id, "rnsga3", nsga_digest,
               {"generations": generations, "preference": "safest",
                "degenerate_fallback": any("degenerate" in item.source for item in rnsga)},
               rnsga_digest)

        merged: dict[str, tuple[ValidatedPlan, set[str]]] = {}
        for source, plan in [
            *(("EXACT", plan) for plan in exact),
            *((item.source, item.plan) for item in evolved),
        ]:
            validated = validate_plan(
                candidates, policy, dict(plan.actions), expected_metrics=plan.metrics
            )
            entry = merged.setdefault(validated.plan_id, (validated, set()))
            entry[1].add(source)
        reduced = _reduce(merged)
        if not reduced:
            raise RuntimeError("no independently validated proposal survived reduction")
        validate_digest = _digest([
            (plan.plan_id, plan.metrics.values()) for plan, _, _ in reduced
        ])
        _stage(output, run_id, "validate", rnsga_digest,
               {"independent_recomputation": True}, validate_digest)
        for plan, sources, labels in reduced:
            output.execute("INSERT INTO proposed_plans VALUES(?,?,?,?,?,?,?)", (
                run_id, plan.plan_id, json.dumps(sources), json.dumps(labels),
                json.dumps(plan.metrics.values()), 1, "UNAPPROVED",
            ))
            output.executemany("INSERT INTO plan_actions VALUES(?,?,?,?)", [
                (run_id, plan.plan_id, candidate_id, action.name)
                for candidate_id, action in plan.actions
            ])
            output.executemany("INSERT INTO proposed_archives VALUES(?,?,?,?)", [
                (run_id, plan.plan_id, candidate_id, name)
                for candidate_id, name in plan.archive_names
            ])
        presentation_digest = _table_digest(output,
            "SELECT plan_id,sources_json,labels_json,objectives_json,validated,approval_state "
            "FROM proposed_plans WHERE run_id=? ORDER BY plan_id", run_id)
        _stage(output, run_id, "present", validate_digest,
               {"limit": 12, "approval_state": "UNAPPROVED"}, presentation_digest)
        output_digest = _digest([
            candidate_digest, exact_digest, nsga_digest, rnsga_digest,
            validate_digest, presentation_digest,
        ])
        output.execute(
            "UPDATE plan_runs SET output_digest=?,state='COMPLETE',finished_at=? WHERE run_id=?",
            (output_digest, _utc(), run_id),
        )
        output.commit()
        return OptimizationResult(
            run_id, "COMPLETE", input_digest, output_digest, len(candidates),
            sum(candidate.eligible for candidate in candidates), len(reduced),
        )
    except BaseException as exc:
        output.rollback()
        output.execute(
            "UPDATE plan_runs SET state='FAILED',finished_at=?,error=? WHERE run_id=?",
            (_utc(), f"{type(exc).__name__}: {exc}", run_id),
        )
        output.commit()
        raise
    finally:
        output.close()
