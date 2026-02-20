"""About screen — app info and links."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from book2audiobook.ui.components.card import Card
from book2audiobook.ui.theme import SPACING


class AboutScreen(QWidget):
    """Simple about/information screen."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QLabel("ℹ️  About")
        header.setProperty("cssClass", "title")
        layout.addWidget(header)

        card = Card()

        name = QLabel("📖  Book2Audiobook")
        name.setStyleSheet("font-size: 24px; font-weight: 700; background: transparent;")
        card.add_widget(name)

        version = QLabel("Version 0.1.0")
        version.setProperty("cssClass", "subtitle")
        version.setStyleSheet("background: transparent;")
        card.add_widget(version)

        desc = QLabel(
            "Convert DRM-free books (EPUB, PDF, TXT) into high-quality audiobooks "
            "using AI text-to-speech.\n\n"
            "Supports multiple TTS backends:\n"
            "  • Kokoro — high-quality local TTS (no internet required)\n"
            "  • OpenAI — cloud-based TTS via OpenAI API\n"
            "  • OpenRouter — access multiple TTS models via OpenRouter\n\n"
            "Built with PySide6 (Qt for Python)."
        )
        desc.setWordWrap(True)
        desc.setProperty("cssClass", "muted")
        desc.setStyleSheet("font-size: 13px; line-height: 1.6; background: transparent;")
        card.add_widget(desc)

        disclaimer = QLabel("⚠️  Only convert content you have rights to.")
        disclaimer.setStyleSheet("color: #E5A100; font-size: 12px; font-weight: 500; background: transparent;")
        card.add_widget(disclaimer)

        layout.addWidget(card)
        layout.addStretch()
