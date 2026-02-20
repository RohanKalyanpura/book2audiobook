"""Top header bar widget."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QWidget,
)

from book2audiobook.ui.components.buttons import PrimaryButton, IconButton
from book2audiobook.ui.theme import HEADER_HEIGHT, SPACING


class HeaderBar(QFrame):
    """Horizontal header bar with app controls."""

    open_book_clicked = Signal()
    backend_changed = Signal(str)      # emits backend value
    theme_toggle_clicked = Signal()
    settings_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("cssClass", "header")
        self.setFixedHeight(HEADER_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], 0, SPACING["lg"], 0)
        layout.setSpacing(SPACING["md"])

        # Open Book button
        self.open_btn = PrimaryButton("📂  Open Book")
        self.open_btn.setMinimumWidth(140)
        self.open_btn.clicked.connect(self.open_book_clicked.emit)

        # Backend selector
        backend_label = QLabel("Backend:")
        backend_label.setProperty("cssClass", "fieldLabel")
        backend_label.setStyleSheet("background: transparent; font-size: 12px;")

        self.backend_combo = QComboBox()
        self.backend_combo.setMinimumWidth(170)
        self.backend_combo.addItem("🏠  Kokoro (Local)", "kokoro")
        self.backend_combo.addItem("☁️  OpenAI", "openai")
        self.backend_combo.addItem("🌐  OpenRouter", "openrouter")
        self.backend_combo.currentIndexChanged.connect(
            lambda _: self.backend_changed.emit(self.backend_combo.currentData())
        )

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy())
        spacer.setStyleSheet("background: transparent;")

        # Theme toggle
        self.theme_btn = IconButton("🌓", "Toggle theme (Light / Dark / System)")
        self.theme_btn.clicked.connect(self.theme_toggle_clicked.emit)

        # Settings
        self.settings_btn = IconButton("⚙️", "Preferences (⌘,)")
        self.settings_btn.clicked.connect(self.settings_clicked.emit)

        layout.addWidget(self.open_btn)
        layout.addSpacing(SPACING["lg"])
        layout.addWidget(backend_label)
        layout.addWidget(self.backend_combo)
        layout.addStretch(1)
        layout.addWidget(self.theme_btn)
        layout.addWidget(self.settings_btn)

    def current_backend(self) -> str:
        return self.backend_combo.currentData()
