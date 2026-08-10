"""Bottom-up aggregates and project/relationship evidence."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from .roles import RoleResult
from .snapshot import SnapshotItem

PROJECT_RULE_VERSION = "projects-0.4.0"
PROJECT_MARKERS = {"pyproject.toml": 5, "package.json": 5, "cargo.toml": 5, "cmakelists.txt": 4}


@dataclass
class Aggregate:
    recursive_bytes: int = 0
    file_count: int = 0
    directory_count: int = 0
    roles: Counter[str] = field(default_factory=Counter)

    @property
    def role_coherence(self) -> float:
        total = sum(self.roles.values())
        if total == 0:
            return 0.0
        active = [count for count in self.roles.values() if count]
        if len(active) == 1:
            return 1.0
        entropy = -sum((count / total) * math.log(count / total) for count in active)
        return 1.0 - entropy / math.log(len(active))


def ancestors(path: str | None) -> list[str]:
    if not path:
        return [""]
    parts = path.split("/")
    return ["/".join(parts[:index]) for index in range(len(parts), 0, -1)] + [""]


def aggregate(items: list[SnapshotItem], roles: dict[str, RoleResult]) -> dict[str, Aggregate]:
    result: dict[str, Aggregate] = {"": Aggregate()}
    for item in items:
        if item.kind == "directory":
            result.setdefault(item.relative_path, Aggregate())
            for directory in ancestors(item.parent_path):
                result.setdefault(directory, Aggregate()).directory_count += 1
        else:
            role = roles[item.relative_path].role
            for directory in ancestors(item.parent_path):
                current = result.setdefault(directory, Aggregate())
                current.recursive_bytes += item.logical_bytes
                current.file_count += 1
                current.roles[role] += 1
    return result


def projects(items: list[SnapshotItem]) -> dict[str, tuple[int, tuple[str, ...]]]:
    scores: dict[str, int] = {}
    markers: dict[str, list[str]] = {}
    for item in items:
        if item.kind != "file":
            continue
        weight = PROJECT_MARKERS.get(item.name.casefold())
        if weight is None and item.extension.casefold() in {".sln", ".csproj"}:
            weight = 5
        if weight is not None:
            parent = item.parent_path or ""
            scores[parent] = scores.get(parent, 0) + weight
            markers.setdefault(parent, []).append(item.name)
    return {
        path: (score, tuple(sorted(markers[path], key=str.casefold)))
        for path, score in scores.items() if score >= 4
    }
