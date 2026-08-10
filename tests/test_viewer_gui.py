from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:
    pytest.skip(f"PySide6 native Qt runtime is unavailable: {exc}", allow_module_level=True)

from rootwise_view.decisions import DecisionStore
from rootwise_view.gui import ViewerWindow
from rootwise_view.inventory import InventoryReader

from .test_viewer_inventory import completed_inventory


def test_gui_constructs_bounded_results_without_source_access(tmp_path: Path) -> None:
    inventory_path, session = completed_inventory(tmp_path)
    application = QApplication.instance() or QApplication([])
    with InventoryReader(inventory_path) as reader, DecisionStore(
        tmp_path / "decisions.db", inventory_path=inventory_path
    ) as decisions:
        window = ViewerWindow(reader, decisions, session_id=session)
        window.show()
        application.processEvents()
        assert window.windowTitle().startswith("Rootwise 0.3")
        assert 0 < window.model.rowCount() <= 200
        assert window.sessions.currentData() == session
        window.close()
