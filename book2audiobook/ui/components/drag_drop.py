"""Drag-and-drop file zone widget."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout

from book2audiobook.ui.theme import RADII, SPACING

ACCEPTED_EXTENSIONS = {".epub", ".pdf", ".txt"}


class DragDropZone(QFrame):
    """A zone that accepts file drops or click-to-browse."""

    file_selected = Signal(str)  # emits file path string

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMinimumHeight(120)
        self.setStyleSheet(f"""
            DragDropZone {{
                border: 2px dashed palette(mid);
                border-radius: {RADII['lg']}px;
                background: transparent;
            }}
            DragDropZone[dragOver="true"] {{
                border-color: palette(highlight);
                background: rgba(79, 110, 247, 0.06);
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(SPACING["sm"])

        icon_label = QLabel("📁")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 32px; background: transparent; border: none;")

        text_label = QLabel("Drop a book here or click to browse")
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setProperty("cssClass", "muted")
        text_label.setStyleSheet("background: transparent; border: none;")

        hint_label = QLabel("Supports: EPUB, PDF, TXT")
        hint_label.setAlignment(Qt.AlignCenter)
        hint_label.setProperty("cssClass", "muted")
        hint_label.setStyleSheet("font-size: 11px; background: transparent; border: none;")

        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        layout.addWidget(hint_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Book", str(Path.home()),
                "Books (*.epub *.pdf *.txt)",
            )
            if path:
                self.file_selected.emit(path)
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in ACCEPTED_EXTENSIONS:
                    event.acceptProposedAction()
                    self.setProperty("dragOver", True)
                    self.style().unpolish(self)
                    self.style().polish(self)
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in ACCEPTED_EXTENSIONS:
                self.file_selected.emit(str(path))
                event.acceptProposedAction()
                return
        event.ignore()
