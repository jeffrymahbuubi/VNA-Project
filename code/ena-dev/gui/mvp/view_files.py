"""view_files.py — Screen 3 (History / Files), F-7.

Display-only list of saved run files (CSV / xlsx) under the data root, with
multi-select delete and zip-export. The presenter does the filesystem work; this
view only shows items and emits intents. Reached from the Setup TopBar "Files…"
button; returns via Back.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QAbstractItemView,
)

from . import theme as T


class FilesPage(QWidget):
    """Screen 3 — saved-run history."""

    backClicked = Signal()
    refreshClicked = Signal()
    deleteClicked = Signal()
    zipClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("filesPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.backButton = T.button_sm("←  Back", min_w=90)
        self.backButton.setObjectName("filesBackButton")
        self.backButton.clicked.connect(self.backClicked)
        self.topBar = T.TopBar("Saved Runs — History", right_widget=self.backButton)
        self.topBar.setObjectName("filesTopBar")
        root.addWidget(self.topBar)

        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(10)
        root.addWidget(body, 1)

        col.addWidget(T.section_header("Saved CSV / xlsx (multi-select)"))

        self.filesList = QListWidget()
        self.filesList.setObjectName("filesList")
        self.filesList.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.filesList.setStyleSheet(
            f"QListWidget{{background:{T.CLR['card']};border:1px solid {T.CLR['border']};"
            f"border-radius:8px;color:{T.CLR['t1']};padding:4px;}}"
            f"QListWidget::item:selected{{background:{T.CLR['accent_dim']};}}"
        )
        col.addWidget(self.filesList, 1)

        bar = QWidget(); bh = QHBoxLayout(bar)
        bh.setContentsMargins(0, 0, 0, 0); bh.setSpacing(10)
        self.refreshFilesButton = T.button_sm("Refresh", min_w=90)
        self.refreshFilesButton.setObjectName("refreshFilesButton")
        self.refreshFilesButton.clicked.connect(self.refreshClicked)
        self.zipFilesButton = T.button_sm("Zip selected…", min_w=120)
        self.zipFilesButton.setObjectName("zipFilesButton")
        self.zipFilesButton.clicked.connect(self.zipClicked)
        self.deleteFilesButton = T.button("Delete selected", T.CLR['red'], T.CLR['red_hover'], min_w=140)
        self.deleteFilesButton.setObjectName("deleteFilesButton")
        self.deleteFilesButton.clicked.connect(self.deleteClicked)
        bh.addWidget(self.refreshFilesButton)
        bh.addWidget(self.zipFilesButton)
        bh.addStretch()
        bh.addWidget(self.deleteFilesButton)
        col.addWidget(bar)

        self.filesStatusLabel = T.label("—", "small", color=T.CLR['t3'])
        self.filesStatusLabel.setObjectName("filesStatusLabel")
        col.addWidget(self.filesStatusLabel)

    # ── presenter helpers ───────────────────────────────────
    def set_files(self, paths):
        self.filesList.clear()
        for p in paths:
            pp = Path(p)
            try:
                size_kb = pp.stat().st_size / 1024.0
            except OSError:
                size_kb = 0.0
            item = QListWidgetItem(f"{pp.name}   ·   {pp.parent.name}/   ·   {size_kb:,.1f} KB")
            item.setData(Qt.ItemDataRole.UserRole, str(pp))
            self.filesList.addItem(item)
        self.filesStatusLabel.setText(f"{len(paths)} file(s).")

    def selected_files(self):
        return [it.data(Qt.ItemDataRole.UserRole) for it in self.filesList.selectedItems()]

    def set_status(self, text: str):
        self.filesStatusLabel.setText(text)
