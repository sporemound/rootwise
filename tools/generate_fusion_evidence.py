"""Exercise the installed fusion CLI over temporary synthetic D3 evidence."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from paretodrive_analytics.pipeline import run_analysis
from paretodrive_enrich.pipeline import run_enrichment
from paretodrive_enrich.reader import ReadPolicy
from tests.test_enrichment_pipeline import (
    enrichment_fixture,
    fake_resolver,
    manifest,
    tree_digest,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="paretodrive-fusion-") as temporary:
        root = Path(temporary)
        source, inventory, session = enrichment_fixture(root)
        analysis = root / "analysis.db"
        selection = root / "selection.json"
        evidence = root / "evidence.db"
        fusion = root / "fusion.db"
        run_analysis(inventory, analysis, session_id=session)
        manifest(selection, inventory, session, "D3", [
            "media/final exports/other.wav",
            "media/final exports/render-copy.wav",
            "media/final exports/render.wav",
        ])
        run_enrichment(
            inventory,
            source,
            selection,
            evidence,
            allow_content_read=True,
            read_policy=ReadPolicy(4096, 4096, 10**9),
            volume_resolver=fake_resolver(source),
        )
        before = {
            "inventory": _sha256(inventory), "analysis": _sha256(analysis),
            "evidence": _sha256(evidence), "source": tree_digest(source),
        }
        entrypoint_directory = Path(
            os.environ.get("PARETODRIVE_ENTRYPOINT_DIR", str(Path(sys.executable).parent))
        )
        executable = entrypoint_directory / (
            "paretodrive-fuse-evidence.exe" if os.name == "nt" else "paretodrive-fuse-evidence"
        )
        if not executable.is_file():
            raise RuntimeError(f"installed fusion entry point is missing: {executable}")
        completed = subprocess.run(
            [str(executable), "--analysis", str(analysis), "--evidence", str(evidence),
             "--fusion", str(fusion)],
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
                f"installed fusion CLI failed: exit={completed.returncode}; "
                f"stdout={completed.stdout!r}; stderr={completed.stderr!r}"
            )
        result = json.loads(completed.stdout)
        connection = sqlite3.connect(fusion)
        root_features = connection.execute(
            "SELECT selected_file_count,candidate_member_count,confirmed_member_count "
            "FROM directory_evidence_features WHERE relative_path=''"
        ).fetchone()
        status = connection.execute("SELECT state,evidence_level FROM fusion_runs").fetchone()
        connection.close()
        if status != ("COMPLETE", "D3") or root_features != (3, 0, 2):
            raise RuntimeError("installed fusion output did not preserve D3 evidence semantics")
        after = {
            "inventory": _sha256(inventory), "analysis": _sha256(analysis),
            "evidence": _sha256(evidence), "source": tree_digest(source),
        }
        if before != after:
            raise RuntimeError("installed fusion CLI modified an input or source content")
        print(json.dumps({
            "status": "PASS",
            "entry_point": executable.name,
            "output_digest": result["output_digest"],
            "fusion_sha256": _sha256(fusion),
            "inputs_unchanged": True,
            "source_contents_unchanged": True,
            "root_features": {
                "selected_file_count": 3,
                "candidate_member_count": 0,
                "confirmed_member_count": 2,
            },
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
