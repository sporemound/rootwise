"""Explicit immutable selection-manifest contract for content reads."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "rootwise-enrichment-selection-1"
LEVELS = {"D2", "D3", "D4"}


@dataclass(frozen=True)
class Selection:
    scan_session_id: str
    inventory_digest: str
    evidence_level: str
    paths: tuple[str, ...]
    manifest_digest: str


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or value.startswith(("/", "\\")):
        raise ValueError("selection paths must be nonempty normalized relative strings")
    normalized = value.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("selection path contains an unsafe component")
    return "/".join(parts)


def load_selection(path: str | Path, *, maximum_files: int = 10_000) -> Selection:
    manifest_path = Path(path).expanduser().resolve(strict=True)
    raw = manifest_path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("selection manifest is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "scan_session_id", "inventory_digest", "evidence_level", "paths"
    }:
        raise ValueError("selection manifest fields do not match the required schema")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError("selection manifest schema version mismatch")
    session = value["scan_session_id"]
    digest = value["inventory_digest"]
    level = value["evidence_level"]
    raw_paths = value["paths"]
    if not isinstance(session, str) or not session or len(session) > 128:
        raise ValueError("selection scan session ID is invalid")
    if not isinstance(digest, str) or len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError("selection inventory digest must be lowercase SHA-256")
    if level not in LEVELS:
        raise ValueError("selection evidence level must be D2, D3, or D4")
    if not isinstance(raw_paths, list) or not 1 <= len(raw_paths) <= maximum_files:
        raise ValueError("selection path count is outside the configured bound")
    paths = tuple(_path(item) for item in raw_paths)
    if paths != tuple(sorted(set(paths))):
        raise ValueError("selection paths must be unique and bytewise sorted")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return Selection(session, digest, str(level), paths, hashlib.sha256(canonical).hexdigest())
