"""Create a deterministic source ZIP only after local evidence gates pass."""

from __future__ import annotations

import json
import zipfile
import hashlib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def main() -> int:
    evidence_name = "TEST-WINDOWS.json" if __import__("os").name == "nt" else "TEST-LINUX.json"
    evidence_path = ROOT / "artifacts" / evidence_name
    if not evidence_path.is_file():
        raise SystemExit("local verification evidence is missing; run tools/verify.py")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("status") != "PASS" or not evidence.get("source_unchanged"):
        raise SystemExit("local mandatory gates did not pass; release build refused")
    manifest = json.loads((ROOT / "artifacts" / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    provenance = json.loads(
        (ROOT / "artifacts" / "BUILD_PROVENANCE.json").read_text(encoding="utf-8")
    )
    source_revision = provenance.get("source_revision")
    if not isinstance(source_revision, str) or len(source_revision) != 40:
        raise SystemExit("verified source revision is missing or invalid")
    for relative, expected in manifest["files"].items():
        candidate = ROOT / relative
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            raise SystemExit(f"verified source changed; release build refused: {relative}")
    output = ROOT / "artifacts" / "paretodrive-0.11.0-alpha-source.zip"
    included_roots = ("src", "docs", "tests", "tools")
    files = [ROOT / name for name in (
        "pyproject.toml", "requirements-dev.lock", "requirements-viewer.lock",
        "requirements-analytics.lock",
        "requirements-optimizer.lock",
        "requirements-enrichment.lock",
        "README.md", "LICENSE", "CHANGELOG.md",
    )]
    for directory in included_roots:
        files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
        revision_info = zipfile.ZipInfo("RELEASE_REVISION.txt", (2026, 1, 1, 0, 0, 0))
        revision_info.compress_type = zipfile.ZIP_DEFLATED
        revision_info.external_attr = 0o100644 << 16
        archive.writestr(revision_info, source_revision + "\n")
    for relative, expected in manifest["files"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise SystemExit(f"source changed during packaging: {relative}")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
