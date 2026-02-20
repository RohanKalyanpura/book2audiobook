"""Toast notification overlay widget."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect

from book2audiobook.ui.theme import RADII, SPACING


class _Toast(QFrame):
    """A single toast message."""

    def __init__(self, message: str, level: str = "info", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(48)
        self.setMinimumWidth(300)
        self.setMaximumWidth(500)

        colors = {
            "info": ("#0DCAF0", "#1A1D26"),
            "success": ("#2BA84A", "#FFFFFF"),
            "warning": ("#E5A100", "#1A1D26"),
            "error": ("#DC3545", "#FFFFFF"),
        }
        bg, fg = colors.get(level, colors["info"])

        self.setStyleSheet(f"""
            _Toast {{
                background-color: {bg};
                border-radius: {RADII['sm']}px;
                color: {fg};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["md"], 0, SPACING["sm"], 0)

        label = QLabel(message)
        label.setStyleSheet(f"color: {fg}; font-weight: 500; font-size: 13px; background: transparent;")
        layout.addWidget(label, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {fg};
                border: none;
                font-size: 14px;
            }}
        """)
        close_btn.clicked.connect(self._fade_out)
        layout.addWidget(close_btn)

        # Opacity effect for fade
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

    def show_animated(self, duration_ms: int = 3000) -> None:
        self.show()
        # Fade in
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

        QTimer.singleShot(duration_ms, self._fade_out)

    def _fade_out(self) -> None:
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(300)
        anim.setStartValue(self._opacity.opacity())
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.finished.connect(self.deleteLater)
        anim.start(QPropertyAnimation.DeleteWhenStopped)


class ToastManager:
    """Manages toast notifications positioned relative to a parent widget."""

    def __init__(self, parent_widget):
        self._parent = parent_widget
        self._active: list[_Toast] = []

    def show(self, message: str, level: str = "info", duration_ms: int = 3000) -> None:
        toast = _Toast(message, level, self._parent)
        toast.adjustSize()

        # Position top-right corner of parent
        parent_rect = self._parent.rect()
        x = self._parent.mapToGlobal(parent_rect.topRight()).x() - toast.width() - 20
        y = self._parent.mapToGlobal(parent_rect.topRight()).y() + 70 + len(self._active) * 56

        toast.move(x, y)
        toast.show_animated(duration_ms)

        self._active.append(toast)
        toast.destroyed.connect(lambda: self._active.remove(toast) if toast in self._active else None)
