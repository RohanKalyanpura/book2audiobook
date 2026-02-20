from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from book2audiobook.backends.openai_backend import clear_openai_api_key, save_openai_api_key
from book2audiobook.backends.openrouter_backend import clear_openrouter_api_key, save_openrouter_api_key


class LogConsole(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)

    def append_line(self, line: str) -> None:
        self.append(line)


class ProviderApiKeysDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Provider API Keys")
        self._openai_edit = QLineEdit()
        self._openrouter_edit = QLineEdit()
        self._openai_edit.setEchoMode(QLineEdit.Password)
        self._openrouter_edit.setEchoMode(QLineEdit.Password)

        openai_box = QGroupBox("OpenAI")
        openai_form = QFormLayout(openai_box)
        openai_form.addRow("API Key", self._openai_edit)
        clear_openai_btn = QPushButton("Clear OpenAI Key")
        clear_openai_btn.clicked.connect(self._clear_openai)
        openai_form.addRow(clear_openai_btn)

        openrouter_box = QGroupBox("OpenRouter")
        openrouter_form = QFormLayout(openrouter_box)
        openrouter_form.addRow("API Key", self._openrouter_edit)
        clear_openrouter_btn = QPushButton("Clear OpenRouter Key")
        clear_openrouter_btn.clicked.connect(self._clear_openrouter)
        openrouter_form.addRow(clear_openrouter_btn)

        note = QLabel(
            "Environment variables take precedence: OPENAI_API_KEY and OPENROUTER_API_KEY."
        )
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(openai_box)
        layout.addWidget(openrouter_box)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _save(self) -> None:
        openai_key = self._openai_edit.text().strip()
        openrouter_key = self._openrouter_edit.text().strip()
        if not openai_key and not openrouter_key:
            QMessageBox.warning(self, "Invalid keys", "Enter at least one key to save.")
            return
        if openai_key:
            save_openai_api_key(openai_key)
        if openrouter_key:
            save_openrouter_api_key(openrouter_key)
        self.accept()

    def _clear_openai(self) -> None:
        clear_openai_api_key()
        QMessageBox.information(self, "Cleared", "Saved OpenAI key removed.")

    def _clear_openrouter(self) -> None:
        clear_openrouter_api_key()
        QMessageBox.information(self, "Cleared", "Saved OpenRouter key removed.")


class FfmpegMissingDialog(QMessageBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ffmpeg Not Found")
        self.setIcon(QMessageBox.Warning)
        self.setText("ffmpeg/ffprobe are required.")
        self.setInformativeText(
            "macOS: brew install ffmpeg\n"
            "Windows: install FFmpeg and add bin folder to PATH.\n"
            "See README troubleshooting section for details."
        )


def add_copy_log_button(log_widget: QTextEdit, parent_layout: QVBoxLayout) -> QPushButton:
    row = QHBoxLayout()
    btn = QPushButton("Copy Log")

    def _copy() -> None:
        log_widget.selectAll()
        log_widget.copy()
        log_widget.moveCursor(log_widget.textCursor().End)

    btn.clicked.connect(_copy)
    row.addWidget(btn)
    row.addStretch(1)
    parent_layout.addLayout(row)
    return btn
