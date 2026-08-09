"""Minimal bounded PySide6 interface over the tested viewer backends."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
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

from .decisions import DECISIONS, DecisionStore
from .inventory import InventoryItem, InventoryReader

PAGE_SIZE = 200


class InventoryTableModel(QAbstractTableModel):
    headers = ("Type", "Name", "Path", "Extension", "Bytes", "Status")

    def __init__(self) -> None:
        super().__init__()
        self.items: list[InventoryItem] = []

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
        if not index.isValid() or role != int(Qt.ItemDataRole.DisplayRole):
            return None
        item = self.items[index.row()]
        values = (
            item.kind,
            item.name,
            item.relative_path,
            item.extension,
            str(item.logical_bytes),
            item.observation_status,
        )
        return values[index.column()]

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = int(Qt.ItemDataRole.DisplayRole)
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == int(Qt.ItemDataRole.DisplayRole):
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def replace(self, items: list[InventoryItem]) -> None:
        self.beginResetModel()
        self.items = items
        self.endResetModel()


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
        self.setWindowTitle("ParetoDrive 0.3 — Read-only Inventory")
        self.resize(1100, 700)

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
        self.note = QLineEdit()
        self.note.setPlaceholderText("Decision note (optional)")
        self.apply_button = QPushButton("Record decision")

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

        self.search_button.clicked.connect(self._new_search)
        self.query.returnPressed.connect(self._new_search)
        self.previous_button.clicked.connect(self._previous)
        self.next_button.clicked.connect(self._next)
        self.apply_button.clicked.connect(self._record_decision)
        self.sessions.currentIndexChanged.connect(self._new_search)
        self._load()

    def _session_id(self) -> str:
        return str(self.sessions.currentData())

    def _new_search(self, *_: object) -> None:
        self.offset = 0
        self._load()

    def _load(self) -> None:
        try:
            items = self.reader.search(
                self._session_id(),
                self.query.text(),
                kind=self.kind.currentData(),
                limit=PAGE_SIZE,
                offset=self.offset,
            )
            self.model.replace(items)
            self.status.setText(f"Rows {self.offset + 1}–{self.offset + len(items)}")
            self.previous_button.setEnabled(self.offset > 0)
            self.next_button.setEnabled(len(items) == PAGE_SIZE)
        except Exception as exc:
            QMessageBox.critical(self, "Search failed", str(exc))

    def _previous(self) -> None:
        self.offset = max(0, self.offset - PAGE_SIZE)
        self._load()

    def _next(self) -> None:
        self.offset += PAGE_SIZE
        self._load()

    def _record_decision(self) -> None:
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
            self.status.setText(
                f"Recorded {record.decision} revision {record.revision} for {record.relative_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Decision failed", str(exc))


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
