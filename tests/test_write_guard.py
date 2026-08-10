from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from rootwise.models import VolumeInfo
from rootwise.write_guard import WriteGuard


def test_guard_authorizes_child_of_external_root(tmp_path: Path) -> None:
    source = VolumeInfo("source", "S:\\", "exFAT", None)
    destination = VolumeInfo("destination", str(tmp_path), "NTFS", None)
    with patch("rootwise.write_guard.resolve_volume", return_value=destination):
        guard = WriteGuard(source, tmp_path, destination)
        assert guard.authorize(tmp_path / "inventory.db") == tmp_path / "inventory.db"


def test_guarded_output_refuses_existing_final_component(tmp_path: Path) -> None:
    source = VolumeInfo("source", "S:\\", "exFAT", None)
    destination = VolumeInfo("destination", str(tmp_path), "NTFS", None)
    output = tmp_path / "existing.ndjson"
    output.touch()
    with patch("rootwise.write_guard.resolve_volume", return_value=destination):
        guard = WriteGuard(source, tmp_path, destination)
        with pytest.raises(FileExistsError):
            with guard.open_new_binary(output):
                pass
