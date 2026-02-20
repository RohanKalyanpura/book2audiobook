"""Pipeline step indicator widget."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy

from book2audiobook.ui.theme import SPACING


PIPELINE_STEPS = ["Parsing", "Chunking", "TTS", "Assembly", "Encoding"]


class _StepDot(QWidget):
    """A single step dot + label."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label_text = label
        self._state = "pending"  # pending | active | done

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = QLabel("○")
        self._dot.setFixedWidth(18)
        self._dot.setAlignment(Qt.AlignCenter)
        self._dot.setStyleSheet("font-size: 14px; background: transparent;")

        self._text = QLabel(label)
        self._text.setProperty("cssClass", "muted")
        self._text.setStyleSheet("font-size: 12px; background: transparent;")

        layout.addWidget(self._dot)
        layout.addWidget(self._text)

    def set_state(self, state: str) -> None:
        self._state = state
        if state == "done":
            self._dot.setText("✓")
            self._dot.setStyleSheet("font-size: 14px; color: #2BA84A; font-weight: bold; background: transparent;")
            self._text.setStyleSheet("font-size: 12px; color: #2BA84A; font-weight: 500; background: transparent;")
        elif state == "active":
            self._dot.setText("●")
            self._dot.setStyleSheet("font-size: 14px; color: #4F6EF7; background: transparent;")
            self._text.setStyleSheet("font-size: 12px; color: #4F6EF7; font-weight: 600; background: transparent;")
        else:
            self._dot.setText("○")
            self._dot.setStyleSheet("font-size: 14px; color: #8B8FA3; background: transparent;")
            self._text.setStyleSheet("font-size: 12px; color: #8B8FA3; background: transparent;")


class StepIndicator(QWidget):
    """Horizontal step indicator showing pipeline stages."""

    def __init__(self, steps: list[str] | None = None, parent=None):
        super().__init__(parent)
        self._steps_labels = steps or PIPELINE_STEPS
        self._dots: list[_StepDot] = []
        self._current_index = -1

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, SPACING["sm"], 0, SPACING["sm"])
        layout.setSpacing(SPACING["lg"])

        for label in self._steps_labels:
            dot = _StepDot(label)
            self._dots.append(dot)
            layout.addWidget(dot)

        layout.addStretch(1)

    def set_step(self, index: int) -> None:
        """Mark step at index as active; all prior steps as done."""
        self._current_index = index
        for i, dot in enumerate(self._dots):
            if i < index:
                dot.set_state("done")
            elif i == index:
                dot.set_state("active")
            else:
                dot.set_state("pending")

    def reset(self) -> None:
        self._current_index = -1
        for dot in self._dots:
            dot.set_state("pending")

    def set_all_done(self) -> None:
        for dot in self._dots:
            dot.set_state("done")
