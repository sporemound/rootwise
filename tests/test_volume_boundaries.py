from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from paretodrive.errors import BoundaryViolation, VolumeIdentityError
from paretodrive.models import VolumeInfo
from paretodrive.volume import validate_distinct_volumes
from paretodrive.write_guard import WriteGuard


def volume(identity: str, mount: str) -> VolumeInfo:
    return VolumeInfo(identity, mount, "testfs", identity)


def test_same_volume_rejected() -> None:
    with pytest.raises(VolumeIdentityError, match="source volume"):
        validate_distinct_volumes(volume("same", "S:\\"), volume("same", "S:\\other"))


def test_unresolved_identity_rejected() -> None:
    with pytest.raises(VolumeIdentityError, match="empty"):
        validate_distinct_volumes(volume("", "S:\\"), volume("destination", "D:\\"))


def test_guard_rejects_escape(tmp_path: Path) -> None:
    source = volume("source", "S:\\")
    destination = volume("destination", str(tmp_path))
    with patch("paretodrive.write_guard.resolve_volume", return_value=destination):
        guard = WriteGuard(source, tmp_path, destination)
        with pytest.raises(BoundaryViolation, match="escapes"):
            guard.authorize(tmp_path.parent / "outside.db")


def test_guard_rechecks_destination_volume(tmp_path: Path) -> None:
    source = volume("source", "S:\\")
    destination = volume("destination", str(tmp_path))
    changed = volume("changed", str(tmp_path))
    guard = WriteGuard(source, tmp_path, destination)
    with patch("paretodrive.write_guard.resolve_volume", return_value=changed):
        with pytest.raises(BoundaryViolation, match="changed"):
            guard.authorize(tmp_path / "inventory.db")

