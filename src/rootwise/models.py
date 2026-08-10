"""Small immutable data models for raw scanner observations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class SessionState(str, Enum):
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class VolumeInfo:
    identity: str
    mount_path: str
    filesystem_type: str | None
    device: str | None


@dataclass(frozen=True)
class ScanConfig:
    source: str
    database: str
    max_files_per_second: float = 250.0
    batch_size: int = 256
    sleep_ms_per_batch: int = 25
    stop_after: int | None = None
    max_rss_mib: int | None = 512
    min_free_destination_mib: int | None = 1024
    active_window_seconds: float = 30.0
    cooldown_seconds: float = 2.0

    def validate(self) -> None:
        if not math.isfinite(self.max_files_per_second) or self.max_files_per_second <= 0:
            raise ValueError("max_files_per_second must be positive")
        if not 1 <= self.batch_size <= 10_000:
            raise ValueError("batch_size must be between 1 and 10000")
        if not 0 <= self.sleep_ms_per_batch <= 60_000:
            raise ValueError("sleep_ms_per_batch must be between 0 and 60000")
        if self.stop_after is not None and self.stop_after < 1:
            raise ValueError("stop_after must be positive")
        if self.max_rss_mib is not None and self.max_rss_mib < 32:
            raise ValueError("max_rss_mib must be at least 32 or disabled")
        if self.min_free_destination_mib is not None and self.min_free_destination_mib < 1:
            raise ValueError("min_free_destination_mib must be positive or disabled")
        if not math.isfinite(self.active_window_seconds) or self.active_window_seconds <= 0:
            raise ValueError("active_window_seconds must be finite and positive")
        if not math.isfinite(self.cooldown_seconds) or self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be finite and nonnegative")


@dataclass(frozen=True)
class Observation:
    relative_path: str
    comparison_path: str
    parent_path: str | None
    name: str
    extension: str
    entry_type: str
    logical_bytes: int
    created_ns: int | None
    modified_ns: int | None
    accessed_ns: int | None
    attributes: int
    depth: int
    display_path: str
    observation_status: str = "OBSERVED"
