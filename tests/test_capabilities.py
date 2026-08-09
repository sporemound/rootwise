from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from paretodrive.capabilities import detect_capabilities
from paretodrive.models import VolumeInfo


def test_exfat_capabilities_do_not_infer_ntfs_features(tmp_path: Path) -> None:
    volume = VolumeInfo("volume", str(tmp_path), "exFAT", "device")
    with (
        patch("paretodrive.capabilities.resolve_volume", return_value=volume),
        patch("paretodrive.capabilities._windows_read_only", return_value=True),
    ):
        result = detect_capabilities(tmp_path)
    assert result.filesystem_type == "exFAT"
    assert result.source_content_reads is False
    assert result.usn_journal is False
    assert result.ntfs_acl_semantics is False
    assert result.alternate_data_streams is False
    assert result.os_enforced_read_only is True

