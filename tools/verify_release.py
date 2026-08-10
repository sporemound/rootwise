"""Extract a source package into a fresh temporary directory and rerun verification."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import time
import json
import zipfile
from pathlib import Path


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    root = Path(__file__).parents[1]
    package = root / "artifacts" / "rootwise-0.21.0-alpha-source.zip"
    if not package.is_file():
        raise SystemExit("release package is missing")
    with tempfile.TemporaryDirectory(prefix="rootwise-release-") as temporary:
        extracted = Path(temporary)
        with zipfile.ZipFile(package, "r") as archive:
            archive.extractall(extracted)
        environment = {key: value for key, value in os.environ.items() if key in {
            "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC",
            "ROOTWISE_ENTRYPOINT_DIR",
        }}
        environment.update({"PYTHONHASHSEED": "0", "TZ": "UTC", "PYTHONUTF8": "1"})
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, "tools/verify.py"], cwd=extracted, env=environment,
            capture_output=True, text=True, timeout=240, check=False,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        result = {
            "command": [sys.executable, "tools/verify.py"],
            "duration_seconds": round(time.monotonic() - started, 6),
            "exit_code": completed.returncode, "stdout": completed.stdout,
            "stderr": completed.stderr, "timeout_seconds": 240,
            "source_archive_name": package.name,
            "source_archive_sha256": _hash_file(package),
            "passed": completed.returncode == 0 and completed.stderr == "" and bool(completed.stdout),
        }
        (root / "artifacts" / "VERIFY-RELEASE.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
