"""Create a development environment using the checked-in lock file."""

from __future__ import annotations

import subprocess
import sys
import os
import json
import time
from pathlib import Path


def main() -> int:
    root = Path(__file__).parents[1]
    environment = root / ".venv"
    commands = [
        [sys.executable, "-m", "venv", str(environment)],
        [str(environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")),
         "-m", "pip", "install", "--require-hashes", "-r", str(root / "requirements-dev.lock")],
    ]
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC")
    clean = {key: os.environ[key] for key in allowed if key in os.environ}
    clean.update({"PYTHONHASHSEED": "0", "TZ": "UTC", "PYTHONUTF8": "1",
                  "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"})
    for command in commands:
        started = time.monotonic()
        completed = subprocess.run(
            command, cwd=root, env=clean, timeout=300, check=False,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        print(json.dumps({
            "command": command, "duration_seconds": round(time.monotonic() - started, 6),
            "exit_code": completed.returncode, "stdout": completed.stdout,
            "stderr": completed.stderr, "timeout_seconds": 300,
        }, sort_keys=True))
        if completed.returncode or completed.stderr:
            return completed.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
