"""Exercise the installed Stage 0.12 dependency-graph CLI on synthetic snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from rootwise_longitudinal.pipeline import run_longitudinal
from tests.test_longitudinal_pipeline import repeated_snapshots, tree_digest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rootwise-dependency-") as temporary:
        root = Path(temporary)
        source, inventory, baseline, current, baseline_run, current_run = repeated_snapshots(root)
        longitudinal = root / "longitudinal.db"
        history = run_longitudinal(
            baseline, current, longitudinal,
            baseline_analysis_run_id=baseline_run,
            current_analysis_run_id=current_run,
            shared_extension_threshold=0.2,
        )
        manifest = root / "dependency-evidence.json"
        manifest.write_text(json.dumps({
            "schema": "rootwise-project-dependency-evidence-v1",
            "longitudinal_run_id": history.run_id,
            "longitudinal_output_digest": history.output_digest,
            "producer": "installed-synthetic-fixture",
            "created_at": "2026-08-09T00:00:00Z",
            "evaluated_projects": ["project", "project2"],
            "relationships": [{
                "evidence_id": "edge-001", "source_project": "project2",
                "target_project": "project", "relationship_type": "DEPENDS_ON",
                "confidence": 0.9, "evidence_reference": "explicit synthetic declaration",
            }],
        }, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
        output = root / "dependency.db"
        before = {
            "inventory": _sha256(inventory), "longitudinal": _sha256(longitudinal),
            "manifest": _sha256(manifest), "source": tree_digest(source),
        }
        entrypoint_directory = Path(
            os.environ.get("ROOTWISE_ENTRYPOINT_DIR", str(Path(sys.executable).parent))
        )
        executable = entrypoint_directory / ("rootwise.exe" if os.name == "nt" else "rootwise")
        if not executable.is_file():
            raise RuntimeError(f"installed dependency entry point is missing: {executable}")
        completed = subprocess.run(
            [str(executable), "evidence", "dependency", "--longitudinal", str(longitudinal),
             "--evidence-manifest", str(manifest), "--output", str(output)],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, check=False,
        )
        if completed.returncode != 0 or completed.stderr or not completed.stdout:
            raise RuntimeError(
                f"installed dependency CLI failed: exit={completed.returncode}; "
                f"stdout={completed.stdout!r}; stderr={completed.stderr!r}"
            )
        result = json.loads(completed.stdout)
        database = sqlite3.connect(output)
        edge = database.execute(
            "SELECT relationship_type,directed FROM dependency_edges"
        ).fetchone()
        coverage = database.execute(
            "SELECT dependency_evidence_coverage FROM dependency_runs"
        ).fetchone()[0]
        database.close()
        if edge != ("DEPENDS_ON", 1) or coverage != 1.0:
            raise RuntimeError("installed dependency output violated explicit-evidence semantics")
        after = {
            "inventory": _sha256(inventory), "longitudinal": _sha256(longitudinal),
            "manifest": _sha256(manifest), "source": tree_digest(source),
        }
        if before != after:
            raise RuntimeError("installed dependency CLI modified an input or source content")
        print(json.dumps({
            "status": "PASS", "entry_point": executable.name,
            "output_digest": result["output_digest"], "dependency_sha256": _sha256(output),
            "dependency_edge_count": 1, "dependency_evidence_coverage": coverage,
            "inputs_unchanged": True, "source_contents_unchanged": True,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
