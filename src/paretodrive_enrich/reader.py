"""Bounded read-only file handles and D2/D3/D4 digest construction."""

from __future__ import annotations

import hashlib
import os
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator, Protocol

from blake3 import blake3

REPARSE_POINT = 0x400


class _Hasher(Protocol):
    def update(self, data: bytes) -> object: ...
    def hexdigest(self) -> str: ...


@dataclass(frozen=True)
class InventoryFile:
    relative_path: str
    logical_bytes: int
    modified_ns: int | None


@dataclass(frozen=True)
class ReadPolicy:
    chunk_bytes: int = 1_048_576
    sample_bytes: int = 65_536
    maximum_bytes_per_second: int = 16_777_216

    def validate(self) -> None:
        if not 4_096 <= self.chunk_bytes <= 4_194_304:
            raise ValueError("chunk_bytes must be between 4096 and 4194304")
        if not 4_096 <= self.sample_bytes <= 1_048_576:
            raise ValueError("sample_bytes must be between 4096 and 1048576")
        if self.maximum_bytes_per_second < 1_048_576:
            raise ValueError("maximum_bytes_per_second must be at least 1048576")


class RateLimiter:
    def __init__(self, maximum_bytes_per_second: int) -> None:
        self.maximum = maximum_bytes_per_second
        self.started = time.monotonic()
        self.bytes_read = 0

    def account(self, count: int) -> None:
        self.bytes_read += count
        remaining = self.bytes_read / self.maximum - (time.monotonic() - self.started)
        while remaining > 0:
            time.sleep(min(remaining, 0.25))
            remaining = self.bytes_read / self.maximum - (time.monotonic() - self.started)


def _check_metadata(metadata: os.stat_result, expected: InventoryFile) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError("selected path is no longer a regular file")
    if int(metadata.st_size) != expected.logical_bytes:
        raise OSError("selected file size no longer matches the inventory")
    if expected.modified_ns is not None and int(metadata.st_mtime_ns) != expected.modified_ns:
        raise OSError("selected file modification time no longer matches the inventory")
    if int(getattr(metadata, "st_file_attributes", 0)) & REPARSE_POINT:
        raise OSError("selected file is a reparse point")


@contextmanager
def open_verified(source: Path, expected: InventoryFile) -> Iterator[BinaryIO]:
    current = source
    for component in PurePosixPath(expected.relative_path).parts:
        current = current / component
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or int(
            getattr(metadata, "st_file_attributes", 0)
        ) & REPARSE_POINT:
            raise OSError("selected path contains a link or reparse component")
    candidate = current.resolve(strict=True)
    candidate.relative_to(source)
    before = candidate.stat(follow_symlinks=False)
    _check_metadata(before, expected)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(candidate, flags)
    stream = os.fdopen(descriptor, "rb", buffering=0)
    try:
        opened = os.fstat(stream.fileno())
        _check_metadata(opened, expected)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise OSError("opened file identity differs from the verified path")
        yield stream
        after = os.fstat(stream.fileno())
        _check_metadata(after, expected)
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
            raise OSError("opened file identity changed during enrichment")
    finally:
        stream.close()


def _sample_offsets(size: int, sample_bytes: int) -> tuple[int, ...]:
    if size <= sample_bytes:
        return (0,)
    return tuple(sorted({0, max(0, (size - sample_bytes) // 2), max(0, size - sample_bytes)}))


def hash_file(
    source: Path,
    expected: InventoryFile,
    level: str,
    policy: ReadPolicy,
    limiter: RateLimiter,
) -> tuple[str, str, int]:
    policy.validate()
    bytes_read = 0
    with open_verified(source, expected) as stream:
        if level == "D2":
            hasher = blake3(max_threads=1)
            hasher.update(b"ParetoDrive-D2-sampled-v1\0")
            hasher.update(expected.logical_bytes.to_bytes(8, "big"))
            for offset in _sample_offsets(expected.logical_bytes, policy.sample_bytes):
                stream.seek(offset)
                data = stream.read(min(policy.sample_bytes, expected.logical_bytes - offset))
                limiter.account(len(data))
                bytes_read += len(data)
                hasher.update(offset.to_bytes(8, "big"))
                hasher.update(len(data).to_bytes(8, "big"))
                hasher.update(data)
            return "BLAKE3-SAMPLED-V1", hasher.hexdigest(), bytes_read
        if level == "D3":
            full_hasher: _Hasher = blake3(max_threads=1)
            algorithm = "BLAKE3"
        elif level == "D4":
            full_hasher = hashlib.sha256()
            algorithm = "SHA-256"
        else:
            raise ValueError("unsupported evidence level")
        while True:
            data = stream.read(policy.chunk_bytes)
            if not data:
                break
            limiter.account(len(data))
            bytes_read += len(data)
            full_hasher.update(data)
        return algorithm, full_hasher.hexdigest(), bytes_read
