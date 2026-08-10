"""Run a fast smoke check against the installed Rootwise command hierarchy."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


CHECKS = (
    ((), "Audit-first filesystem inventory"),
    (("scan",), "usage: rootwise scan"),
    (("view",), "usage: rootwise view"),
    (("analyze",), "usage: rootwise analyze"),
    (("plan",), "usage: rootwise plan"),
    (("evidence",), "usage: rootwise evidence"),
    (("verify",), "usage: rootwise verify"),
)


def installed_rootwise() -> Path:
    name = "rootwise.exe" if sys.platform == "win32" else "rootwise"
    return Path(sys.executable).with_name(name)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Smoke-test the installed Rootwise CLI.")
    result.add_argument("--rootwise", type=Path, default=installed_rootwise())
    result.add_argument("--timeout-seconds", type=int, default=20)
    return result


def clean_environment() -> dict[str, str]:
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC")
    result = {key: os.environ[key] for key in allowed if key in os.environ}
    result.update({
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "TZ": "UTC",
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
    })
    return result


def main(argv: Sequence[str] | None = None) -> int:
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 300:
        argument_parser.error("--timeout-seconds must be between 1 and 300")
    try:
        executable = args.rootwise.expanduser().resolve(strict=True)
    except OSError as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "status": "FAIL"}, sort_keys=True))
        return 1
    if not executable.is_file():
        print(json.dumps({"error": "rootwise path is not a file", "status": "FAIL"}, sort_keys=True))
        return 1
    results: list[dict[str, object]] = []
    for arguments, expected in CHECKS:
        command = [str(executable), *arguments, "--help"]
        try:
            completed = subprocess.run(
                command,
                env=clean_environment(),
                timeout=args.timeout_seconds,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            passed = (
                completed.returncode == 0
                and completed.stderr == ""
                and expected in completed.stdout
            )
            result = {
                "arguments": [*arguments, "--help"],
                "exit_code": completed.returncode,
                "passed": passed,
                "timed_out": False,
            }
            if not passed:
                result.update({"stderr": completed.stderr, "stdout": completed.stdout})
        except subprocess.TimeoutExpired as exc:
            result = {
                "arguments": [*arguments, "--help"],
                "exit_code": None,
                "passed": False,
                "stderr": exc.stderr or "",
                "stdout": exc.stdout or "",
                "timed_out": True,
            }
        except OSError as exc:
            result = {
                "arguments": [*arguments, "--help"],
                "error": f"{type(exc).__name__}: {exc}",
                "exit_code": None,
                "passed": False,
                "stderr": "",
                "stdout": "",
                "timed_out": False,
            }
        results.append(result)
    passed = all(bool(result["passed"]) for result in results)
    print(json.dumps({
        "checks": results,
        "executable": executable.name,
        "status": "PASS" if passed else "FAIL",
    }, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
