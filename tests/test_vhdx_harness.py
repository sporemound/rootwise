from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path


def test_vhdx_harness_is_plan_only_by_default_and_has_no_disk_number_input(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "tools" / "windows_exfat_vhdx.ps1"
    source = script.read_text(encoding="utf-8")
    assert '[string]$Action = "Plan"' in source
    assert "[int]$DiskNumber" not in source
    assert "Clear-Disk" not in source
    assert "Remove-Item" not in source
    assert "CREATE-DISPOSABLE-EXFAT-VHDX" in source
    if os.name == "nt":
        vhdx = tmp_path / "disposable.vhdx"
        completed = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-File", str(script),
                "-WorkDirectory", str(tmp_path), "-VhdxPath", str(vhdx),
            ],
            cwd=Path(__file__).parents[1], capture_output=True, text=True,
            timeout=20, check=False,
        )
        assert completed.returncode == 0
        assert completed.stderr == ""
        plan = json.loads(completed.stdout)
        assert plan["action"] == "Plan"
        assert plan["physical_disk_selection"] is False
        assert not vhdx.exists()
