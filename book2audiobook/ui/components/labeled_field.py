"""Consistent label-above-widget layout."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from book2audiobook.ui.theme import SPACING


class LabeledField(QWidget):
    """A label positioned above a widget, with consistent spacing."""

    def __init__(self, label: str, widget: QWidget, parent=None):
        super().__init__(parent)
        self._widget = widget

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel(label)
        lbl.setProperty("cssClass", "fieldLabel")
        layout.addWidget(lbl)
        layout.addWidget(widget)

    @property
    def widget(self) -> QWidget:
        return self._widget
