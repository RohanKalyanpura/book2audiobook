"""Preferences dialog — tabbed settings UI."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from book2audiobook.ui.components.buttons import SecondaryButton
from book2audiobook.ui.theme import RADII, SPACING


class PreferencesDialog(QDialog):
    """Tabbed preferences dialog."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(560, 480)
        self._config = config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_backends_tab(), "Backends")
        tabs.addTab(self._build_audio_tab(), "Audio")
        tabs.addTab(self._build_advanced_tab(), "Advanced")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_general_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(SPACING["md"])

        # Default output dir
        dir_row = QHBoxLayout()
        self.default_output_edit = QLineEdit(str(Path.home()))
        browse_btn = SecondaryButton("Browse…")
        browse_btn.clicked.connect(self._browse_default_output)
        dir_row.addWidget(self.default_output_edit, 1)
        dir_row.addWidget(browse_btn)
        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)
        form.addRow("Default Output Folder", dir_widget)

        # Default format
        self.default_format_combo = QComboBox()
        self.default_format_combo.addItems(["M4B", "MP3", "WAV"])
        form.addRow("Default Format", self.default_format_combo)

        # Default bitrate
        self.default_bitrate_combo = QComboBox()
        for kbps in [48, 64, 96, 128, 192]:
            self.default_bitrate_combo.addItem(f"{kbps} kbps", kbps)
        self.default_bitrate_combo.setCurrentIndex(1)
        form.addRow("Default Quality", self.default_bitrate_combo)

        return page

    def _build_backends_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(SPACING["md"])

        # Kokoro section
        kokoro_header = QLabel("── Kokoro ──")
        kokoro_header.setProperty("cssClass", "fieldLabel")
        form.addRow(kokoro_header)

        self.kokoro_device_combo = QComboBox()
        self.kokoro_device_combo.addItems(["auto", "cpu", "mps", "cuda", "dml"])
        device_val = self._config.get("kokoro", {}).get("device", "auto")
        idx = self.kokoro_device_combo.findText(device_val)
        if idx >= 0:
            self.kokoro_device_combo.setCurrentIndex(idx)
        form.addRow("Device", self.kokoro_device_combo)

        self.kokoro_threads_edit = QLineEdit(
            str(self._config.get("kokoro", {}).get("cpu_threads", "auto"))
        )
        form.addRow("CPU Threads", self.kokoro_threads_edit)

        # OpenAI section
        openai_header = QLabel("── OpenAI ──")
        openai_header.setProperty("cssClass", "fieldLabel")
        form.addRow(openai_header)
        self.openai_key_edit = QLineEdit()
        self.openai_key_edit.setEchoMode(QLineEdit.Password)
        self.openai_key_edit.setPlaceholderText("Enter API key or set OPENAI_API_KEY env var")
        form.addRow("API Key", self.openai_key_edit)

        self.openai_model_edit = QLineEdit(
            self._config.get("openai", {}).get("model", "gpt-4o-mini-tts")
        )
        form.addRow("Model", self.openai_model_edit)

        # OpenRouter section
        or_header = QLabel("── OpenRouter ──")
        or_header.setProperty("cssClass", "fieldLabel")
        form.addRow(or_header)
        self.openrouter_key_edit = QLineEdit()
        self.openrouter_key_edit.setEchoMode(QLineEdit.Password)
        self.openrouter_key_edit.setPlaceholderText("Enter API key or set OPENROUTER_API_KEY env var")
        form.addRow("API Key", self.openrouter_key_edit)

        return page

    def _build_audio_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(SPACING["md"])

        # FFmpeg path
        ffmpeg_row = QHBoxLayout()
        self.ffmpeg_path_edit = QLineEdit()
        self.ffmpeg_path_edit.setPlaceholderText("Auto-detect")
        ffmpeg_browse = SecondaryButton("Browse…")
        ffmpeg_browse.clicked.connect(self._browse_ffmpeg)
        ffmpeg_row.addWidget(self.ffmpeg_path_edit, 1)
        ffmpeg_row.addWidget(ffmpeg_browse)
        ffmpeg_widget = QWidget()
        ffmpeg_widget.setLayout(ffmpeg_row)
        form.addRow("FFmpeg Path", ffmpeg_widget)

        # Default sample rate
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["22050", "24000", "44100", "48000"])
        self.sample_rate_combo.setCurrentIndex(1)
        form.addRow("Sample Rate", self.sample_rate_combo)

        return page

    def _build_advanced_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(SPACING["md"])

        # Chunk size
        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(500, 20000)
        self.chunk_size_spin.setValue(
            self._config.get("kokoro", {}).get("max_chars", 2200)
        )
        self.chunk_size_spin.setSuffix(" chars")
        form.addRow("Chunk Size", self.chunk_size_spin)

        # Retries
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 10)
        self.retries_spin.setValue(
            self._config.get("openai", {}).get("retries", 4)
        )
        form.addRow("Retries", self.retries_spin)

        # Log level
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level_combo.setCurrentIndex(1)
        form.addRow("Log Level", self.log_level_combo)

        return page

    def _browse_default_output(self):
        d = QFileDialog.getExistingDirectory(self, "Default Output Folder", str(Path.home()))
        if d:
            self.default_output_edit.setText(d)

    def _browse_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(self, "FFmpeg Binary")
        if path:
            self.ffmpeg_path_edit.setText(path)
