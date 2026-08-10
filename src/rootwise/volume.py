"""Fail-closed operating-system volume identity resolution."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

from .errors import VolumeIdentityError
from .models import VolumeInfo


def _existing_probe(path: Path) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve(strict=False)
    probe = candidate
    while not probe.exists():
        if probe.parent == probe:
            raise VolumeIdentityError(f"no existing ancestor for path: {path}")
        probe = probe.parent
    return probe


def resolve_volume(path: str | os.PathLike[str]) -> VolumeInfo:
    """Resolve an OS-backed identity; never fall back to path-prefix comparison."""
    probe = _existing_probe(Path(path))
    if os.name == "nt":
        return _resolve_windows(probe)
    return _resolve_posix(probe)


def _resolve_windows(path: Path) -> VolumeInfo:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    volume_path = ctypes.create_unicode_buffer(32768)
    if not kernel32.GetVolumePathNameW(str(path), volume_path, len(volume_path)):
        raise VolumeIdentityError(f"GetVolumePathNameW failed: {ctypes.get_last_error()}")

    volume_name = ctypes.create_unicode_buffer(32768)
    if not kernel32.GetVolumeNameForVolumeMountPointW(
        volume_path.value, volume_name, len(volume_name)
    ):
        raise VolumeIdentityError(
            f"GetVolumeNameForVolumeMountPointW failed: {ctypes.get_last_error()}"
        )

    filesystem = ctypes.create_unicode_buffer(256)
    if not kernel32.GetVolumeInformationW(
        volume_path.value, None, 0, None, None, None, filesystem, len(filesystem)
    ):
        raise VolumeIdentityError(f"GetVolumeInformationW failed: {ctypes.get_last_error()}")
    identity = volume_name.value.rstrip("\\").casefold()
    if not identity:
        raise VolumeIdentityError("Windows returned an empty volume identity")
    return VolumeInfo(identity, volume_path.value, filesystem.value or None, volume_name.value)


def _resolve_posix(path: Path) -> VolumeInfo:
    try:
        device_number = path.stat().st_dev
    except OSError as exc:
        raise VolumeIdentityError(f"stat failed for volume probe: {exc}") from exc
    mount = path
    while mount.parent != mount:
        try:
            if mount.parent.stat().st_dev != device_number:
                break
        except OSError as exc:
            raise VolumeIdentityError(f"mount identity resolution failed: {exc}") from exc
        mount = mount.parent
    fs_type = _linux_filesystem_type(mount)
    return VolumeInfo(f"posix-device:{device_number}", str(mount), fs_type, str(device_number))


def _linux_filesystem_type(mount: Path) -> str | None:
    proc_mounts = Path("/proc/mounts")
    if not proc_mounts.is_file():
        return None
    try:
        # This reads OS mount metadata, never source-file content.
        rows = proc_mounts.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    matches: list[tuple[int, str]] = []
    for row in rows:
        parts = row.split()
        if len(parts) >= 3:
            mounted_at = parts[1].replace("\\040", " ")
            if mounted_at == str(mount):
                matches.append((len(mounted_at), parts[2]))
    return max(matches, default=(0, None))[1]


def validate_distinct_volumes(source: VolumeInfo, destination: VolumeInfo) -> None:
    if not source.identity or not destination.identity:
        raise VolumeIdentityError("empty volume identity is not an authorization boundary")
    if source.identity == destination.identity:
        raise VolumeIdentityError("database/output destination is on the source volume")

