"""Data-only contracts for proposal generation and independent validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Action(IntEnum):
    KEEP_UNPACKED = 0
    ARCHIVE_AS_UNIT = 1
    DEFER_TO_CHILDREN = 2
    PROTECTED = 3


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    relative_path: str
    parent_id: str | None
    recursive_bytes: int
    file_count: int
    eligible: bool
    protected: bool
    preservation_risk: float
    incoherence: float


@dataclass(frozen=True)
class PlanPolicy:
    maximum_archive_bytes: int
    destination_available_bytes: int
    destination_safety_margin: float = 0.15

    @property
    def usable_destination_bytes(self) -> int:
        return int(self.destination_available_bytes * (1.0 - self.destination_safety_margin))


@dataclass(frozen=True)
class PlanMetrics:
    negative_recoverable_bytes: float
    remaining_loose_files: float
    preservation_risk: float
    peak_temporary_bytes: float
    archive_count: float
    archive_incoherence: float

    def values(self) -> tuple[float, ...]:
        return (
            self.negative_recoverable_bytes,
            self.remaining_loose_files,
            self.preservation_risk,
            self.peak_temporary_bytes,
            self.archive_count,
            self.archive_incoherence,
        )


@dataclass(frozen=True)
class ValidatedPlan:
    plan_id: str
    actions: tuple[tuple[str, Action], ...]
    metrics: PlanMetrics
    archive_names: tuple[tuple[str, str], ...]
