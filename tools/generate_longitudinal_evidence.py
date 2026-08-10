"""Exercise the installed longitudinal CLI on two temporary synthetic snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.test_longitudinal_pipeline import repeated_snapshots, tree_digest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rootwise-longitudinal-") as temporary:
        root = Path(temporary)
        source, inventory, baseline, current, baseline_run, current_run = repeated_snapshots(root)
        output = root / "longitudinal.db"
        before = {
            "inventory": _sha256(inventory), "baseline": _sha256(baseline),
            "current": _sha256(current), "source": tree_digest(source),
        }
        entrypoint_directory = Path(
            os.environ.get("ROOTWISE_ENTRYPOINT_DIR", str(Path(sys.executable).parent))
        )
        executable = entrypoint_directory / (
            "rootwise-longitudinal.exe" if os.name == "nt" else "rootwise-longitudinal"
        )
        if not executable.is_file():
            raise RuntimeError(f"installed longitudinal entry point is missing: {executable}")
        completed = subprocess.run(
            [str(executable), "--baseline-analysis", str(baseline),
             "--current-analysis", str(current), "--output", str(output),
             "--baseline-run", baseline_run, "--current-run", current_run,
             "--shared-extension-threshold", "0.2"],
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
                f"installed longitudinal CLI failed: exit={completed.returncode}; "
                f"stdout={completed.stdout!r}; stderr={completed.stderr!r}"
            )
        result = json.loads(completed.stdout)
        connection = sqlite3.connect(output)
        change_types = dict(connection.execute(
            "SELECT change_type,COUNT(*) FROM file_changes GROUP BY change_type"
        ))
        dependency_coverage = float(connection.execute(
            "SELECT COALESCE(MAX(dependency_evidence_coverage),0) FROM project_graph_features"
        ).fetchone()[0])
        contextual_edges = int(connection.execute(
            "SELECT COUNT(*) FROM project_edges WHERE relationship_type='SHARED_EXTENSION_PROFILE'"
        ).fetchone()[0])
        connection.close()
        required = {"ADDED", "REMOVED", "METADATA_CHANGED", "METADATA_UNCHANGED"}
        if not required <= set(change_types) or dependency_coverage != 0.0 or contextual_edges < 1:
            raise RuntimeError("installed longitudinal output violated change or graph semantics")
        after = {
            "inventory": _sha256(inventory), "baseline": _sha256(baseline),
            "current": _sha256(current), "source": tree_digest(source),
        }
        if before != after:
            raise RuntimeError("installed longitudinal CLI modified an input or source content")
        print(json.dumps({
            "status": "PASS",
            "entry_point": executable.name,
            "output_digest": result["output_digest"],
            "longitudinal_sha256": _sha256(output),
            "change_types": change_types,
            "contextual_edge_count": contextual_edges,
            "dependency_evidence_coverage": dependency_coverage,
            "inputs_unchanged": True,
            "source_contents_unchanged": True,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
