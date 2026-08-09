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

    def validate(self) -> None:
        if not math.isfinite(self.max_files_per_second) or self.max_files_per_second <= 0:
            raise ValueError("max_files_per_second must be positive")
        if not 1 <= self.batch_size <= 10_000:
            raise ValueError("batch_size must be between 1 and 10000")
        if not 0 <= self.sleep_ms_per_batch <= 60_000:
            raise ValueError("sleep_ms_per_batch must be between 0 and 60000")
        if self.stop_after is not None and self.stop_after < 1:
            raise ValueError("stop_after must be positive")


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
