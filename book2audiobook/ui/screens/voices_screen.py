"""Voices screen — browse and preview available voices."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from book2audiobook.ui.components.buttons import SecondaryButton, IconButton
from book2audiobook.ui.components.card import Card
from book2audiobook.ui.state import StateManager
from book2audiobook.ui.theme import SPACING

logger = logging.getLogger(__name__)


class VoicesScreen(QWidget):
    """Searchable voice browser with backend filtering."""

    voice_selected = Signal(str)  # voice id

    def __init__(self, state: StateManager, parent=None):
        super().__init__(parent)
        self._state = state
        self._all_voices: dict[str, list[str]] = {}  # backend -> voices

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QLabel("🎙️  Voices")
        header.setProperty("cssClass", "title")
        layout.addWidget(header)

        # Search + filter row
        top_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search voices…")
        self.search_edit.textChanged.connect(self._filter_voices)
        top_row.addWidget(self.search_edit, 1)

        self.backend_filter = QComboBox()
        self.backend_filter.addItem("All Backends", "all")
        self.backend_filter.addItem("Kokoro", "kokoro")
        self.backend_filter.addItem("OpenAI", "openai")
        self.backend_filter.addItem("OpenRouter", "openrouter")
        self.backend_filter.currentIndexChanged.connect(lambda _: self._filter_voices())
        top_row.addWidget(self.backend_filter)

        layout.addLayout(top_row)

        # Voice list
        card = Card()
        self.voice_list = QListWidget()
        self.voice_list.setAlternatingRowColors(True)
        self.voice_list.setStyleSheet("QListWidget { min-height: 300px; }")
        self.voice_list.itemClicked.connect(
            lambda item: self.voice_selected.emit(item.text())
        )
        card.add_widget(self.voice_list)

        # Info row
        self._info_label = QLabel("Load voices by configuring a backend on the Convert screen.")
        self._info_label.setProperty("cssClass", "muted")
        self._info_label.setStyleSheet("background: transparent;")
        card.add_widget(self._info_label)

        layout.addWidget(card)
        layout.addStretch()

    def set_voices(self, backend: str, voices: list[str]) -> None:
        """Called by controller when voices are loaded for a backend."""
        self._all_voices[backend] = voices
        self._filter_voices()

    def _filter_voices(self) -> None:
        search = self.search_edit.text().strip().lower()
        backend_filter = self.backend_filter.currentData()

        self.voice_list.clear()
        for backend, voices in self._all_voices.items():
            if backend_filter != "all" and backend != backend_filter:
                continue
            for v in voices:
                if search and search not in v.lower():
                    continue
                item = QListWidgetItem(f"{v}  ({backend})")
                item.setData(Qt.UserRole, v)
                self.voice_list.addItem(item)

        count = self.voice_list.count()
        self._info_label.setText(f"{count} voice{'s' if count != 1 else ''} available")
