from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from blake3 import blake3

from paretodrive_enrich.reader import InventoryFile, RateLimiter, ReadPolicy, hash_file
from paretodrive_enrich.selection import load_selection


def test_selection_is_explicit_sorted_and_digest_bound(tmp_path: Path) -> None:
    manifest = tmp_path / "selection.json"
    manifest.write_text(
        '{"evidence_level":"D3","inventory_digest":"' + "a" * 64
        + '","paths":["a.bin","b.bin"],"scan_session_id":"session",'
          '"schema_version":"paretodrive-enrichment-selection-1"}', encoding="utf-8"
    )
    selection = load_selection(manifest)
    assert selection.paths == ("a.bin", "b.bin")
    assert len(selection.manifest_digest) == 64
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        '"a.bin","b.bin"', '"b.bin","a.bin"'
    ), encoding="utf-8")
    with pytest.raises(ValueError, match="sorted"):
        load_selection(manifest)


def test_d2_samples_and_d3_d4_read_complete_file_without_writes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = bytes(range(256)) * 1024
    path = source / "payload.bin"
    path.write_bytes(content)
    metadata = path.stat()
    expected = InventoryFile("payload.bin", len(content), metadata.st_mtime_ns)
    policy = ReadPolicy(chunk_bytes=4096, sample_bytes=4096, maximum_bytes_per_second=10**9)
    mode_before = os.stat(path).st_mode
    d2 = hash_file(source, expected, "D2", policy, RateLimiter(10**9))
    d3 = hash_file(source, expected, "D3", policy, RateLimiter(10**9))
    d4 = hash_file(source, expected, "D4", policy, RateLimiter(10**9))
    assert d2[0] == "BLAKE3-SAMPLED-V1" and d2[2] == 3 * 4096
    assert d3 == ("BLAKE3", blake3(content).hexdigest(), len(content))
    assert d4 == ("SHA-256", hashlib.sha256(content).hexdigest(), len(content))
    assert path.read_bytes() == content
    assert os.stat(path).st_mode == mode_before


def test_reader_rejects_metadata_drift(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    path = source / "file.bin"
    path.write_bytes(b"changed")
    with pytest.raises(OSError, match="size"):
        hash_file(source, InventoryFile("file.bin", 1, path.stat().st_mtime_ns), "D3",
                  ReadPolicy(maximum_bytes_per_second=10**9), RateLimiter(10**9))
