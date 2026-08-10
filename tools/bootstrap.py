"""Create a locked Rootwise contributor environment and verify its installed CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).parents[1]
PROFILE_LOCKS = {
    "core": (),
    "headless": (
        "requirements-analytics.lock",
        "requirements-optimizer.lock",
        "requirements-enrichment.lock",
    ),
    "full": (
        "requirements-viewer.lock",
        "requirements-analytics.lock",
        "requirements-optimizer.lock",
        "requirements-enrichment.lock",
    ),
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Create a hash-locked Rootwise development environment."
    )
    result.add_argument(
        "--profile",
        choices=tuple(PROFILE_LOCKS),
        default="core",
        help="core, headless analytics, or the complete Windows reference environment",
    )
    result.add_argument(
        "--environment",
        default=".venv",
        help="new or existing repository-local virtual environment (default: .venv)",
    )
    result.add_argument("--timeout-seconds", type=int, default=600)
    return result


def environment_path(root: Path, supplied: str) -> Path:
    candidate = Path(supplied)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve(strict=False)
    if resolved == root or root.resolve() not in resolved.parents:
        raise ValueError("development environment must be a child of the repository")
    if resolved.exists() and not (resolved / "pyvenv.cfg").is_file():
        raise ValueError("existing environment path is not a Python virtual environment")
    return resolved


def environment_python(environment: Path, platform_name: str = sys.platform) -> Path:
    relative = "Scripts/python.exe" if platform_name == "win32" else "bin/python"
    return environment / relative


def rootwise_executable(environment: Path, platform_name: str = sys.platform) -> Path:
    relative = "Scripts/rootwise.exe" if platform_name == "win32" else "bin/rootwise"
    return environment / relative


def command_plan(
    root: Path,
    environment: Path,
    profile: str,
    *,
    platform_name: str = sys.platform,
    bootstrap_python: str = sys.executable,
) -> list[tuple[str, list[str]]]:
    if profile == "full" and platform_name != "win32":
        raise ValueError("the full profile requires Windows because the Viewer lock is Windows-only")
    python = environment_python(environment, platform_name)
    commands: list[tuple[str, list[str]]] = []
    if not environment.exists():
        commands.append(("create_environment", [bootstrap_python, "-m", "venv", str(environment)]))
    commands.append((
        "install_development_dependencies",
        [str(python), "-m", "pip", "install", "--require-hashes", "--requirement",
         str(root / "requirements-dev.lock")],
    ))
    for lock_name in PROFILE_LOCKS[profile]:
        commands.append((
            f"install_{lock_name.removeprefix('requirements-').removesuffix('.lock')}",
            [str(python), "-m", "pip", "install", "--require-hashes", "--requirement",
             str(root / lock_name)],
        ))
    commands.extend((
        ("install_rootwise", [str(python), "-m", "pip", "install", "--no-deps", "--editable", "."]),
        ("smoke", [str(python), str(root / "tools" / "smoke.py"),
                   "--rootwise", str(rootwise_executable(environment, platform_name))]),
    ))
    return commands


def clean_environment() -> dict[str, str]:
    allowed = (
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "PIP_INDEX_URL", "PIP_TRUSTED_HOST",
        "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
    )
    result = {key: os.environ[key] for key in allowed if key in os.environ}
    result.update({
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "TZ": "UTC",
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    })
    return result


def execute(
    label: str,
    command: list[str],
    *,
    root: Path,
    timeout_seconds: int,
) -> bool:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=clean_environment(),
            timeout=timeout_seconds,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        result = {
            "command": command,
            "duration_seconds": round(time.monotonic() - started, 6),
            "exit_code": completed.returncode,
            "label": label,
            "stderr": completed.stderr,
            "stdout": completed.stdout,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "command": command,
            "duration_seconds": round(time.monotonic() - started, 6),
            "exit_code": None,
            "label": label,
            "stderr": exc.stderr or "",
            "stdout": exc.stdout or "",
            "timed_out": True,
        }
    except OSError as exc:
        result = {
            "command": command,
            "duration_seconds": round(time.monotonic() - started, 6),
            "error": f"{type(exc).__name__}: {exc}",
            "exit_code": None,
            "label": label,
            "stderr": "",
            "stdout": "",
            "timed_out": False,
        }
    print(json.dumps(result, sort_keys=True))
    return result["exit_code"] == 0 and not result["timed_out"]


def main(argv: Sequence[str] | None = None) -> int:
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 3_600:
        argument_parser.error("--timeout-seconds must be between 1 and 3600")
    try:
        environment = environment_path(ROOT, args.environment)
        commands = command_plan(ROOT, environment, args.profile)
    except ValueError as exc:
        argument_parser.error(str(exc))
    for label, command in commands:
        if not execute(label, command, root=ROOT, timeout_seconds=args.timeout_seconds):
            return 1
    print(json.dumps({
        "environment": str(environment),
        "profile": args.profile,
        "python": str(environment_python(environment)),
        "rootwise": str(rootwise_executable(environment)),
        "status": "READY",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
