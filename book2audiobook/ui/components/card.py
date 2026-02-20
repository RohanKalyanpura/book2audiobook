"""Card container widget with rounded corners and optional shadow."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QVBoxLayout
from PySide6.QtGui import QColor

from book2audiobook.ui.theme import RADII, SPACING


class Card(QFrame):
    """A rounded card container with subtle shadow and optional title."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("cssClass", "card")
        self.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])

        # Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 20))
        self.setGraphicsEffect(shadow)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        self._layout.setSpacing(SPACING["md"])

        if title:
            title_label = QLabel(title)
            title_label.setProperty("cssClass", "sectionTitle")
            self._layout.addWidget(title_label)

    def add_widget(self, widget):
        self._layout.addWidget(widget)

    def add_layout(self, layout):
        self._layout.addLayout(layout)

    def add_stretch(self, factor: int = 1):
        self._layout.addStretch(factor)

    @property
    def card_layout(self) -> QVBoxLayout:
        return self._layout
