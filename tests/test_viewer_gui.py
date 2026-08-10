from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

try:
    from PySide6.QtCore import Qt
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
        assert window.windowTitle() == "Rootwise 0.21.0-alpha — Read-only Inventory"
        assert 0 < window.model.rowCount() <= 200
        assert window.sessions.currentData() == session
        window.close()


def test_gui_displays_and_immediately_refreshes_decision_note_and_revision(
    tmp_path: Path,
) -> None:
    inventory_path, session = completed_inventory(tmp_path)
    application = QApplication.instance() or QApplication([])
    with InventoryReader(inventory_path) as reader, DecisionStore(
        tmp_path / "decisions.db", inventory_path=inventory_path
    ) as decisions:
        decisions.set_decision(session, "project/src/main.py", "PROTECT", note="original")
        window = ViewerWindow(reader, decisions, session_id=session)
        window.show()
        application.processEvents()

        assert window.model.headers[-3:] == ("Decision", "Revision", "Note")
        decided_row = next(
            index
            for index, item in enumerate(window.model.items)
            if item.relative_path == "project/src/main.py"
        )
        undecided_row = next(
            index
            for index, item in enumerate(window.model.items)
            if item.relative_path != "project/src/main.py"
        )
        decision_column = window.model.headers.index("Decision")
        revision_column = window.model.headers.index("Revision")
        note_column = window.model.headers.index("Note")

        assert window.model.data(window.model.index(decided_row, decision_column)) == (
            "RECORDED: PROTECT"
        )
        assert window.model.data(window.model.index(decided_row, revision_column)) == "1"
        assert window.model.data(window.model.index(decided_row, note_column)) == "original"
        assert window.model.data(window.model.index(undecided_row, decision_column)) == "UNDECIDED"
        decided_index = window.model.index(decided_row, decision_column)
        assert window.model.data(
            decided_index, int(Qt.ItemDataRole.BackgroundRole)
        ) is None
        assert window.model.data(
            decided_index, int(Qt.ItemDataRole.ForegroundRole)
        ) is None
        decided_font = window.model.data(decided_index, int(Qt.ItemDataRole.FontRole))
        assert decided_font is not None
        assert decided_font.bold()

        window.table.selectRow(decided_row)
        application.processEvents()
        assert window.decision.currentText() == "PROTECT"
        assert window.note.text() == "original"
        window.decision.setCurrentText("KEEP")
        window.note.setText("reviewed")
        window.apply_button.click()
        application.processEvents()

        assert window.model.data(window.model.index(decided_row, decision_column)) == (
            "RECORDED: KEEP"
        )
        assert window.model.data(window.model.index(decided_row, revision_column)) == "2"
        assert window.model.data(window.model.index(decided_row, note_column)) == "reviewed"
        assert "Recorded KEEP revision 2" in window.status.text()
        window._new_search()
        refreshed_row = next(
            index
            for index, item in enumerate(window.model.items)
            if item.relative_path == "project/src/main.py"
        )
        assert window.model.data(window.model.index(refreshed_row, decision_column)) == (
            "RECORDED: KEEP"
        )
        window.close()


def test_gui_menu_bar_exposes_bounded_view_and_decision_actions(tmp_path: Path) -> None:
    inventory_path, session = completed_inventory(tmp_path)
    application = QApplication.instance() or QApplication([])
    with InventoryReader(inventory_path) as reader, DecisionStore(
        tmp_path / "decisions.db", inventory_path=inventory_path
    ) as decisions:
        window = ViewerWindow(reader, decisions, session_id=session)
        window.show()
        application.processEvents()

        menu_names = [action.text().replace("&", "") for action in window.menuBar().actions()]
        assert menu_names == ["File", "View", "Decisions", "Help"]
        assert window.close_action.shortcut().toString() == "Ctrl+W"
        assert window.refresh_action.shortcut().toString() == "F5"
        assert window.focus_search_action.shortcut().toString() == "Ctrl+F"
        assert window.record_decision_action.shortcut().toString() == "Ctrl+Return"

        window.files_only_action.trigger()
        application.processEvents()
        assert window.kind.currentData() == "file"
        assert all(item.kind == "file" for item in window.model.items)
        window.show_all_action.trigger()
        application.processEvents()
        assert window.kind.currentData() is None

        selected_row = next(
            index
            for index, item in enumerate(window.model.items)
            if item.relative_path == "project/src/main.py"
        )
        window.table.selectRow(selected_row)
        window.decision_value_actions["PROTECT"].trigger()
        window.note.setText("menu-recorded")
        window.record_decision_action.trigger()
        application.processEvents()
        current = decisions.current(session, "project/src/main.py")
        assert current is not None
        assert (current.decision, current.note, current.revision) == (
            "PROTECT", "menu-recorded", 1
        )
        assert window.decision_history_action.isEnabled()
        assert window.session_info_action.isEnabled()
        assert window.safety_action.isEnabled()
        window.close()
