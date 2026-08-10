"""Exercise the installed Stage 0.14 evidence-synthesis CLI."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.test_enrichment_pipeline import tree_digest
from tests.test_synthesis_pipeline import synthesis_fixture


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="paretodrive-synthesis-") as temporary:
        root = Path(temporary)
        source, inputs = synthesis_fixture(root)
        output = root / "synthesis.db"
        before = {str(path): _sha256(path) for path in inputs}
        source_before = tree_digest(source)
        entrypoint_directory = Path(
            os.environ.get("PARETODRIVE_ENTRYPOINT_DIR", str(Path(sys.executable).parent))
        )
        executable = entrypoint_directory / (
            "paretodrive-synthesize-evidence.exe" if os.name == "nt"
            else "paretodrive-synthesize-evidence"
        )
        if not executable.is_file():
            raise RuntimeError(f"installed synthesis entry point is missing: {executable}")
        completed = subprocess.run(
            [str(executable), "--ranking", str(inputs[1]), "--fusion", str(inputs[2]),
             "--dependency", str(inputs[3]), "--history", str(inputs[4]),
             "--output", str(output)],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=150, check=False,
        )
        if completed.returncode != 0 or completed.stderr or not completed.stdout:
            raise RuntimeError(
                f"installed synthesis CLI failed: exit={completed.returncode}; "
                f"stdout={completed.stdout!r}; stderr={completed.stderr!r}"
            )
        result = json.loads(completed.stdout)
        database = sqlite3.connect(output)
        confirmed = database.execute(
            "SELECT COUNT(*) FROM review_signals WHERE signal_type='CONFIRMED_DUPLICATE_MEMBERS'"
        ).fetchone()[0]
        churn = database.execute(
            "SELECT COUNT(*) FROM review_signals WHERE signal_type='HISTORY_CHURN_OBSERVED'"
        ).fetchone()[0]
        database.close()
        after = {str(path): _sha256(path) for path in inputs}
        if result["candidate_count"] < 1 or confirmed < 1 or churn < 1:
            raise RuntimeError("installed synthesis output omitted required evidence dimensions")
        if before != after or tree_digest(source) != source_before:
            raise RuntimeError("installed synthesis CLI modified an input or source content")
        print(json.dumps({
            "status": "PASS", "entry_point": executable.name,
            "output_digest": result["output_digest"], "synthesis_sha256": _sha256(output),
            "candidate_count": result["candidate_count"], "signal_count": result["signal_count"],
            "confirmed_signal_count": confirmed, "churn_signal_count": churn,
            "inputs_unchanged": True, "source_contents_unchanged": True,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
