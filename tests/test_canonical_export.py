from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from paretodrive.canonicalize import export_canonical
from paretodrive.database import InventoryDatabase
from paretodrive.models import ScanConfig
from paretodrive.scanner import MetadataScanner
from paretodrive.errors import ScanStateError
import pytest

from .helpers import RecordingGuard, actual_volume, make_corpus


def test_canonical_export_is_byte_deterministic_and_self_hashing(tmp_path: Path) -> None:
    source = make_corpus(tmp_path / "source")
    database_path = tmp_path / "inventory.db"
    config = ScanConfig(str(source), str(database_path), 100_000, 3, 0)
    guard = RecordingGuard(tmp_path)
    with InventoryDatabase(database_path, guard) as database:
        session, _ = MetadataScanner(source, actual_volume(source), database, config).run()
        digest_one, count_one = export_canonical(database, guard, session, tmp_path / "one.ndjson")
        digest_two, count_two = export_canonical(database, guard, session, tmp_path / "two.ndjson")
    first = (tmp_path / "one.ndjson").read_bytes()
    second = (tmp_path / "two.ndjson").read_bytes()
    assert first == second
    assert digest_one == digest_two == hashlib.sha256(first).hexdigest()
    assert count_one == count_two
    assert b'"status":"COMPLETE"' in first
    if os.name == "nt" and sys.version_info[:2] == (3, 12):
        manifest = json.loads(
            (Path(__file__).parent / "fixtures" / "corpus-v1" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert digest_one == manifest["expected_sha256"]["windows-cpython-3.12"]


def test_canonical_export_rejects_inconsistent_complete_session(tmp_path: Path) -> None:
    source = make_corpus(tmp_path / "source")
    database_path = tmp_path / "inventory.db"
    output = tmp_path / "invalid.ndjson"
    config = ScanConfig(str(source), str(database_path), 100_000, 5, 0)
    guard = RecordingGuard(tmp_path)
    with InventoryDatabase(database_path, guard) as database:
        session, _ = MetadataScanner(source, actual_volume(source), database, config).run()
        database.connection.execute(
            "UPDATE scan_sessions SET observed_count=observed_count+1 WHERE scan_session_id=?",
            (session,),
        )
        database.connection.commit()
        with pytest.raises(ScanStateError, match="consistency"):
            export_canonical(database, guard, session, output)
    assert not output.exists()
