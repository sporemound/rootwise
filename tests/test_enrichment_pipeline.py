from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from rootwise.database import InventoryDatabase
from rootwise.models import ScanConfig, VolumeInfo
from rootwise.scanner import MetadataScanner
from rootwise.volume import resolve_volume
from rootwise_analytics.snapshot import InventorySnapshot
from rootwise_enrich.cli import main as enrichment_main
from rootwise_enrich.pipeline import ENRICHMENT_APPLICATION_ID, run_enrichment
from rootwise_enrich.reader import ReadPolicy

from .helpers import RecordingGuard, make_corpus


def enrichment_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    source = make_corpus(tmp_path / "source")
    duplicate = source / "media" / "final exports" / "render-copy.wav"
    duplicate.write_bytes((source / "media" / "final exports" / "render.wav").read_bytes())
    database = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database), 100_000, 8, 0)
    with InventoryDatabase(database, RecordingGuard(tmp_path)) as inventory:
        session, _ = MetadataScanner(source, resolve_volume(source), inventory, config).run()
    return source, database, session


def fake_resolver(source: Path):  # type: ignore[no-untyped-def]
    source_volume = resolve_volume(source)

    def resolve(path: str | Path) -> VolumeInfo:
        candidate = Path(path).resolve()
        try:
            candidate.relative_to(source)
            return source_volume
        except ValueError:
            return VolumeInfo("synthetic-destination", str(candidate), "synthetic", "test")

    return resolve


def manifest(path: Path, inventory: Path, session: str, level: str, paths: list[str]) -> None:
    with InventorySnapshot(inventory, session) as snapshot:
        inventory_digest = snapshot.logical_digest()
    path.write_text(json.dumps({
        "schema_version": "rootwise-enrichment-selection-1",
        "scan_session_id": session,
        "inventory_digest": inventory_digest,
        "evidence_level": level,
        "paths": sorted(paths),
    }, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def tree_digest(source: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        digest.update(path.relative_to(source).as_posix().encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def test_d3_pipeline_confirms_duplicates_without_modifying_inputs(tmp_path: Path) -> None:
    source, inventory, session = enrichment_fixture(tmp_path)
    selection = tmp_path / "selection.json"
    paths = ["media/final exports/render-copy.wav", "media/final exports/render.wav",
             "media/final exports/other.wav"]
    manifest(selection, inventory, session, "D3", paths)
    before = (tree_digest(source), hashlib.sha256(inventory.read_bytes()).hexdigest(),
              hashlib.sha256(selection.read_bytes()).hexdigest())
    result = run_enrichment(
        inventory, source, selection, tmp_path / "evidence.db", allow_content_read=True,
        read_policy=ReadPolicy(4096, 4096, 10**9), volume_resolver=fake_resolver(source),
    )
    assert result.state == "COMPLETE"
    assert result.completed_count == 3 and result.duplicate_group_count == 1
    assert before == (tree_digest(source), hashlib.sha256(inventory.read_bytes()).hexdigest(),
                      hashlib.sha256(selection.read_bytes()).hexdigest())
    connection = sqlite3.connect(tmp_path / "evidence.db")
    assert connection.execute("PRAGMA application_id").fetchone()[0] == ENRICHMENT_APPLICATION_ID
    assert connection.execute(
        "SELECT evidence_status,member_count FROM duplicate_groups"
    ).fetchone() == ("CONFIRMED", 2)
    assert {row[0] for row in connection.execute("SELECT stage_name FROM enrichment_stages")} == {
        "selection", "read", "duplicates"
    }
    connection.close()


def test_acknowledgement_volume_boundary_and_stopped_run_fail_closed(tmp_path: Path) -> None:
    source, inventory, session = enrichment_fixture(tmp_path)
    selection = tmp_path / "selection.json"
    manifest(selection, inventory, session, "D4", [
        "media/final exports/other.wav", "media/final exports/render.wav",
    ])
    with pytest.raises(PermissionError, match="acknowledgement"):
        run_enrichment(inventory, source, selection, tmp_path / "denied.db")
    with pytest.raises(Exception, match="same|source volume"):
        run_enrichment(
            inventory, source, selection, tmp_path / "same-volume.db", allow_content_read=True
        )
    stopped = run_enrichment(
        inventory, source, selection, tmp_path / "stopped.db", allow_content_read=True,
        read_policy=ReadPolicy(4096, 4096, 10**9), stop_after=1,
        volume_resolver=fake_resolver(source),
    )
    assert stopped.state == "STOPPED" and stopped.completed_count == 1
    connection = sqlite3.connect(tmp_path / "stopped.db")
    assert connection.execute("SELECT state FROM enrichment_runs").fetchone()[0] == "STOPPED"
    assert connection.execute(
        "SELECT state FROM enrichment_stages WHERE stage_name='read'"
    ).fetchone()[0] == "STOPPED"
    assert connection.execute("SELECT COUNT(*) FROM duplicate_groups").fetchone()[0] == 0
    connection.close()


def test_cli_refuses_same_volume_before_reading_selected_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, inventory, session = enrichment_fixture(tmp_path)
    selection = tmp_path / "selection.json"
    manifest(selection, inventory, session, "D3", ["media/final exports/render.wav"])
    before = tree_digest(source)
    evidence = tmp_path / "evidence.db"
    status = enrichment_main([
        "--inventory", str(inventory), "--source", str(source),
        "--selection", str(selection), "--evidence", str(evidence),
        "--allow-content-read",
    ])
    captured = capsys.readouterr()
    assert status == 1
    assert "same" in captured.err.lower() or "source volume" in captured.err.lower()
    assert not evidence.exists()
    assert tree_digest(source) == before


@pytest.mark.parametrize(("level", "status", "algorithm"), [
    ("D2", "CANDIDATE", "BLAKE3-SAMPLED-V1"),
    ("D4", "CONFIRMED", "SHA-256"),
])
def test_evidence_levels_do_not_overstate_duplicate_status(
    tmp_path: Path, level: str, status: str, algorithm: str
) -> None:
    source, inventory, session = enrichment_fixture(tmp_path)
    selection = tmp_path / "selection.json"
    manifest(selection, inventory, session, level, [
        "media/final exports/render-copy.wav", "media/final exports/render.wav",
    ])
    result = run_enrichment(
        inventory, source, selection, tmp_path / "evidence.db", allow_content_read=True,
        read_policy=ReadPolicy(4096, 4096, 10**9), volume_resolver=fake_resolver(source),
    )
    assert result.duplicate_group_count == 1
    connection = sqlite3.connect(tmp_path / "evidence.db")
    assert connection.execute(
        "SELECT evidence_status,algorithm FROM duplicate_groups"
    ).fetchone() == (status, algorithm)
    connection.close()
