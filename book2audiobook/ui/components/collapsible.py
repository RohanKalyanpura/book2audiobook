"""Collapsible section with animated expand/collapse."""
from __future__ import annotations

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PySide6.QtWidgets import (
    QFrame, QPushButton, QVBoxLayout, QWidget, QSizePolicy,
)
from PySide6.QtGui import QCursor


class CollapsibleSection(QWidget):
    """A section with a clickable header that shows/hides content with animation."""

    def __init__(self, title: str = "Advanced", parent=None, initially_open: bool = False):
        super().__init__(parent)
        self._is_open = initially_open

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Toggle button
        self._toggle_btn = QPushButton(f"{'▼' if initially_open else '▶'}  {title}")
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                text-align: left;
                padding: 8px 4px;
                font-weight: 600;
                font-size: 12px;
                color: palette(text);
            }
            QPushButton:hover {
                color: palette(highlight);
            }
        """)
        self._toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._toggle_btn.clicked.connect(self.toggle)
        outer.addWidget(self._toggle_btn)

        # Content area
        self._content = QFrame()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 4, 0, 4)
        self._content_layout.setSpacing(8)
        outer.addWidget(self._content)

        self._title = title
        if not initially_open:
            self._content.setMaximumHeight(0)
            self._content.setVisible(False)

    def add_widget(self, widget: QWidget) -> None:
        self._content_layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._content_layout.addLayout(layout)

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def toggle(self) -> None:
        self._is_open = not self._is_open
        arrow = "▼" if self._is_open else "▶"
        self._toggle_btn.setText(f"{arrow}  {self._title}")

        if self._is_open:
            self._content.setVisible(True)
            self._content.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        else:
            self._content.setMaximumHeight(0)
            self._content.setVisible(False)

    def is_open(self) -> bool:
        return self._is_open
