"""Sidebar navigation widget."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from book2audiobook.ui.theme import SIDEBAR_WIDTH, SPACING


@dataclass
class SidebarItem:
    icon: str       # Unicode char or emoji
    label: str
    key: str        # unique identifier


class _NavButton(QPushButton):
    """Individual sidebar navigation button."""

    def __init__(self, item: SidebarItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setCheckable(True)
        self.setMinimumHeight(42)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(12)

        icon_label = QLabel(item.icon)
        icon_label.setFixedWidth(22)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 16px; background: transparent;")
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        text_label = QLabel(item.label)
        text_label.setStyleSheet("font-size: 13px; font-weight: 500; background: transparent;")
        text_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        layout.addStretch()

    def _update_style(self, selected: bool):
        if selected:
            self.setStyleSheet("""
                QPushButton {
                    background-color: rgba(79, 110, 247, 0.12);
                    border: none;
                    border-radius: 8px;
                    text-align: left;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 8px;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.06);
                }
            """)


class SidebarNav(QFrame):
    """Vertical sidebar with icon + label navigation items."""

    page_changed = Signal(str)  # emits item key

    DEFAULT_ITEMS: List[SidebarItem] = [
        SidebarItem("🔄", "Convert", "convert"),
        SidebarItem("🎙️", "Voices", "voices"),
        SidebarItem("📋", "Logs", "logs"),
        SidebarItem("ℹ️", "About", "about"),
    ]

    def __init__(self, items: List[SidebarItem] | None = None, parent=None):
        super().__init__(parent)
        self.setProperty("cssClass", "sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._items = items or self.DEFAULT_ITEMS
        self._buttons: list[_NavButton] = []
        self._selected_key: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["sm"], SPACING["lg"], SPACING["sm"], SPACING["lg"])
        layout.setSpacing(4)

        # App branding
        brand = QLabel("📖  Book2Audiobook")
        brand.setProperty("cssClass", "subtitle")
        brand.setStyleSheet("font-size: 14px; font-weight: 700; padding: 12px 12px 20px 12px; background: transparent;")
        layout.addWidget(brand)

        # Nav buttons
        for item in self._items:
            btn = _NavButton(item)
            btn.clicked.connect(lambda checked, k=item.key: self._on_click(k))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch(1)

        # Version at bottom
        version = QLabel("v0.1.0")
        version.setProperty("cssClass", "muted")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("padding: 8px; background: transparent;")
        layout.addWidget(version)

        # Select first
        if self._items:
            self.select(self._items[0].key)

    def select(self, key: str) -> None:
        self._selected_key = key
        for btn in self._buttons:
            is_sel = btn.item.key == key
            btn.setChecked(is_sel)
            btn._update_style(is_sel)

    def _on_click(self, key: str) -> None:
        self.select(key)
        self.page_changed.emit(key)
