"""DuckDB/Polars feature materialization, interval ranking, and review selection."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import duckdb
import polars as pl

from .pareto import Interval, pareto_ranks

RANKING_APPLICATION_ID = 1_346_654_809
CODE_VERSION = "0.5.0-alpha"
OBJECTIVE_VERSION = "objectives-0.5.0"
PYARROW_VERSION = importlib.metadata.version("pyarrow")
SCHEMA = """
PRAGMA application_id=1346654809;
CREATE TABLE ranking_runs (
 run_id TEXT PRIMARY KEY, analysis_path TEXT NOT NULL, analysis_run_id TEXT NOT NULL,
 input_digest TEXT NOT NULL, output_digest TEXT, state TEXT NOT NULL,
 duckdb_version TEXT NOT NULL, polars_version TEXT NOT NULL, pyarrow_version TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, error TEXT
);
CREATE TABLE ranking_stages (
 run_id TEXT NOT NULL, stage_name TEXT NOT NULL, state TEXT NOT NULL,
 input_digest TEXT NOT NULL, config_digest TEXT NOT NULL, output_digest TEXT NOT NULL,
 code_version TEXT NOT NULL, PRIMARY KEY(run_id,stage_name)
);
CREATE TABLE directory_features (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, cohort TEXT NOT NULL,
 recursive_bytes INTEGER NOT NULL, file_count INTEGER NOT NULL,
 preservation_ratio REAL NOT NULL, unknown_ratio REAL NOT NULL,
 role_coherence REAL NOT NULL, is_project INTEGER NOT NULL,
 PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE objective_intervals (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, objective_name TEXT NOT NULL,
 low REAL NOT NULL, point REAL NOT NULL, high REAL NOT NULL, confidence REAL NOT NULL,
 PRIMARY KEY(run_id,relative_path,objective_name)
);
CREATE TABLE pareto_results (
 run_id TEXT NOT NULL, relative_path TEXT NOT NULL, cohort TEXT NOT NULL, pareto_rank INTEGER NOT NULL,
 PRIMARY KEY(run_id,relative_path)
);
CREATE TABLE review_queue (
 run_id TEXT NOT NULL, review_order INTEGER NOT NULL, relative_path TEXT NOT NULL,
 priority REAL NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(run_id,review_order)
);
"""


@dataclass(frozen=True)
class RankingResult:
    run_id: str
    state: str
    input_digest: str
    output_digest: str
    candidate_count: int
    cohort_count: int
    review_count: int


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _table_digest(connection: sqlite3.Connection, query: str, run_id: str) -> str:
    digest = hashlib.sha256()
    for row in connection.execute(query, (run_id,)):
        digest.update(json.dumps(tuple(row), separators=(",", ":")).encode() + b"\n")
    return digest.hexdigest()


def _cohort(path: str, size: int) -> str:
    top = path.split("/", 1)[0] if path else "ROOT"
    band = 0 if size <= 0 else int(math.log2(size))
    return f"{top}|size2^{band}"


def _as_int(value: object) -> int:
    if isinstance(value, int | float | str | bytes | bytearray):
        return int(value)
    raise TypeError(f"expected an integer-compatible value, got {type(value).__name__}")


def _as_float(value: object) -> float:
    if isinstance(value, int | float | str | bytes | bytearray):
        return float(value)
    raise TypeError(f"expected a numeric value, got {type(value).__name__}")


def _intervals(feature: dict[str, object], max_log_bytes: float) -> tuple[Interval, ...]:
    size = _as_int(feature["recursive_bytes"])
    preservation = _as_float(feature["preservation_ratio"])
    unknown = _as_float(feature["unknown_ratio"])
    coherence = _as_float(feature["role_coherence"])
    uncertainty = min(1.0, unknown + (0.15 if _as_int(feature["file_count"]) < 3 else 0.0))
    storage = -math.log1p(size) / max_log_bytes if max_log_bytes else 0.0
    return (
        Interval("negative_storage_benefit", storage, storage, storage, 1.0),
        Interval("preservation_risk", max(0.0, preservation - uncertainty * 0.2), preservation,
                 min(1.0, preservation + uncertainty * 0.4), 1.0 - uncertainty),
        Interval("uncertainty", unknown, uncertainty, min(1.0, uncertainty + 0.15), 1.0 - unknown),
        Interval("incoherence", 1.0 - coherence, 1.0 - coherence, 1.0 - coherence, 0.9),
    )


def run_ranking(
    analysis_path: str | Path,
    ranking_path: str | Path,
    *,
    analysis_run_id: str | None = None,
    review_limit: int = 100,
) -> RankingResult:
    if not 1 <= review_limit <= 1000:
        raise ValueError("review_limit must be between 1 and 1000")
    source = Path(analysis_path).expanduser().resolve(strict=True)
    destination = Path(ranking_path).expanduser().resolve(strict=False)
    if destination == source or destination.parent != source.parent or destination.exists():
        raise ValueError("ranking database must be a new distinct file beside the analysis database")
    input_connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    input_connection.row_factory = sqlite3.Row
    input_connection.execute("PRAGMA query_only=ON")
    try:
        if input_connection.execute("PRAGMA application_id").fetchone()[0] != 1_346_654_808:
            raise ValueError("analysis database application identity mismatch")
        if analysis_run_id is None:
            run = input_connection.execute(
                "SELECT run_id,input_digest,output_digest FROM analysis_runs WHERE state='COMPLETE' "
                "ORDER BY finished_at DESC,run_id DESC LIMIT 1"
            ).fetchone()
        else:
            run = input_connection.execute(
                "SELECT run_id,input_digest,output_digest FROM analysis_runs "
                "WHERE run_id=? AND state='COMPLETE'", (analysis_run_id,),
            ).fetchone()
        if run is None or run[2] is None:
            raise ValueError("ranking requires a COMPLETE 0.4 analysis run")
        source_run = str(run[0])
        input_digest = _digest([str(run[1]), str(run[2])])
        projects = {str(row[0]) for row in input_connection.execute(
            "SELECT relative_path FROM projects WHERE run_id=?", (source_run,)
        )}
        raw: list[dict[str, object]] = []
        preservation_roles = {"SOURCE", "ORIGINAL_MEDIA", "PROJECT_METADATA", "CONFIGURATION"}
        for row in input_connection.execute(
            "SELECT relative_path,recursive_bytes,file_count,role_counts_json,role_coherence "
            "FROM directory_aggregates WHERE run_id=? AND relative_path!='' ORDER BY relative_path",
            (source_run,),
        ):
            counts = json.loads(row[3])
            total = max(1, int(row[2]))
            raw.append({
                "relative_path": str(row[0]), "recursive_bytes": int(row[1]),
                "file_count": int(row[2]),
                "preservation_ratio": sum(int(counts.get(role, 0)) for role in preservation_roles) / total,
                "unknown_ratio": int(counts.get("UNKNOWN", 0)) / total,
                "role_coherence": float(row[4]), "is_project": int(str(row[0]) in projects),
            })
    finally:
        input_connection.close()

    frame = pl.DataFrame(raw).lazy().with_columns(
        pl.struct(["relative_path", "recursive_bytes"]).map_elements(
            lambda value: _cohort(str(value["relative_path"]), int(value["recursive_bytes"])),
            return_dtype=pl.String,
        ).alias("cohort")
    ).collect()
    duck = duckdb.connect(":memory:")
    duck.register("directory_frame", frame)
    materialized = duck.execute(
        "SELECT relative_path,cohort,recursive_bytes,file_count,preservation_ratio,unknown_ratio,"
        "role_coherence,is_project FROM directory_frame ORDER BY relative_path"
    ).fetchall()
    duck.close()

    run_id = str(uuid4())
    output = sqlite3.connect(destination)
    try:
        output.execute("PRAGMA journal_mode=DELETE")
        output.execute("PRAGMA synchronous=FULL")
        output.executescript(SCHEMA)
        output.execute(
            "INSERT INTO ranking_runs VALUES(?,?,?,?,NULL,'RUNNING',?,?,?,?,NULL,NULL)",
            (
                run_id, str(source), source_run, input_digest,
                duckdb.__version__, pl.__version__, PYARROW_VERSION, _utc(),
            ),
        )
        output.commit()
        features: dict[str, dict[str, object]] = {}
        for row in materialized:
            feature = dict(zip(("relative_path", "cohort", "recursive_bytes", "file_count",
                "preservation_ratio", "unknown_ratio", "role_coherence", "is_project"), row, strict=True))
            path = str(feature["relative_path"])
            features[path] = feature
            output.execute("INSERT INTO directory_features VALUES(?,?,?,?,?,?,?,?,?)", (run_id, *row))
        feature_digest = _table_digest(output, "SELECT relative_path,cohort,recursive_bytes,file_count,"
            "preservation_ratio,unknown_ratio,role_coherence,is_project FROM directory_features "
            "WHERE run_id=? ORDER BY relative_path", run_id)
        _record_stage(output, run_id, "materialize", input_digest, {
            "duckdb": duckdb.__version__, "polars": pl.__version__, "pyarrow": PYARROW_VERSION,
        }, feature_digest)

        max_log = max(
            (math.log1p(_as_int(item["recursive_bytes"])) for item in features.values()),
            default=1.0,
        )
        objectives = {path: _intervals(feature, max_log) for path, feature in features.items()}
        for path, values in objectives.items():
            output.executemany("INSERT INTO objective_intervals VALUES(?,?,?,?,?,?,?)", [
                (run_id, path, value.name, value.low, value.point, value.high, value.confidence)
                for value in values
            ])
        objective_digest = _table_digest(output, "SELECT relative_path,objective_name,low,point,high,"
            "confidence FROM objective_intervals WHERE run_id=? ORDER BY relative_path,objective_name", run_id)
        _record_stage(output, run_id, "objectives", feature_digest,
            {"version": OBJECTIVE_VERSION}, objective_digest)

        ranks: dict[str, int] = {}
        for cohort in sorted({str(item["cohort"]) for item in features.values()}):
            cohort_items = {path: objectives[path] for path, item in features.items() if item["cohort"] == cohort}
            ranks.update(pareto_ranks(cohort_items))
        for path, rank in ranks.items():
            output.execute("INSERT INTO pareto_results VALUES(?,?,?,?)",
                (run_id, path, features[path]["cohort"], rank))
        pareto_digest = _table_digest(output, "SELECT relative_path,cohort,pareto_rank FROM pareto_results "
            "WHERE run_id=? ORDER BY relative_path", run_id)
        _record_stage(output, run_id, "pareto", objective_digest,
            {"dominance": "interval-worst-vs-best", "scope": "cohort"}, pareto_digest)

        review = sorted(features, key=lambda path: (
            -(math.log1p(_as_int(features[path]["recursive_bytes"]))
              * (_as_float(features[path]["unknown_ratio"]) + 0.1) / (ranks[path] + 1)), path
        ))[:review_limit]
        for order, path in enumerate(review, 1):
            priority = math.log1p(_as_int(features[path]["recursive_bytes"])) * (
                _as_float(features[path]["unknown_ratio"]) + 0.1) / (ranks[path] + 1)
            reason = "impact × uncertainty × Pareto sensitivity; review only, no action implied"
            output.execute("INSERT INTO review_queue VALUES(?,?,?,?,?)", (run_id, order, path, priority, reason))
        review_digest = _table_digest(output, "SELECT review_order,relative_path,priority,reason "
            "FROM review_queue WHERE run_id=? ORDER BY review_order", run_id)
        _record_stage(output, run_id, "review", pareto_digest, {"limit": review_limit}, review_digest)
        output_digest = _digest([feature_digest, objective_digest, pareto_digest, review_digest])
        output.execute("UPDATE ranking_runs SET output_digest=?,state='COMPLETE',finished_at=? WHERE run_id=?",
            (output_digest, _utc(), run_id))
        output.commit()
        return RankingResult(run_id, "COMPLETE", input_digest, output_digest, len(features),
            len({str(item["cohort"]) for item in features.values()}), len(review))
    except BaseException as exc:
        output.rollback()
        output.execute("UPDATE ranking_runs SET state='FAILED',finished_at=?,error=? WHERE run_id=?",
            (_utc(), f"{type(exc).__name__}: {exc}", run_id))
        output.commit()
        raise
    finally:
        output.close()


def _record_stage(connection: sqlite3.Connection, run_id: str, name: str, input_digest: str,
                  config: object, output_digest: str) -> None:
    connection.execute("INSERT INTO ranking_stages VALUES(?,?,?,?,?,?,?)",
        (run_id, name, "COMPLETE", input_digest, _digest(config), output_digest, CODE_VERSION))
