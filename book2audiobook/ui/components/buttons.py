"""Styled button components."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QPushButton


class PrimaryButton(QPushButton):
    """Accent-colored call-to-action button."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setProperty("cssClass", "primary")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMinimumHeight(40)


class SecondaryButton(QPushButton):
    """Outlined / neutral button."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMinimumHeight(36)


class IconButton(QPushButton):
    """Square icon-only button with tooltip."""

    def __init__(self, icon_char: str = "", tooltip: str = "", parent=None):
        super().__init__(icon_char, parent)
        self.setToolTip(tooltip)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedSize(QSize(36, 36))
        self.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                padding: 0;
                border-radius: 8px;
            }
        """)


class DangerButton(QPushButton):
    """Red danger/stop button."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setProperty("cssClass", "danger")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMinimumHeight(40)
