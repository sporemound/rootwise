"""Immutable Stage 0.18 recording of one externally evidenced acceptance gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .evaluator import (
    GATE_MEASUREMENT_FIELDS,
    MAX_MANIFEST_BYTES,
    REQUIRED_GATES,
    _evaluate_gate,
    _load_manifest,
)

MAX_MEASUREMENTS_BYTES = 65_536


@dataclass(frozen=True)
class GateRecording:
    gate_id: str
    gate_status: str
    evidence_sha256: str
    source_manifest_digest: str
    output_manifest_digest: str
    recorded_gate_count: int


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def _bounded_notes(value: str) -> str:
    if not value or len(value) > 2_000:
        raise ValueError("notes must be a non-empty bounded string")
    return value


def _load_measurements(path: Path, gate_id: str) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > MAX_MEASUREMENTS_BYTES:
        raise ValueError("measurements file exceeds the size limit")
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != _canonical(value) + b"\n":
        raise ValueError("measurements must be a canonical JSON object")
    required = set(GATE_MEASUREMENT_FIELDS[gate_id])
    if set(value) != required:
        missing = sorted(required - set(value))
        unexpected = sorted(set(value) - required)
        raise ValueError(
            f"measurements keys mismatch; missing={missing}, unexpected={unexpected}"
        )
    return value


def record_gate(
    manifest_path: str | Path,
    evidence_path: str | Path,
    measurements_path: str | Path,
    output_path: str | Path,
    *,
    gate_id: str,
    notes: str,
) -> GateRecording:
    manifest = Path(manifest_path).expanduser().resolve(strict=True)
    evidence = Path(evidence_path).expanduser().resolve(strict=True)
    measurements_file = Path(measurements_path).expanduser().resolve(strict=True)
    output = Path(output_path).expanduser().resolve(strict=False)
    if gate_id not in REQUIRED_GATES:
        raise ValueError(f"unknown acceptance gate: {gate_id}")
    if len({manifest, evidence, measurements_file, output}) != 4:
        raise ValueError("manifest, evidence, measurements, and output must be distinct")
    if output.exists() or not output.parent.is_dir():
        raise ValueError("output manifest must be a new file in an existing directory")
    if not evidence.is_file() or not measurements_file.is_file():
        raise ValueError("evidence and measurements must be existing regular files")

    manifest_value, source_digest = _load_manifest(manifest)
    gates_value = manifest_value["gates"]
    if not isinstance(gates_value, list):
        raise ValueError("manifest gates must be a sorted list")
    existing = [_evaluate_gate(gate) for gate in gates_value]
    identifiers = [str(gate["gate_id"]) for gate in existing]
    if identifiers != sorted(set(identifiers)):
        raise ValueError("manifest gates must be sorted and unique")
    if gate_id in identifiers:
        raise ValueError("manifest already contains this gate; replacement is forbidden")

    measurements = _load_measurements(measurements_file, gate_id)
    evidence_sha256 = _hash_file(evidence)
    gate = {
        "gate_id": gate_id,
        "evidence_sha256": evidence_sha256,
        "measurements": measurements,
        "notes": _bounded_notes(notes),
    }
    evaluated = _evaluate_gate(gate)
    revised = dict(manifest_value)
    revised["gates"] = sorted([*gates_value, gate], key=lambda item: str(item["gate_id"]))
    encoded = _canonical(revised) + b"\n"
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError("revised acceptance manifest exceeds the size limit")
    output.write_bytes(encoded)
    return GateRecording(
        gate_id=gate_id,
        gate_status=str(evaluated["status"]),
        evidence_sha256=evidence_sha256,
        source_manifest_digest=source_digest,
        output_manifest_digest=hashlib.sha256(encoded).hexdigest(),
        recorded_gate_count=len(gates_value) + 1,
    )
