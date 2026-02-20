"""Logs screen — tail log view with utility buttons."""
from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from book2audiobook import app_data_dir
from book2audiobook.ui.components.buttons import SecondaryButton
from book2audiobook.ui.components.card import Card
from book2audiobook.ui.widgets import LogConsole
from book2audiobook.ui.theme import SPACING

logger = logging.getLogger(__name__)


class LogsScreen(QWidget):
    """Application log viewer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_dir = app_data_dir()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QLabel("📋  Logs")
        header.setProperty("cssClass", "title")
        layout.addWidget(header)

        # Info card
        info_card = Card()
        path_label = QLabel(f"Log directory: {self._log_dir}")
        path_label.setProperty("cssClass", "muted")
        path_label.setStyleSheet("background: transparent;")
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_card.add_widget(path_label)
        layout.addWidget(info_card)

        # Log console
        log_card = Card("Live Log")
        self.log_console = LogConsole()
        self.log_console.setMinimumHeight(300)
        log_card.add_widget(self.log_console)
        layout.addWidget(log_card)

        # Buttons
        btn_row = QHBoxLayout()
        copy_btn = SecondaryButton("📋  Copy All")
        copy_btn.clicked.connect(self._copy_all)

        copy_sel_btn = SecondaryButton("📑  Copy Selected")
        copy_sel_btn.clicked.connect(self._copy_selected)

        open_btn = SecondaryButton("📂  Open Folder")
        open_btn.clicked.connect(self._open_folder)

        clear_btn = SecondaryButton("🗑  Clear")
        clear_btn.clicked.connect(self.log_console.clear)

        btn_row.addWidget(copy_btn)
        btn_row.addWidget(copy_sel_btn)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()

    def _copy_all(self):
        text = self.log_console.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def _copy_selected(self):
        cursor = self.log_console.textCursor()
        text = cursor.selectedText()
        if text:
            QApplication.clipboard().setText(text)

    def _open_folder(self):
        path = str(self._log_dir)
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            elif platform.system() == "Windows":
                subprocess.Popen(["explorer", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            logger.warning("Failed to open folder: %s", exc)
