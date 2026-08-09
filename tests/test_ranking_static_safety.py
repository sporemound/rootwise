from __future__ import annotations

from pathlib import Path


def test_ranking_reads_only_analysis_and_contains_no_execution_language() -> None:
    root = Path(__file__).parents[1] / "src" / "paretodrive_analytics"
    source = (root / "ranking_pipeline.py").read_text(encoding="utf-8")
    assert "?mode=ro" in source
    assert "PRAGMA query_only=ON" in source
    for forbidden in ("subprocess", "socket", "shutil", "Path.unlink", "os.remove", "zipfile"):
        assert forbidden not in source
