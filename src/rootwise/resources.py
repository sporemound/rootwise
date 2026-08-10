"""Fail-closed process, destination-capacity, and workload pacing controls."""

from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import ResourceLimitExceeded


MIB = 1024 * 1024


@dataclass(frozen=True)
class ResourcePolicy:
    max_rss_bytes: int | None
    min_free_destination_bytes: int | None
    active_window_seconds: float
    cooldown_seconds: float


class ResourceController:
    def __init__(
        self,
        destination: Path,
        policy: ResourcePolicy,
        cancelled: Callable[[], bool],
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.destination = destination.resolve(strict=True)
        self.policy = policy
        self.cancelled = cancelled
        self.clock = clock
        self.sleeper = sleeper
        self.window_started = clock()
        self.last_checked = float("-inf")

    def check(self) -> None:
        now = self.clock()
        if now - self.last_checked < 0.5:
            return
        self.last_checked = now
        if self.policy.max_rss_bytes is not None:
            rss = process_rss_bytes()
            if rss is None:
                raise ResourceLimitExceeded("process RSS could not be resolved")
            if rss > self.policy.max_rss_bytes:
                raise ResourceLimitExceeded(
                    f"process RSS {rss} exceeds limit {self.policy.max_rss_bytes}"
                )
        if self.policy.min_free_destination_bytes is not None:
            available = destination_free_bytes(self.destination)
            if available < self.policy.min_free_destination_bytes:
                raise ResourceLimitExceeded(
                    f"destination free bytes {available} below floor "
                    f"{self.policy.min_free_destination_bytes}"
                )
        if now - self.window_started >= self.policy.active_window_seconds:
            remaining = self.policy.cooldown_seconds
            while remaining > 0 and not self.cancelled():
                interval = min(remaining, 0.25)
                self.sleeper(interval)
                remaining -= interval
            self.window_started = self.clock()


def process_rss_bytes() -> int | None:
    if os.name == "nt":
        return _windows_rss_bytes()
    proc_statm = Path("/proc/self/statm")
    if proc_statm.is_file():
        try:
            resident_pages = int(proc_statm.read_text(encoding="ascii").split()[1])
            return resident_pages * int(getattr(os, "sysconf")("SC_PAGE_SIZE"))
        except (OSError, ValueError, IndexError):
            return None
    try:
        import resource

        maximum = getattr(resource, "getrusage")(getattr(resource, "RUSAGE_SELF")).ru_maxrss
        return int(maximum if __import__("sys").platform == "darwin" else maximum * 1024)
    except (ImportError, OSError, ValueError):
        return None


def _windows_rss_bytes() -> int | None:
    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_uint32), ("page_faults", ctypes.c_uint32),
            ("peak_working_set", ctypes.c_size_t), ("working_set", ctypes.c_size_t),
            ("peak_paged_pool", ctypes.c_size_t), ("paged_pool", ctypes.c_size_t),
            ("peak_nonpaged_pool", ctypes.c_size_t), ("nonpaged_pool", ctypes.c_size_t),
            ("pagefile", ctypes.c_size_t), ("peak_pagefile", ctypes.c_size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_uint32
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return None
    return int(counters.working_set)


def destination_free_bytes(path: Path) -> int:
    if os.name == "nt":
        available = ctypes.c_ulonglong()
        total = ctypes.c_ulonglong()
        free = ctypes.c_ulonglong()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetDiskFreeSpaceExW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_ulonglong),
            ctypes.POINTER(ctypes.c_ulonglong),
            ctypes.POINTER(ctypes.c_ulonglong),
        ]
        kernel32.GetDiskFreeSpaceExW.restype = ctypes.c_int
        if not kernel32.GetDiskFreeSpaceExW(
            str(path), ctypes.byref(available), ctypes.byref(total), ctypes.byref(free)
        ):
            raise ResourceLimitExceeded(
                f"destination free space could not be resolved: {ctypes.get_last_error()}"
            )
        return int(available.value)
    try:
        values = getattr(os, "statvfs")(path)
    except OSError as exc:
        raise ResourceLimitExceeded(f"destination free space could not be resolved: {exc}") from exc
    return int(values.f_bavail * values.f_frsize)
