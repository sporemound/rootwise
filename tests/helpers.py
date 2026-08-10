from __future__ import annotations

import json
import os
import ctypes
from contextlib import contextmanager
from typing import BinaryIO, Iterator
from pathlib import Path

from rootwise.models import VolumeInfo
from rootwise.volume import resolve_volume


class RecordingGuard:
    """Test-only destination guard; production boundary behavior has separate unit tests."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def authorize(self, path: str | os.PathLike[str]) -> Path:
        candidate = Path(path).resolve()
        candidate.relative_to(self.root)
        return candidate

    def verify_existing(self, path: str | os.PathLike[str]) -> Path:
        return self.authorize(path)

    def authorize_sqlite_journal(self, database_path: str | os.PathLike[str]) -> Path:
        return self.authorize(str(database_path) + "-journal")

    def open_database_lease(self, database_path: str | os.PathLike[str]) -> BinaryIO:
        lease = self.authorize(str(database_path) + "-scanlock")
        return lease.open("r+b" if lease.exists() else "x+b")

    @contextmanager
    def open_new_binary(self, path: str | os.PathLike[str]) -> Iterator[tuple[Path, BinaryIO]]:
        candidate = self.authorize(path)
        with candidate.open("xb") as stream:
            yield candidate, stream


def fake_volume(identity: str = "fixture-source") -> VolumeInfo:
    return VolumeInfo(identity, "synthetic", "synthetic", identity)


def actual_volume(source: Path) -> VolumeInfo:
    return resolve_volume(source)


def make_corpus(destination: Path) -> Path:
    manifest_path = Path(__file__).parent / "fixtures" / "corpus-v1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    destination.mkdir()
    for relative in manifest["directories"]:
        (destination / relative).mkdir(parents=True, exist_ok=True)
    fixed = manifest["fixed_timestamp_ns"]
    for relative, content in manifest["files"].items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        os.utime(path, ns=(fixed, fixed))
        _set_windows_file_times(path, fixed)
    for directory in sorted(destination.rglob("*"), reverse=True):
        if directory.is_dir():
            os.utime(directory, ns=(fixed, fixed))
            _set_windows_file_times(directory, fixed)
    return destination


def _set_windows_file_times(path: Path, unix_ns: int) -> None:
    if os.name != "nt":
        return

    class FileTime(ctypes.Structure):
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

    ticks = unix_ns // 100 + 116_444_736_000_000_000
    timestamp = FileTime(ticks & 0xFFFFFFFF, ticks >> 32)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.SetFileTime.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(FileTime), ctypes.POINTER(FileTime), ctypes.POINTER(FileTime)
    ]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateFileW(
        str(path), 0x100, 0x7, None, 3, 0x02000000 if path.is_dir() else 0, None
    )
    invalid = ctypes.c_void_p(-1).value
    if handle == invalid:
        raise OSError(ctypes.get_last_error(), f"CreateFileW failed for fixture: {path}")
    try:
        if not kernel32.SetFileTime(
            handle, ctypes.byref(timestamp), ctypes.byref(timestamp), ctypes.byref(timestamp)
        ):
            raise OSError(ctypes.get_last_error(), f"SetFileTime failed for fixture: {path}")
    finally:
        kernel32.CloseHandle(handle)
