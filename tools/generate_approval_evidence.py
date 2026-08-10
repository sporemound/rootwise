"""Exercise installed approval and preflight CLIs on a temporary synthetic chain."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from rootwise_analytics.optimizer_pipeline import run_optimization
from rootwise_analytics.pipeline import run_analysis
from rootwise_analytics.ranking_pipeline import run_ranking
from rootwise_approval.declaration import ACKNOWLEDGEMENTS, INTENT, SCHEMA_VERSION
from rootwise.viewer.decisions import DecisionStore
from tests.test_viewer_inventory import completed_inventory


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_digest(source: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        digest.update(path.relative_to(source).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rootwise-approval-") as temporary:
        root = Path(temporary)
        inventory, session = completed_inventory(root)
        analysis = root / "analysis.db"
        ranking = root / "ranking.db"
        decisions = root / "decisions.db"
        plans = root / "plans.db"
        analysis_result = run_analysis(inventory, analysis, session_id=session)
        run_ranking(analysis, ranking, analysis_run_id=analysis_result.run_id, review_limit=5)
        with DecisionStore(decisions, inventory_path=inventory) as store:
            store.set_decision(session, "project/src", "ARCHIVE_ELIGIBLE")
            store.set_decision(session, "originals", "PROTECT")
        result = run_optimization(
            ranking,
            decisions,
            plans,
            maximum_archive_bytes=10_000,
            destination_available_bytes=100_000,
            generations=2,
            max_frontier_states=200,
        )
        connection = sqlite3.connect(plans)
        row = connection.execute(
            "SELECT p.plan_id,r.output_digest,r.decisions_digest FROM proposed_plans p "
            "JOIN plan_runs r USING(run_id) WHERE p.run_id=? AND EXISTS ("
            "SELECT 1 FROM proposed_archives a WHERE a.run_id=p.run_id AND a.plan_id=p.plan_id) "
            "ORDER BY p.plan_id LIMIT 1",
            (result.run_id,),
        ).fetchone()
        connection.close()
        if row is None:
            raise RuntimeError("synthetic optimizer produced no archive proposal")
        declaration = root / "approval-declaration.json"
        declaration.write_text(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "plan_run_id": result.run_id,
            "plan_id": str(row[0]),
            "plan_output_digest": str(row[1]),
            "decisions_digest": str(row[2]),
            "intent": INTENT,
            "acknowledgements": list(ACKNOWLEDGEMENTS),
            "operator": "installed-cli-synthetic-fixture",
            "approved_at": "2026-08-09T22:00:00Z",
            "note": "Temporary installed CLI integration evidence only.",
        }, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        source = root / "source"
        before = {
            "plans": _sha256(plans), "declaration": _sha256(declaration),
            "inventory": _sha256(inventory), "source": _tree_digest(source),
        }
        entrypoint_directory = Path(
            os.environ.get("ROOTWISE_ENTRYPOINT_DIR", str(Path(sys.executable).parent))
        )
        executable = entrypoint_directory / ("rootwise.exe" if os.name == "nt" else "rootwise")
        if not executable.is_file():
            raise RuntimeError(f"installed approval entry point is missing: {executable}")
        receipt = root / "approval-receipt.json"
        completed = subprocess.run(
            [str(executable), "plan", "approve", "--plans", str(plans),
             "--declaration", str(declaration), "--receipt", str(receipt)],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        if completed.returncode != 0 or completed.stderr or not completed.stdout:
            raise RuntimeError(
                f"installed approval CLI failed: exit={completed.returncode}; "
                f"stdout={completed.stdout!r}; stderr={completed.stderr!r}"
            )
        cli_result = json.loads(completed.stdout)
        receipt_value = json.loads(receipt.read_bytes())
        if any(receipt_value["authorizations"].values()):
            raise RuntimeError("approval receipt unexpectedly authorized an action")
        after_approval = {
            "plans": _sha256(plans), "declaration": _sha256(declaration),
            "inventory": _sha256(inventory), "source": _tree_digest(source),
        }
        if before != after_approval:
            raise RuntimeError("installed approval CLI modified an input")
        preflight_executable = executable
        if not preflight_executable.is_file():
            raise RuntimeError(f"installed preflight entry point is missing: {preflight_executable}")
        manifest = root / "preflight-manifest.json"
        preflight = subprocess.run(
            [str(preflight_executable), "plan", "preflight", "--plans", str(plans),
             "--approval-receipt", str(receipt), "--inventory", str(inventory),
             "--manifest", str(manifest)],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        if preflight.returncode != 0 or preflight.stderr or not preflight.stdout:
            raise RuntimeError(
                f"installed preflight CLI failed: exit={preflight.returncode}; "
                f"stdout={preflight.stdout!r}; stderr={preflight.stderr!r}"
            )
        preflight_result = json.loads(preflight.stdout)
        manifest_value = json.loads(manifest.read_bytes())
        if any(manifest_value["authorizations"].values()):
            raise RuntimeError("preflight manifest unexpectedly authorized an action")
        after_preflight = {
            "plans": _sha256(plans), "declaration": _sha256(declaration),
            "inventory": _sha256(inventory), "source": _tree_digest(source),
        }
        if before != after_preflight:
            raise RuntimeError("installed preflight CLI modified an input or source content")
        print(json.dumps({
            "status": "PASS",
            "approval_entry_point": executable.name,
            "preflight_entry_point": preflight_executable.name,
            "receipt_digest": cli_result["receipt_digest"],
            "receipt_sha256": _sha256(receipt),
            "manifest_digest": preflight_result["manifest_digest"],
            "manifest_sha256": _sha256(manifest),
            "inputs_unchanged": True,
            "source_contents_unchanged": True,
            "receipt_authorizations": receipt_value["authorizations"],
            "manifest_authorizations": manifest_value["authorizations"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
