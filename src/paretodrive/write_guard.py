"""Central authorization point for every audit-scanner write path."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from .errors import BoundaryViolation
from .models import VolumeInfo
from .volume import resolve_volume, validate_distinct_volumes


class WriteGuard:
    def __init__(
        self,
        source_volume: VolumeInfo,
        allowed_root: str | os.PathLike[str],
        destination_volume: VolumeInfo | None = None,
    ) -> None:
        root = Path(allowed_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise BoundaryViolation(f"write root is not a directory: {root}")
        destination = destination_volume or resolve_volume(root)
        validate_distinct_volumes(source_volume, destination)
        self.source_volume = source_volume
        self.destination_volume = destination
        self.allowed_root = root

    def authorize(self, path: str | os.PathLike[str]) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.allowed_root / candidate
        parent = candidate.parent.resolve(strict=True)
        resolved = parent / candidate.name
        try:
            resolved.relative_to(self.allowed_root)
        except ValueError as exc:
            raise BoundaryViolation(f"write escapes approved root: {resolved}") from exc
        destination = resolve_volume(parent)
        if destination.identity != self.destination_volume.identity:
            raise BoundaryViolation("write path changed destination volume")
        validate_distinct_volumes(self.source_volume, destination)
        return resolved

    def verify_existing(self, path: str | os.PathLike[str]) -> Path:
        """Verify the final object after opening but before an application write."""
        candidate = self.authorize(path)
        if candidate.is_symlink():
            raise BoundaryViolation(f"write target is link-like: {candidate}")
        resolved = candidate.resolve(strict=True)
        try:
            resolved.relative_to(self.allowed_root)
        except ValueError as exc:
            raise BoundaryViolation(f"write target resolves outside approved root: {resolved}") from exc
        if not resolved.is_file():
            raise BoundaryViolation(f"write target is not a regular file: {resolved}")
        destination = resolve_volume(resolved)
        if destination.identity != self.destination_volume.identity:
            raise BoundaryViolation("opened write target is on an unauthorized volume")
        validate_distinct_volumes(self.source_volume, destination)
        return resolved

    def authorize_sqlite_journal(self, database_path: str | os.PathLike[str]) -> Path:
        """Authorize SQLite's exact durable rollback-journal companion path."""
        journal = self.authorize(str(database_path) + "-journal")
        if journal.is_symlink():
            raise BoundaryViolation(f"SQLite journal path is link-like: {journal}")
        return journal

    @contextmanager
    def open_new_binary(self, path: str | os.PathLike[str]) -> Iterator[tuple[Path, BinaryIO]]:
        """Atomically create a new output; existing files and final links fail closed."""
        candidate = self.authorize(path)
        stream = candidate.open("xb")
        try:
            self.verify_existing(candidate)
            yield candidate, stream
        finally:
            stream.close()
