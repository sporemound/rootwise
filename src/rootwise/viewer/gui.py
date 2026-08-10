"""Bounded PySide6 review interface over the tested viewer backends."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QAction, QActionGroup, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from rootwise import __version__

from .decisions import DECISIONS, DecisionRecord, DecisionStore
from .inventory import InventoryItem, InventoryReader

PAGE_SIZE = 200
RECORDED_FONT = QFont()
RECORDED_FONT.setBold(True)


class InventoryTableModel(QAbstractTableModel):
    headers = (
        "Type", "Name", "Path", "Extension", "Bytes", "Status",
        "Decision", "Revision", "Note",
    )

    def __init__(self) -> None:
        super().__init__()
        self.items: list[InventoryItem] = []
        self.decisions: dict[str, DecisionRecord] = {}

    def rowCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        return 0 if parent.isValid() else len(self.items)

    def columnCount(  # noqa: N802
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid():
            return None
        item = self.items[index.row()]
        decision = self.decisions.get(item.relative_path)
        if role == int(Qt.ItemDataRole.FontRole) and decision is not None:
            return RECORDED_FONT
        if role == int(Qt.ItemDataRole.ToolTipRole):
            if decision is None:
                return "No decision recorded"
            return f"{decision.decision} revision {decision.revision}: {decision.note}"
        if role != int(Qt.ItemDataRole.DisplayRole):
            return None
        values = (
            item.kind,
            item.name,
            item.relative_path,
            item.extension,
            str(item.logical_bytes),
            item.observation_status,
            "UNDECIDED" if decision is None else f"RECORDED: {decision.decision}",
            "" if decision is None else str(decision.revision),
            "" if decision is None else decision.note,
        )
        return values[index.column()]

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = int(Qt.ItemDataRole.DisplayRole)
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == int(Qt.ItemDataRole.DisplayRole):
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def replace(
        self, items: list[InventoryItem], decisions: dict[str, DecisionRecord]
    ) -> None:
        self.beginResetModel()
        self.items = items
        self.decisions = decisions
        self.endResetModel()

    def update_decision(self, record: DecisionRecord) -> None:
        self.decisions[record.relative_path] = record
        for row, item in enumerate(self.items):
            if item.relative_path == record.relative_path:
                self.dataChanged.emit(
                    self.index(row, 0),
                    self.index(row, len(self.headers) - 1),
                    [
                        int(Qt.ItemDataRole.DisplayRole),
                        int(Qt.ItemDataRole.FontRole),
                        int(Qt.ItemDataRole.ToolTipRole),
                    ],
                )
                return


class ViewerWindow(QMainWindow):
    def __init__(
        self,
        reader: InventoryReader,
        decisions: DecisionStore,
        *,
        session_id: str | None,
    ) -> None:
        super().__init__()
        self.reader = reader
        self.decisions = decisions
        self.offset = 0
        self.setWindowTitle(f"Rootwise {__version__} — Read-only Inventory")
        self.resize(1200, 750)

        self.sessions = QComboBox()
        complete = [item for item in reader.sessions() if item.state == "COMPLETE"]
        if not complete:
            raise ValueError("inventory has no COMPLETE scan session")
        for item in complete:
            self.sessions.addItem(
                f"{item.started_at} — {item.observed_count} observations", item.scan_session_id
            )
        if session_id is not None:
            index = self.sessions.findData(session_id)
            if index < 0:
                raise ValueError("requested COMPLETE session was not found")
            self.sessions.setCurrentIndex(index)

        self.query = QLineEdit()
        self.query.setPlaceholderText("Search observed paths")
        self.kind = QComboBox()
        self.kind.addItem("Files and directories", None)
        self.kind.addItem("Files", "file")
        self.kind.addItem("Directories", "directory")
        self.search_button = QPushButton("Search")
        self.previous_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.status = QLabel()

        self.model = InventoryTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.decision = QComboBox()
        self.decision.addItems(DECISIONS)
        self.decision.setCurrentText("UNKNOWN")
        self.note = QLineEdit()
        self.note.setPlaceholderText("Decision note (optional)")
        self.apply_button = QPushButton("Record decision")
        self.apply_button.setEnabled(False)

        search_row = QHBoxLayout()
        for widget in (self.sessions, self.query, self.kind, self.search_button):
            search_row.addWidget(widget)
        page_row = QHBoxLayout()
        page_row.addWidget(self.previous_button)
        page_row.addWidget(self.next_button)
        page_row.addWidget(self.status)
        page_row.addStretch()
        decision_row = QHBoxLayout()
        decision_row.addWidget(QLabel("Selected item:"))
        decision_row.addWidget(self.decision)
        decision_row.addWidget(self.note)
        decision_row.addWidget(self.apply_button)
        layout = QVBoxLayout()
        layout.addLayout(search_row)
        layout.addWidget(self.table)
        layout.addLayout(page_row)
        layout.addLayout(decision_row)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self._build_menus()
        self.search_button.clicked.connect(self._new_search)
        self.query.returnPressed.connect(self._new_search)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.previous_button.clicked.connect(self._previous)
        self.next_button.clicked.connect(self._next)
        self.apply_button.clicked.connect(self._record_decision)
        self.sessions.currentIndexChanged.connect(self._new_search)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.decision.currentTextChanged.connect(self._sync_decision_action)
        self._sync_decision_action(self.decision.currentText())
        self._load()

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.session_info_action = QAction("Inventory && Session &Info…", self)
        self.session_info_action.triggered.connect(self._show_session_info)
        file_menu.addAction(self.session_info_action)
        file_menu.addSeparator()
        self.close_action = QAction("&Close Window", self)
        self.close_action.setShortcut("Ctrl+W")
        self.close_action.triggered.connect(self.close)
        file_menu.addAction(self.close_action)

        view_menu = self.menuBar().addMenu("&View")
        self.refresh_action = QAction("&Refresh Results", self)
        self.refresh_action.setShortcut("F5")
        self.refresh_action.triggered.connect(self._load)
        view_menu.addAction(self.refresh_action)
        self.focus_search_action = QAction("Focus &Search", self)
        self.focus_search_action.setShortcut("Ctrl+F")
        self.focus_search_action.triggered.connect(self.query.setFocus)
        view_menu.addAction(self.focus_search_action)
        view_menu.addSeparator()
        filter_group = QActionGroup(self)
        filter_group.setExclusive(True)
        self.show_all_action = QAction("Show &All", self, checkable=True)
        self.files_only_action = QAction("&Files Only", self, checkable=True)
        self.directories_only_action = QAction("&Directories Only", self, checkable=True)
        for action in (
            self.show_all_action, self.files_only_action, self.directories_only_action
        ):
            filter_group.addAction(action)
            view_menu.addAction(action)
        self.show_all_action.setChecked(True)
        self.show_all_action.triggered.connect(lambda: self._set_kind(None))
        self.files_only_action.triggered.connect(lambda: self._set_kind("file"))
        self.directories_only_action.triggered.connect(lambda: self._set_kind("directory"))
        view_menu.addSeparator()
        self.previous_action = QAction("&Previous Page", self)
        self.previous_action.setShortcut("Alt+Left")
        self.previous_action.triggered.connect(self._previous)
        view_menu.addAction(self.previous_action)
        self.next_action = QAction("&Next Page", self)
        self.next_action.setShortcut("Alt+Right")
        self.next_action.triggered.connect(self._next)
        view_menu.addAction(self.next_action)

        decisions_menu = self.menuBar().addMenu("&Decisions")
        self.record_decision_action = QAction("&Record Selected Decision", self)
        self.record_decision_action.setShortcut("Ctrl+Return")
        self.record_decision_action.setEnabled(False)
        self.record_decision_action.triggered.connect(self._record_decision)
        decisions_menu.addAction(self.record_decision_action)
        self.decision_history_action = QAction("Decision &History…", self)
        self.decision_history_action.setEnabled(False)
        self.decision_history_action.triggered.connect(self._show_decision_history)
        decisions_menu.addAction(self.decision_history_action)
        self.clear_note_action = QAction("Clear Decision &Note", self)
        self.clear_note_action.triggered.connect(self.note.clear)
        decisions_menu.addAction(self.clear_note_action)
        decisions_menu.addSeparator()
        decision_values_menu = decisions_menu.addMenu("Set Decision &Value")
        decision_group = QActionGroup(self)
        decision_group.setExclusive(True)
        self.decision_value_actions: dict[str, QAction] = {}
        for decision in DECISIONS:
            action = QAction(decision.replace("_", " ").title(), self, checkable=True)
            action.triggered.connect(
                lambda checked=False, value=decision: self._choose_decision(value, checked)
            )
            decision_group.addAction(action)
            decision_values_menu.addAction(action)
            self.decision_value_actions[decision] = action

        help_menu = self.menuBar().addMenu("&Help")
        self.safety_action = QAction("Viewer &Safety Boundaries…", self)
        self.safety_action.triggered.connect(self._show_safety_boundaries)
        help_menu.addAction(self.safety_action)
        self.about_action = QAction("&About Rootwise…", self)
        self.about_action.triggered.connect(self._show_about)
        help_menu.addAction(self.about_action)

    def _session_id(self) -> str:
        return str(self.sessions.currentData())

    def _new_search(self, *_: object) -> None:
        self.offset = 0
        self._load()

    def _kind_changed(self, *_: object) -> None:
        current = self.kind.currentData()
        self.show_all_action.setChecked(current is None)
        self.files_only_action.setChecked(current == "file")
        self.directories_only_action.setChecked(current == "directory")
        self._new_search()

    def _set_kind(self, kind: str | None) -> None:
        index = self.kind.findData(kind)
        if index < 0:
            raise ValueError("unknown inventory kind filter")
        if index == self.kind.currentIndex():
            self._new_search()
        else:
            self.kind.setCurrentIndex(index)

    def _load(self, *_: object) -> None:
        try:
            items = self.reader.search(
                self._session_id(),
                self.query.text(),
                kind=self.kind.currentData(),
                limit=PAGE_SIZE,
                offset=self.offset,
            )
            decisions = self.decisions.current_for_paths(
                self._session_id(), [item.relative_path for item in items]
            )
            self.model.replace(items, decisions)
            first_row = self.offset + 1 if items else 0
            self.status.setText(f"Rows {first_row}–{self.offset + len(items)}")
            previous_enabled = self.offset > 0
            next_enabled = len(items) == PAGE_SIZE
            self.previous_button.setEnabled(previous_enabled)
            self.next_button.setEnabled(next_enabled)
            self.previous_action.setEnabled(previous_enabled)
            self.next_action.setEnabled(next_enabled)
        except Exception as exc:
            QMessageBox.critical(self, "Search failed", str(exc))

    def _previous(self, *_: object) -> None:
        self.offset = max(0, self.offset - PAGE_SIZE)
        self._load()

    def _next(self, *_: object) -> None:
        self.offset += PAGE_SIZE
        self._load()

    def _selection_changed(self, *_: object) -> None:
        selected = self.table.selectionModel().selectedRows()
        has_selection = bool(selected)
        self.apply_button.setEnabled(has_selection)
        self.record_decision_action.setEnabled(has_selection)
        self.decision_history_action.setEnabled(has_selection)
        if not selected:
            self.decision.setCurrentText("UNKNOWN")
            self.note.clear()
            return
        item = self.model.items[selected[0].row()]
        current = self.model.decisions.get(item.relative_path)
        if current is None:
            self.decision.setCurrentText("UNKNOWN")
            self.note.clear()
        else:
            self.decision.setCurrentText(current.decision)
            self.note.setText(current.note)

    def _sync_decision_action(self, decision: str) -> None:
        action = self.decision_value_actions.get(decision)
        if action is not None:
            action.setChecked(True)

    def _choose_decision(self, decision: str, checked: bool) -> None:
        if checked:
            self.decision.setCurrentText(decision)

    def _record_decision(self, *_: object) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "No selection", "Select one inventory row first.")
            return
        item = self.model.items[selected[0].row()]
        try:
            current = self.decisions.current(self._session_id(), item.relative_path)
            record = self.decisions.set_decision(
                self._session_id(),
                item.relative_path,
                self.decision.currentText(),
                note=self.note.text(),
                expected_revision=None if current is None else current.revision,
            )
            self.model.update_decision(record)
            self.status.setText(
                f"Recorded {record.decision} revision {record.revision} for {record.relative_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Decision failed", str(exc))

    def _show_decision_history(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "No selection", "Select one inventory row first.")
            return
        item = self.model.items[selected[0].row()]
        history = self.decisions.history(self._session_id(), item.relative_path)
        if history:
            entries = [
                f"Revision {record.revision} · {record.recorded_at} · {record.decision}\n"
                f"{record.note or '(no note)'}"
                for record in reversed(history)
            ]
            body = "\n\n".join(entries)
        else:
            body = "No decision has been recorded for this item."
        QMessageBox.information(self, f"Decision History — {item.relative_path}", body)

    def _show_session_info(self) -> None:
        session = next(
            item for item in self.reader.sessions() if item.scan_session_id == self._session_id()
        )
        QMessageBox.information(
            self,
            "Inventory and Session Information",
            f"Inventory: {self.reader.path}\n"
            f"Decision database: {self.decisions.path}\n"
            f"Session: {session.scan_session_id}\n"
            f"State: {session.state}\n"
            f"Observations: {session.observed_count}\n"
            f"Errors: {session.error_count}\n"
            f"Inventory query-only: {self.reader.query_only}",
        )

    def _show_safety_boundaries(self) -> None:
        QMessageBox.information(
            self,
            "Viewer Safety Boundaries",
            "The inventory database is opened query-only. Decisions are stored in a separate "
            "revisioned database. This viewer does not open observed paths or provide archive, "
            "move, rename, copy, link, delete, or execution actions.",
        )

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Rootwise",
            f"Rootwise {__version__}\nRead-only inventory review and revisioned decisions.",
        )


def run_gui(
    inventory_path: str | Path,
    decision_path: str | Path,
    *,
    session_id: str | None = None,
) -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    with InventoryReader(inventory_path) as reader, DecisionStore(
        decision_path, inventory_path=inventory_path
    ) as decisions:
        window = ViewerWindow(reader, decisions, session_id=session_id)
        window.show()
        return int(application.exec())
