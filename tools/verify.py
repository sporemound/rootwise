"""Run local mandatory gates with isolated, timed subprocesses and evidence capture."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]
ARTIFACTS = ROOT / "artifacts"
TIMEOUT_SECONDS = 180


def source_manifest() -> dict[str, str]:
    excluded = {".git", ".pytest_cache", ".pytest-tmp", ".tool-tmp", "__pycache__", "artifacts", ".venv", "build", "dist"}
    result: dict[str, str] = {}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in excluded for part in path.relative_to(ROOT).parts):
            continue
        result[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def clean_environment() -> dict[str, str]:
    keep = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC")
    environment = {key: os.environ[key] for key in keep if key in os.environ}
    temporary = ROOT / ".tool-tmp"
    temporary.mkdir(exist_ok=True)
    environment.update({
        "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
        "TZ": "UTC", "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / "src") + os.pathsep + str(ROOT),
        "TEMP": str(temporary), "TMP": str(temporary),
    })
    return environment


def execute(command: list[str], label: str) -> dict[str, object]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command, cwd=ROOT, env=clean_environment(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS, check=False,
        )
        result: dict[str, object] = {
            "label": label, "command": command, "timeout_seconds": TIMEOUT_SECONDS,
            "duration_seconds": round(time.monotonic() - started, 6),
            "exit_code": completed.returncode, "stdout": completed.stdout,
            "stderr": completed.stderr, "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "label": label, "command": command, "timeout_seconds": TIMEOUT_SECONDS,
            "duration_seconds": round(time.monotonic() - started, 6), "exit_code": None,
            "stdout": exc.stdout or "", "stderr": exc.stderr or "", "timed_out": True,
        }
    result["passed"] = (
        result["exit_code"] == 0 and not result["timed_out"] and result["stderr"] == ""
        and bool(result["stdout"])
    )
    return result


def versions() -> dict[str, str]:
    names = ("pytest", "psutil", "coverage", "ruff", "mypy")
    found: dict[str, str] = {"python": platform.python_version()}
    for name in names:
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            found[name] = "not-installed"
    return found


def write_json(name: str, value: object) -> None:
    (ARTIFACTS / name).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def write_checksums() -> None:
    lines = []
    for path in sorted(ARTIFACTS.glob("*.json")):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (ARTIFACTS / "SHA256SUMS.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    ARTIFACTS.mkdir(exist_ok=True)
    before = source_manifest()
    revision = execute(
        ["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"], "git_revision"
    )
    test = execute([sys.executable, "-m", "pytest", "-q"], "pytest")
    fixture = execute([sys.executable, "tools/generate_fixture_evidence.py"], "canonical_fixture")
    after = source_manifest()
    unchanged = before == after
    fixture_value: dict[str, object] | None = None
    if fixture["passed"]:
        try:
            fixture_value = json.loads(str(fixture["stdout"]))
        except json.JSONDecodeError:
            fixture["passed"] = False
    overall = bool(revision["passed"] and test["passed"] and fixture["passed"] and unchanged)
    host_name = "TEST-WINDOWS.json" if os.name == "nt" else "TEST-LINUX.json"
    write_json("SOURCE_MANIFEST.json", {"algorithm": "sha256", "files": before})
    write_json(host_name, {
        "status": "PASS" if overall else "FAIL", "version": "0.2.0-audit.2",
        "platform": platform.platform(),
        "dependencies": versions(), "tests": test, "fixture": fixture,
        "canonical_fixture": fixture_value, "source_unchanged": unchanged,
    })
    write_json("SAFETY-AUDIT.json", {
        "status": "PASS" if test["passed"] else "FAIL",
        "property": "local static and dynamic safety tests", "test_command": test["command"],
    })
    write_json("BUILD_PROVENANCE.json", {
        "status": "VERIFIED" if overall else "FAILED", "source_manifest_sha256": hashlib.sha256(
            json.dumps(before, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(), "platform": platform.platform(), "python": sys.version,
        "source_revision": str(revision["stdout"]).strip(),
        "revision_check": revision,
    })
    write_json("SBOM.json", {
        "runtime_dependencies": [], "development_versions": versions(),
        "development_lock_sha256": hashlib.sha256(
            (ROOT / "requirements-dev.lock").read_bytes()
        ).hexdigest(),
    })
    other_host = "TEST-LINUX.json" if os.name == "nt" else "TEST-WINDOWS.json"
    write_json(other_host, {"status": "NOT_TESTED", "reason": "requires independent host"})
    write_json("TEST-EXFAT-VHDX.json", {
        "status": "NOT_TESTED", "reason": "requires disposable exFAT VHDX on Windows",
        "plan_only_harness": "locally tested without administrator privileges",
    })
    write_json("TEST-READ-ONLY.json", {
        "status": "NOT_TESTED", "reason": "requires OS-enforced read-only source and manifests"
    })
    write_checksums()
    summary = {"status": "PASS" if overall else "FAIL", "test": test["passed"],
               "fixture": fixture["passed"], "source_unchanged": unchanged}
    print(json.dumps(summary, sort_keys=True))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
