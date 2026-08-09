from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from paretodrive_approval.receipt import export_approval_receipt
from paretodrive_preflight.cli import main as preflight_main
from paretodrive_preflight.compiler import compile_preflight_manifest

from .test_approval_receipt import completed_plan, write_declaration


def approval_chain(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    plans, run_id, plan_id, output_digest, decisions_digest = completed_plan(tmp_path)
    declaration = tmp_path / "approval-declaration.json"
    receipt = tmp_path / "approval-receipt.json"
    write_declaration(declaration, run_id, plan_id, output_digest, decisions_digest)
    export_approval_receipt(plans, declaration, receipt)
    plans_db = sqlite3.connect(plans)
    ranking_path = Path(str(plans_db.execute(
        "SELECT ranking_path FROM plan_runs WHERE run_id=?", (run_id,),
    ).fetchone()[0]))
    plans_db.close()
    ranking_db = sqlite3.connect(ranking_path)
    analysis_path = Path(str(ranking_db.execute(
        "SELECT analysis_path FROM ranking_runs ORDER BY finished_at DESC LIMIT 1"
    ).fetchone()[0]))
    ranking_db.close()
    analysis_db = sqlite3.connect(analysis_path)
    inventory = Path(str(analysis_db.execute(
        "SELECT inventory_path FROM analysis_runs ORDER BY finished_at DESC LIMIT 1"
    ).fetchone()[0]))
    analysis_db.close()
    inventory_db = sqlite3.connect(inventory)
    source = Path(str(inventory_db.execute(
        "SELECT source_root FROM scan_sessions ORDER BY finished_at DESC LIMIT 1"
    ).fetchone()[0]))
    inventory_db.close()
    return plans, receipt, inventory, source


def tree_digest(source: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        digest.update(path.relative_to(source).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_preflight_manifest_enumerates_members_without_modifying_inputs_or_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plans, receipt, inventory, source = approval_chain(tmp_path)
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (plans, receipt, inventory)
    }
    source_before = tree_digest(source)
    first_path = tmp_path / "preflight-one.json"
    second_path = tmp_path / "preflight-two.json"
    first = compile_preflight_manifest(plans, receipt, inventory, first_path)
    status = preflight_main([
        "--plans", str(plans), "--approval-receipt", str(receipt),
        "--inventory", str(inventory), "--manifest", str(second_path),
    ])
    cli_result = json.loads(capsys.readouterr().out)
    assert status == 0 and cli_result["manifest_digest"] == first.manifest_digest
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first.archive_count > 0 and first.member_count > 0 and first.logical_bytes > 0
    assert before == {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (plans, receipt, inventory)
    }
    assert tree_digest(source) == source_before
    manifest = json.loads(first_path.read_bytes())
    assert not any(manifest["authorizations"].values())
    assert sum(len(group["members"]) for group in manifest["archives"]) == first.member_count
    recorded = manifest.pop("manifest_digest")
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == recorded


def test_preflight_rejects_inventory_tampering_before_manifest_creation(tmp_path: Path) -> None:
    plans, receipt, inventory, _ = approval_chain(tmp_path)
    connection = sqlite3.connect(inventory)
    connection.execute(
        "UPDATE files SET logical_bytes=logical_bytes+1 WHERE rowid=(SELECT MIN(rowid) FROM files)"
    )
    connection.commit()
    connection.close()
    manifest = tmp_path / "tampered.json"
    with pytest.raises(ValueError, match="logical digest"):
        compile_preflight_manifest(plans, receipt, inventory, manifest)
    assert not manifest.exists()


def test_preflight_rejects_scan_error_regions_and_member_limit(tmp_path: Path) -> None:
    plans, receipt, inventory, _ = approval_chain(tmp_path)
    receipt_value = json.loads(receipt.read_bytes())
    archive_path = next(
        action["relative_path"] for action in receipt_value["plan"]["actions"]
        if action["action"] == "ARCHIVE_AS_UNIT"
    )
    session = receipt_value["source"]["scan_session_id"]
    connection = sqlite3.connect(inventory)
    connection.execute(
        "INSERT INTO scan_errors(scan_session_id,relative_path,operation,error_type,error_code,message) "
        "VALUES(?,?,?,?,?,?)",
        (session, archive_path, "fixture", "SyntheticError", None, "test only"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="scan errors"):
        compile_preflight_manifest(plans, receipt, inventory, tmp_path / "error.json")
    connection = sqlite3.connect(inventory)
    connection.execute("UPDATE scan_errors SET relative_path='' WHERE operation='fixture'")
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="scan errors"):
        compile_preflight_manifest(plans, receipt, inventory, tmp_path / "root-error.json")
    connection = sqlite3.connect(inventory)
    connection.execute("DELETE FROM scan_errors WHERE operation='fixture'")
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="member count"):
        compile_preflight_manifest(
            plans, receipt, inventory, tmp_path / "bounded.json", maximum_members=1
        )
