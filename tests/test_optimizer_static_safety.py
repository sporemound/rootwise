from __future__ import annotations

from pathlib import Path


def test_optimizer_is_proposal_only_and_contains_no_executor_capability() -> None:
    root = Path(__file__).parents[1] / "src" / "rootwise_analytics"
    names = (
        "plan_models.py", "plan_validation.py", "exact_optimizer.py",
        "optimizer_moea.py", "optimizer_pipeline.py", "optimizer_cli.py",
    )
    source = "\n".join((root / name).read_text(encoding="utf-8") for name in names)
    for forbidden in (
        "subprocess", "socket", "shutil", "Path.unlink", "os.remove", "zipfile.ZipFile",
        "tarfile", "send2trash", "os.rename", "os.replace",
    ):
        assert forbidden not in source
    assert "UNAPPROVED" in source
    assert "?mode=ro" in source
    assert "PRAGMA query_only=ON" in source
