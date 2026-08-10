from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.prepare_scale_corpus import (
    CorpusSpec,
    _canonical,
    _plan,
    main,
    prepare_corpus,
)


def test_plan_is_nonexecuting_and_requires_a_million_entries(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    plan = _plan(root, CorpusSpec(entry_count=1_000_000, shard_count=256), 256)
    assert plan["code_version"] == "0.23.0-alpha"
    assert plan["execution_authorized"] is False
    assert plan["entry_count"] == 1_000_000
    assert plan["content_bytes_per_file"] == 0
    assert plan["automatic_cleanup"] is False
    assert plan["corpus_root"] == str(root.resolve())
    with pytest.raises(ValueError, match="1000000"):
        CorpusSpec(entry_count=999_999, shard_count=256).validate()
    assert not root.exists()


def test_prepare_stops_and_resumes_without_overwriting(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    manifest = tmp_path / "manifest.json"
    queries = tmp_path / "queries.json"
    spec = CorpusSpec(entry_count=12, shard_count=3)
    stopped = prepare_corpus(
        root,
        manifest,
        queries,
        spec=spec,
        query_count=100,
        maximum_files_per_second=100_000,
        batch_size=4,
        sleep_ms_per_batch=0,
        stop_after=5,
        minimum_entry_count=1,
    )
    assert stopped["status"] == "STOPPED"
    assert stopped["created_this_run"] == 5
    assert not manifest.exists()
    assert not queries.exists()

    completed = prepare_corpus(
        root,
        manifest,
        queries,
        spec=spec,
        query_count=100,
        maximum_files_per_second=100_000,
        batch_size=4,
        sleep_ms_per_batch=0,
        stop_after=None,
        minimum_entry_count=1,
    )
    assert completed["status"] == "COMPLETE"
    assert completed["created_this_run"] == 7
    assert completed["verified_file_count"] == 12
    assert manifest.read_bytes() == _canonical(json.loads(manifest.read_bytes()))
    query_values = json.loads(queries.read_bytes())
    assert len(query_values) == 100
    assert queries.read_bytes() == _canonical(query_values)
    assert all(path.stat().st_size == 0 for path in root.rglob("*.dat"))


def test_resume_rejects_unowned_and_tampered_destinations(tmp_path: Path) -> None:
    spec = CorpusSpec(entry_count=4, shard_count=2)
    unowned = tmp_path / "unowned"
    unowned.mkdir()
    with pytest.raises(ValueError, match="ownership marker"):
        prepare_corpus(
            unowned, tmp_path / "m1.json", tmp_path / "q1.json", spec=spec,
            query_count=100, maximum_files_per_second=100_000, batch_size=2,
            sleep_ms_per_batch=0, stop_after=None, minimum_entry_count=1,
        )

    owned = tmp_path / "owned"
    prepare_corpus(
        owned, tmp_path / "m2.json", tmp_path / "q2.json", spec=spec,
        query_count=100, maximum_files_per_second=100_000, batch_size=2,
        sleep_ms_per_batch=0, stop_after=1, minimum_entry_count=1,
    )
    (owned / "foreign.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected corpus entry"):
        prepare_corpus(
            owned, tmp_path / "m3.json", tmp_path / "q3.json", spec=spec,
            query_count=100, maximum_files_per_second=100_000, batch_size=2,
            sleep_ms_per_batch=0, stop_after=None, minimum_entry_count=1,
        )

    changed = tmp_path / "changed"
    prepare_corpus(
        changed, tmp_path / "m4.json", tmp_path / "q4.json", spec=spec,
        query_count=100, maximum_files_per_second=100_000, batch_size=2,
        sleep_ms_per_batch=0, stop_after=1, minimum_entry_count=1,
    )
    next(changed.rglob("*.dat")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="unexpected corpus entry"):
        prepare_corpus(
            changed, tmp_path / "m5.json", tmp_path / "q5.json", spec=spec,
            query_count=100, maximum_files_per_second=100_000, batch_size=2,
            sleep_ms_per_batch=0, stop_after=None, minimum_entry_count=1,
        )


def test_prepare_rejects_outputs_inside_corpus_and_existing_outputs(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    spec = CorpusSpec(entry_count=2, shard_count=1)
    with pytest.raises(ValueError, match="outside"):
        prepare_corpus(
            root, root / "manifest.json", root / "queries.json", spec=spec,
            query_count=100, maximum_files_per_second=100_000, batch_size=1,
            sleep_ms_per_batch=0, stop_after=None, minimum_entry_count=1,
        )
    occupied = tmp_path / "manifest.json"
    occupied.write_text("occupied", encoding="utf-8")
    with pytest.raises(ValueError, match="new files"):
        prepare_corpus(
            root, occupied, tmp_path / "queries-2.json", spec=spec,
            query_count=100, maximum_files_per_second=100_000, batch_size=1,
            sleep_ms_per_batch=0, stop_after=None, minimum_entry_count=1,
        )


def test_cli_requires_explicit_execution_without_creating_the_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "corpus"
    result = main([
        "prepare", "--corpus-root", str(root), "--manifest", str(tmp_path / "manifest.json"),
        "--queries", str(tmp_path / "queries.json"), "--entry-count", "1000000",
        "--shard-count", "256",
    ])
    assert result == 1
    assert "explicit --execute" in capsys.readouterr().err
    assert not root.exists()
