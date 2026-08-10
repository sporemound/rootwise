"""Interval objectives and robust cohort-local Pareto ranking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    name: str
    low: float
    point: float
    high: float
    confidence: float


def robustly_dominates(left: tuple[Interval, ...], right: tuple[Interval, ...]) -> bool:
    """Return true only when left's worst case beats right's best case for minimization."""
    if tuple(item.name for item in left) != tuple(item.name for item in right):
        raise ValueError("objective sets must match")
    no_worse = all(a.high <= b.low for a, b in zip(left, right, strict=True))
    strictly_better = any(a.high < b.low for a, b in zip(left, right, strict=True))
    return no_worse and strictly_better


def pareto_ranks(items: dict[str, tuple[Interval, ...]]) -> dict[str, int]:
    remaining = set(items)
    ranks: dict[str, int] = {}
    rank = 0
    while remaining:
        front = {
            candidate for candidate in remaining
            if not any(
                other != candidate and robustly_dominates(items[other], items[candidate])
                for other in remaining
            )
        }
        if not front:
            raise RuntimeError("Pareto ranking failed to produce a front")
        for candidate in front:
            ranks[candidate] = rank
        remaining -= front
        rank += 1
    return ranks
