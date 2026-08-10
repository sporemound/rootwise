"""Explicit filesystem capability reporting without inferring missing evidence."""

from __future__ import annotations

import ctypes
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import VolumeInfo
from .volume import resolve_volume


@dataclass(frozen=True)
class FilesystemCapabilities:
    volume_identity: str
    filesystem_type: str | None
    metadata_scan: bool
    source_content_reads: bool
    stable_file_ids: bool | None
    usn_journal: bool | None
    ntfs_acl_semantics: bool | None
    alternate_data_streams: bool | None
    hardlinks: bool | None
    reparse_detection: bool
    os_enforced_read_only: bool | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_capabilities(path: str | os.PathLike[str]) -> FilesystemCapabilities:
    volume = resolve_volume(path)
    filesystem = (volume.filesystem_type or "").upper()
    is_ntfs = filesystem == "NTFS"
    is_exfat = filesystem == "EXFAT"
    return FilesystemCapabilities(
        volume_identity=volume.identity,
        filesystem_type=volume.filesystem_type,
        metadata_scan=True,
        source_content_reads=False,
        stable_file_ids=True if is_ntfs else (False if is_exfat else None),
        usn_journal=True if is_ntfs else (False if is_exfat else None),
        ntfs_acl_semantics=True if is_ntfs else (False if is_exfat else None),
        alternate_data_streams=True if is_ntfs else (False if is_exfat else None),
        hardlinks=True if is_ntfs else (False if is_exfat else None),
        reparse_detection=os.name == "nt",
        os_enforced_read_only=_windows_read_only(Path(path), volume) if os.name == "nt" else None,
    )


def _windows_read_only(path: Path, volume: VolumeInfo) -> bool:
    del path
    flags = ctypes.c_uint32()
    filesystem = ctypes.create_unicode_buffer(256)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not kernel32.GetVolumeInformationW(
        volume.mount_path, None, 0, None, None, ctypes.byref(flags), filesystem, len(filesystem)
    ):
        raise OSError(ctypes.get_last_error(), "GetVolumeInformationW capability query failed")
    return bool(flags.value & 0x00080000)

