"""Exercise the installed Stage 0.13 history CLI on a three-snapshot chain."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.test_history_pipeline import history_fixture
from tests.test_longitudinal_pipeline import tree_digest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rootwise-history-") as temporary:
        root = Path(temporary)
        source, inventory, manifest, links = history_fixture(root)
        output = root / "history.db"
        inputs = [inventory, manifest, *links]
        before = {str(path): _sha256(path) for path in inputs}
        source_before = tree_digest(source)
        entrypoint_directory = Path(
            os.environ.get("ROOTWISE_ENTRYPOINT_DIR", str(Path(sys.executable).parent))
        )
        executable = entrypoint_directory / ("rootwise.exe" if os.name == "nt" else "rootwise")
        if not executable.is_file():
            raise RuntimeError(f"installed history entry point is missing: {executable}")
        completed = subprocess.run(
            [str(executable), "evidence", "history", "--chain-manifest", str(manifest),
             "--output", str(output)],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, check=False,
        )
        if completed.returncode != 0 or completed.stderr or not completed.stdout:
            raise RuntimeError(
                f"installed history CLI failed: exit={completed.returncode}; "
                f"stdout={completed.stdout!r}; stderr={completed.stderr!r}"
            )
        result = json.loads(completed.stdout)
        database = sqlite3.connect(output)
        changed = database.execute(
            "SELECT metadata_change_count FROM file_history_features "
            "WHERE relative_path='project/src/main.py'"
        ).fetchone()[0]
        absent = database.execute(
            "SELECT current_observation_state FROM file_history_features "
            "WHERE relative_path='unicode/café.txt'"
        ).fetchone()[0]
        database.close()
        after = {str(path): _sha256(path) for path in inputs}
        if result["snapshot_count"] != 3 or changed != 2 or absent != "NOT_OBSERVED":
            raise RuntimeError("installed history output violated temporal semantics")
        if before != after or tree_digest(source) != source_before:
            raise RuntimeError("installed history CLI modified an input or source content")
        print(json.dumps({
            "status": "PASS", "entry_point": executable.name,
            "output_digest": result["output_digest"], "history_sha256": _sha256(output),
            "snapshot_count": 3, "transition_count": 2,
            "main_metadata_change_count": changed, "removed_path_current_state": absent,
            "inputs_unchanged": True, "source_contents_unchanged": True,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
