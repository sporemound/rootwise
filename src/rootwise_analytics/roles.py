"""Deterministic metadata-only role rules."""

from __future__ import annotations

from dataclasses import dataclass

from .snapshot import SnapshotItem

RULE_VERSION = "roles-0.4.0"


@dataclass(frozen=True)
class RoleResult:
    role: str
    confidence: float
    rule_id: str
    explanation: str
    evidence: tuple[str, ...]


def classify(item: SnapshotItem) -> RoleResult:
    path = item.relative_path.replace("\\", "/").casefold()
    parts = tuple(part for part in path.split("/") if part)
    name = item.name.casefold()
    extension = item.extension.casefold()
    if item.kind != "file":
        return RoleResult("UNKNOWN", 0.2, "R000", "Directories are aggregated, not assigned file roles.", ())
    directory_rules = (
        ({".venv", "venv", "node_modules", "site-packages"}, "DEPENDENCY_ENVIRONMENT", "R110"),
        ({".cache", "cache", "caches"}, "CACHE", "R120"),
        ({"build", "dist", "target", "out"}, "BUILD_OUTPUT", "R130"),
    )
    for markers, role, rule_id in directory_rules:
        match = next((part for part in parts[:-1] if part in markers), None)
        if match is not None:
            return RoleResult(role, 0.96, rule_id, f"Path segment '{match}' identifies {role.lower()}.", (match,))
    project_markers = {"pyproject.toml", "package.json", "cargo.toml", "cmakelists.txt"}
    if name in project_markers or extension in {".sln", ".csproj"}:
        return RoleResult("PROJECT_METADATA", 0.98, "R210", "Filename is a project marker.", (name,))
    if extension in {".py", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".js", ".ts", ".java"}:
        return RoleResult("SOURCE", 0.9, "R220", "Extension is a source-code type.", (extension,))
    if extension in {".json", ".toml", ".yaml", ".yml", ".ini", ".cfg"}:
        return RoleResult("CONFIGURATION", 0.82, "R230", "Extension is a configuration type.", (extension,))
    if name.startswith("readme") or extension in {".md", ".rst"}:
        return RoleResult("DOCUMENTATION", 0.86, "R240", "Name or extension indicates documentation.", (name,))
    if extension in {".zip", ".7z", ".rar", ".tar", ".gz"}:
        return RoleResult("ARCHIVE", 0.88, "R250", "Extension is an archive container.", (extension,))
    if extension in {".exe", ".msi", ".dmg", ".pkg"}:
        return RoleResult("INSTALLER", 0.86, "R260", "Extension is an installer type.", (extension,))
    media = {".wav", ".flac", ".mp3", ".png", ".jpg", ".jpeg", ".mov", ".mp4"}
    if extension in media and any(part in {"exports", "final exports", "renders"} for part in parts[:-1]):
        return RoleResult("FINAL_EXPORT", 0.84, "R310", "Media appears below an export-named directory.", (extension,))
    if extension in media:
        return RoleResult("ORIGINAL_MEDIA", 0.55, "R320", "Media extension observed; originality remains uncertain.", (extension,))
    return RoleResult("UNKNOWN", 0.1, "R999", "No deterministic metadata rule matched.", ())
