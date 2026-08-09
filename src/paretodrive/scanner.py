"""Bounded, single-worker, metadata-only directory traversal."""

from __future__ import annotations

import os
import stat
import threading
import time
import unicodedata
import ctypes
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterator

from .database import InventoryDatabase
from .errors import ResourceLimitExceeded
from .models import Observation, ScanConfig, SessionState, VolumeInfo
from .resources import MIB, ResourceController, ResourcePolicy

REPARSE_POINT = 0x400


@contextmanager
def _safe_scandir(
    source: Path, relative_dir: str, volume: VolumeInfo
) -> Iterator[Iterator[os.DirEntry[str]]]:
    """Bind enumeration to non-link directory objects on the authorized volume."""
    if os.name == "nt":
        with _windows_directory_lock(source, relative_dir, volume) as directory:
            with os.scandir(directory) as iterator:
                yield iterator
        return

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    try:
        current = os.open(source, flags)
        descriptors.append(current)
        for component in PurePosixPath(relative_dir).parts:
            current = os.open(component, flags, dir_fd=current)
            descriptors.append(current)
        metadata = os.fstat(current)
        if not stat.S_ISDIR(metadata.st_mode) or f"posix-device:{metadata.st_dev}" != volume.identity:
            raise OSError("queued directory is not an authorized source-volume directory")
        with os.scandir(current) as iterator:
            yield iterator
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@contextmanager
def _windows_directory_lock(
    source: Path, relative_dir: str, volume: VolumeInfo
) -> Iterator[Path]:
    class HandleInfo(ctypes.Structure):
        _fields_ = [
            ("attributes", ctypes.c_uint32), ("creation_low", ctypes.c_uint32),
            ("creation_high", ctypes.c_uint32), ("access_low", ctypes.c_uint32),
            ("access_high", ctypes.c_uint32), ("write_low", ctypes.c_uint32),
            ("write_high", ctypes.c_uint32), ("volume_serial", ctypes.c_uint32),
            ("size_high", ctypes.c_uint32), ("size_low", ctypes.c_uint32),
            ("links", ctypes.c_uint32), ("file_index_high", ctypes.c_uint32),
            ("file_index_low", ctypes.c_uint32),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.GetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.POINTER(HandleInfo)]
    kernel32.GetFinalPathNameByHandleW.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32
    ]
    kernel32.GetFinalPathNameByHandleW.restype = ctypes.c_uint32
    handles: list[int] = []
    path = source
    paths = [source]
    for component in PurePosixPath(relative_dir).parts:
        path = path / component
        paths.append(path)
    try:
        for candidate in paths:
            handle = kernel32.CreateFileW(
                str(candidate), 0x1, 0x3, None, 3, 0x02000000 | 0x00200000, None
            )
            if handle == ctypes.c_void_p(-1).value:
                raise OSError(ctypes.get_last_error(), f"safe directory open failed: {candidate}")
            handles.append(handle)
            information = HandleInfo()
            if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(information)):
                raise OSError(ctypes.get_last_error(), f"directory identity failed: {candidate}")
            if information.attributes & REPARSE_POINT or not information.attributes & 0x10:
                raise OSError(f"queued path is link-like or not a directory: {candidate}")
            final_path = ctypes.create_unicode_buffer(32768)
            length = kernel32.GetFinalPathNameByHandleW(handle, final_path, len(final_path), 0x1)
            if not length or length >= len(final_path):
                raise OSError(ctypes.get_last_error(), f"final directory path failed: {candidate}")
            final = final_path.value.rstrip("\\").casefold()
            identity = volume.identity.rstrip("\\").casefold()
            if final != identity and not final.startswith(identity + "\\"):
                raise OSError(f"queued directory escaped the authorized volume: {candidate}")
        yield path
    finally:
        for handle in reversed(handles):
            kernel32.CloseHandle(handle)


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


def comparison_path(relative_path: str) -> str:
    """Create a comparison-only path without altering the filesystem name."""
    raw = relative_path.replace("\\", "/") if os.name == "nt" else relative_path
    if raw.startswith("/"):
        raise ValueError("relative path became absolute")
    clean: list[str] = []
    for part in PurePosixPath(raw).parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("relative path contains unresolved parent escape")
        clean.append(unicodedata.normalize("NFC", part))
    return "/".join(clean)


def inventory_path(relative_path: str) -> str:
    """Normalize separators while preserving the exact Unicode spelling."""
    raw = relative_path.replace("\\", "/") if os.name == "nt" else relative_path
    if raw.startswith("/"):
        raise ValueError("relative path became absolute")
    clean: list[str] = []
    for part in PurePosixPath(raw).parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("relative path contains unresolved parent escape")
        clean.append(part)
    return "/".join(clean)


def _ns(value: int | float | None) -> int | None:
    return None if value is None else int(value)


class MetadataScanner:
    def __init__(
        self,
        source: Path,
        volume: VolumeInfo,
        database: InventoryDatabase,
        config: ScanConfig,
        cancellation: CancellationToken | None = None,
        resource_controller: ResourceController | None = None,
    ) -> None:
        self.source = source.resolve(strict=True)
        self.volume = volume
        self.database = database
        self.config = config
        self.config.validate()
        self.cancellation = cancellation or CancellationToken()
        self.resources = resource_controller or ResourceController(
            Path(config.database).resolve(strict=False).parent,
            ResourcePolicy(
                None if config.max_rss_mib is None else config.max_rss_mib * MIB,
                None
                if config.min_free_destination_mib is None
                else config.min_free_destination_mib * MIB,
                config.active_window_seconds,
                config.cooldown_seconds,
            ),
            lambda: self.cancellation.cancelled,
        )
        self._processed = 0
        self._rate_started = time.monotonic()

    def run(self, *, resume: bool = False) -> tuple[str, SessionState]:
        session_id = (
            self.database.resume_session(self.volume, str(self.source))
            if resume
            else self.database.start_session(self.volume, self.config)
        )
        try:
            self.resources.check()
            while not self.cancellation.cancelled:
                relative_dir = self.database.next_directory(session_id)
                if relative_dir is None:
                    self.database.finish(session_id, SessionState.COMPLETE)
                    return session_id, SessionState.COMPLETE
                self._scan_directory(session_id, relative_dir)
                if self.config.stop_after is not None and self._processed >= self.config.stop_after:
                    self.cancellation.cancel()
            self.database.finish(session_id, SessionState.STOPPED)
            return session_id, SessionState.STOPPED
        except ResourceLimitExceeded as exc:
            self.database.record_error(
                session_id, "", "resource_check", type(exc).__name__, None, str(exc)
            )
            self.database.record_event(
                session_id, "RESOURCE_STOP", {"error_type": type(exc).__name__, "message": str(exc)}
            )
            self.database.finish(session_id, SessionState.STOPPED)
            return session_id, SessionState.STOPPED
        except (KeyboardInterrupt, SystemExit):
            self.database.finish(session_id, SessionState.STOPPED)
            raise
        except Exception as exc:
            self.database.record_error(
                session_id, "", "scanner", type(exc).__name__, getattr(exc, "errno", None), str(exc)
            )
            self.database.finish(session_id, SessionState.FAILED)
            raise

    def _scan_directory(self, session_id: str, relative_dir: str) -> None:
        observations: list[Observation] = []
        children: list[str] = []
        errors: list[tuple[str, str, str, int | None, str]] = []
        try:
            with _safe_scandir(self.source, relative_dir, self.volume) as iterator:
                for entry in iterator:
                    if self.cancellation.cancelled:
                        break
                    try:
                        observation, traversable = self._observe(entry, relative_dir)
                        observations.append(observation)
                        if traversable:
                            children.append(observation.relative_path)
                    except OSError as exc:
                        entry_relative = inventory_path(
                            f"{relative_dir}/{entry.name}" if relative_dir else entry.name
                        )
                        errors.append(self._error(entry_relative, "stat", exc))
                    self._processed += 1
                    self._rate_limit()
                    if len(observations) + len(errors) >= self.config.batch_size:
                        self._flush(session_id, relative_dir, observations, children, errors, done=False)
                    if self.config.stop_after is not None and self._processed >= self.config.stop_after:
                        self.cancellation.cancel()
                        break
        except OSError as exc:
            errors.append(self._error(relative_dir, "scandir", exc))
            self._flush(session_id, relative_dir, observations, children, errors, done=True)
            return
        self._flush(
            session_id, relative_dir, observations, children, errors,
            done=not self.cancellation.cancelled,
        )

    def _observe(self, entry: os.DirEntry[str], relative_dir: str) -> tuple[Observation, bool]:
        metadata = entry.stat(follow_symlinks=False)
        relative = inventory_path(f"{relative_dir}/{entry.name}" if relative_dir else entry.name)
        attributes = int(getattr(metadata, "st_file_attributes", 0))
        link_like = entry.is_symlink() or bool(attributes & REPARSE_POINT)
        is_directory = stat.S_ISDIR(metadata.st_mode)
        if link_like:
            entry_type = "SYMLINK_DIRECTORY" if is_directory else "SYMLINK"
        elif is_directory:
            entry_type = "DIRECTORY"
        elif stat.S_ISREG(metadata.st_mode):
            entry_type = "FILE"
        else:
            entry_type = "OTHER"
        parent = inventory_path(relative_dir) if relative_dir else None
        display = f"{relative_dir}/{entry.name}" if relative_dir else entry.name
        item = Observation(
            relative_path=relative,
            comparison_path=comparison_path(relative),
            parent_path=parent,
            name=entry.name,
            extension=Path(entry.name).suffix,
            entry_type=entry_type,
            logical_bytes=int(metadata.st_size) if entry_type == "FILE" else 0,
            created_ns=_ns(getattr(metadata, "st_birthtime_ns", None)),
            modified_ns=_ns(getattr(metadata, "st_mtime_ns", None)),
            accessed_ns=_ns(getattr(metadata, "st_atime_ns", None)),
            attributes=attributes,
            depth=len(PurePosixPath(relative).parts),
            display_path=display,
        )
        return item, is_directory and not link_like

    def _flush(
        self,
        session_id: str,
        relative_dir: str,
        observations: list[Observation],
        children: list[str],
        errors: list[tuple[str, str, str, int | None, str]],
        *,
        done: bool,
    ) -> None:
        self.database.commit_directory(
            session_id, relative_dir, observations, children, errors, done=done
        )
        observations.clear()
        children.clear()
        errors.clear()
        if self.config.sleep_ms_per_batch:
            time.sleep(self.config.sleep_ms_per_batch / 1000.0)
        self.resources.check()

    def _rate_limit(self) -> None:
        expected = self._processed / self.config.max_files_per_second
        remaining = expected - (time.monotonic() - self._rate_started)
        if remaining > 0:
            time.sleep(min(remaining, 0.25))

    @staticmethod
    def _error(path: str, operation: str, exc: OSError) -> tuple[str, str, str, int | None, str]:
        return (path, operation, type(exc).__name__, exc.errno, str(exc))
