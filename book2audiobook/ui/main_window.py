"""New MainWindow — three-panel layout with header, sidebar, and content area.

This replaces the legacy stacked-widget approach with a modern shell that
delegates all UI to dedicated screen widgets and all business logic to
the ConversionController.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from book2audiobook import BackendType, OutputFormat, app_data_dir
from book2audiobook.backends.kokoro_backend import normalize_voice_names
from book2audiobook.ui.components.header_bar import HeaderBar
from book2audiobook.ui.components.sidebar import SidebarNav
from book2audiobook.ui.components.toast import ToastManager
from book2audiobook.ui.controllers.conversion_controller import ConversionController
from book2audiobook.ui.models import ChapterTableModel
from book2audiobook.ui.preferences import PreferencesDialog
from book2audiobook.ui.screens.convert_screen import ConvertScreen
from book2audiobook.ui.screens.voices_screen import VoicesScreen
from book2audiobook.ui.screens.logs_screen import LogsScreen
from book2audiobook.ui.screens.about_screen import AboutScreen
from book2audiobook.ui.state import StateManager
from book2audiobook.ui.theme import ThemeManager, ThemeMode
from book2audiobook.ui.widgets import FfmpegMissingDialog, ProviderApiKeysDialog

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Modern three-panel main window."""

    def __init__(self, theme_manager: ThemeManager | None = None):
        super().__init__()
        self.setWindowTitle("Book2Audiobook")
        self.setMinimumSize(QSize(960, 640))
        self.resize(1200, 800)

        # Config
        self._config = self._load_config()

        # Theme
        self._theme_manager = theme_manager

        # State
        self._state = StateManager(self)

        # Controller
        self._controller = ConversionController(self._state, self._config, self)

        # Toast manager
        self._toast = ToastManager(self)

        # ─── Build layout ────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Sidebar
        self._sidebar = SidebarNav()
        root_layout.addWidget(self._sidebar)

        # Right side: header + content
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Header
        self._header = HeaderBar()
        right_layout.addWidget(self._header)

        # Content area (stacked screens)
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("QStackedWidget { background: transparent; }")

        self._convert_screen = ConvertScreen(self._state)
        self._voices_screen = VoicesScreen(self._state)
        self._logs_screen = LogsScreen()
        self._about_screen = AboutScreen()

        self._screen_map = {
            "convert": self._convert_screen,
            "voices": self._voices_screen,
            "logs": self._logs_screen,
            "about": self._about_screen,
        }

        for key in ["convert", "voices", "logs", "about"]:
            self._stack.addWidget(self._screen_map[key])

        right_layout.addWidget(self._stack, 1)
        root_layout.addWidget(right, 1)

        # ─── Connect signals ──────────────────────────────────
        self._connect_sidebar()
        self._connect_header()
        self._connect_convert_screen()
        self._connect_controller()
        self._setup_shortcuts()
        self._setup_menu_bar()

        # ─── Initialize ──────────────────────────────────────
        self._init_backend_widgets()

    # ===================================================================
    # Config
    # ===================================================================
    @staticmethod
    def _load_config() -> dict:
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS"))
            resources = base / "book2audiobook" / "resources" / "default_config.json"
        else:
            resources = Path(__file__).resolve().parents[1] / "resources" / "default_config.json"
        return json.loads(resources.read_text(encoding="utf-8"))

    # ===================================================================
    # Signal wiring
    # ===================================================================
    def _connect_sidebar(self):
        self._sidebar.page_changed.connect(self._on_page_changed)

    def _connect_header(self):
        self._header.open_book_clicked.connect(self._open_book)
        self._header.backend_changed.connect(self._on_backend_changed)
        self._header.theme_toggle_clicked.connect(self._toggle_theme)
        self._header.settings_clicked.connect(self._open_preferences)

    def _connect_convert_screen(self):
        cs = self._convert_screen
        cs.import_requested.connect(self._import_book)
        cs.convert_clicked.connect(self._start_conversion)
        cs.cancel_clicked.connect(self._cancel_conversion)

        # Chapter controls
        cs._up_btn.clicked.connect(lambda: self._move_chapter(-1))
        cs._down_btn.clicked.connect(lambda: self._move_chapter(1))
        cs._combine_btn.clicked.connect(self._combine_chapters)

        # Kokoro buttons
        cs.kokoro_browse_btn.clicked.connect(self._browse_kokoro_folder)
        cs.kokoro_default_btn.clicked.connect(self._use_default_kokoro_folder)
        cs.kokoro_load_voices_btn.clicked.connect(self._load_kokoro_voices)
        cs.kokoro_save_voices_btn.clicked.connect(self._save_kokoro_voices)

    def _connect_controller(self):
        ctrl = self._controller
        ctrl.import_success.connect(self._on_import_success)
        ctrl.import_error.connect(self._on_import_error)
        ctrl.log_line.connect(self._on_log_line)
        ctrl.conversion_finished.connect(self._on_conversion_finished)
        ctrl.conversion_error.connect(self._on_conversion_error)
        ctrl.conversion_canceled.connect(self._on_conversion_canceled)
        ctrl.voices_loaded.connect(self._on_voices_loaded)
        ctrl.ffmpeg_missing.connect(lambda: FfmpegMissingDialog(self).exec())
        ctrl.gpu_fallback_warning.connect(self._on_gpu_fallback)

    def _setup_shortcuts(self):
        # Cmd + O: Open Book
        QShortcut(QKeySequence("Ctrl+O"), self, self._open_book)
        # Cmd + , : Preferences
        QShortcut(QKeySequence("Ctrl+,"), self, self._open_preferences)

    def _setup_menu_bar(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("File")
        open_action = QAction("Open Book…", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_book)
        file_menu.addAction(open_action)

        api_action = QAction("Configure API Keys…", self)
        api_action.triggered.connect(lambda: ProviderApiKeysDialog(self).exec())
        file_menu.addAction(api_action)

        prefs_action = QAction("Preferences…", self)
        prefs_action.setShortcut(QKeySequence("Ctrl+,"))
        prefs_action.triggered.connect(self._open_preferences)
        file_menu.addAction(prefs_action)

    # ===================================================================
    # Navigation
    # ===================================================================
    def _on_page_changed(self, key: str):
        screen = self._screen_map.get(key)
        if screen:
            self._stack.setCurrentWidget(screen)

    # ===================================================================
    # Book import
    # ===================================================================
    def _open_book(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Book", str(Path.home()),
            "Books (*.epub *.pdf *.txt)",
        )
        if path:
            self._import_book(path)

    def _import_book(self, path: str):
        self._controller.import_book(path)

    def _on_import_success(self, metadata, chapters):
        cs = self._convert_screen
        cs.show_book_metadata(metadata.title, metadata.author, len(chapters))
        self._chapter_model = ChapterTableModel(chapters)
        cs.set_chapter_model(self._chapter_model)
        self._refresh_voices()
        self._sidebar.select("convert")
        self._stack.setCurrentWidget(self._convert_screen)
        self._toast.show(f"Loaded: {metadata.title}", "success")

    def _on_import_error(self, message: str):
        QMessageBox.critical(self, "Import Failed", message)

    # ===================================================================
    # Backend handling
    # ===================================================================
    def _init_backend_widgets(self):
        cs = self._convert_screen
        state = self._state.state
        cs.kokoro_model_dir_edit.setText(state.kokoro_model_dir)
        cs.kokoro_model_filename_edit.setText(state.kokoro_model_filename)
        cs.kokoro_voices_edit.setText(", ".join(state.kokoro_voices))
        cs.openrouter_model_edit.setText(state.openrouter_model)
        cs.openrouter_voices_edit.setText(", ".join(state.openrouter_voices))
        self._on_backend_changed(self._header.current_backend())

    def _on_backend_changed(self, backend_str: str):
        self._state.set("backend", BackendType(backend_str))
        self._convert_screen.sync_backend_panels(backend_str)
        self._refresh_voices()

    def _refresh_voices(self):
        backend_str = self._header.current_backend()
        kwargs = self._collect_backend_kwargs()
        voices = self._controller.refresh_voices(backend_str, **kwargs)
        cs = self._convert_screen
        selected = cs.voice_combo.currentText().strip()
        cs.voice_combo.clear()
        for v in voices:
            cs.voice_combo.addItem(v)
        if selected:
            if selected not in voices:
                cs.voice_combo.addItem(selected)
            cs.voice_combo.setCurrentText(selected)

    def _on_voices_loaded(self, backend: str, voices: list[str]):
        self._voices_screen.set_voices(backend, voices)

    # ===================================================================
    # Kokoro folder helpers
    # ===================================================================
    def _browse_kokoro_folder(self):
        cs = self._convert_screen
        d = QFileDialog.getExistingDirectory(
            self, "Kokoro Model Folder",
            cs.kokoro_model_dir_edit.text() or str(Path.home()),
        )
        if d:
            cs.kokoro_model_dir_edit.setText(d)
            self._refresh_voices()

    def _use_default_kokoro_folder(self):
        from book2audiobook.backends.kokoro_backend import resolve_kokoro_model_dir
        default_dir = str(resolve_kokoro_model_dir(app_data_dir()))
        self._convert_screen.kokoro_model_dir_edit.setText(default_dir)
        self._refresh_voices()

    def _load_kokoro_voices(self):
        from book2audiobook.backends.kokoro_backend import load_kokoro_voices_file
        model_dir = Path(self._convert_screen.kokoro_model_dir_edit.text().strip())
        voices = load_kokoro_voices_file(model_dir)
        if voices:
            self._convert_screen.kokoro_voices_edit.setText(", ".join(voices))
            self._refresh_voices()
        else:
            QMessageBox.information(
                self, "voices.txt not found",
                f"No voices.txt found in `{model_dir}`."
            )

    def _save_kokoro_voices(self):
        from book2audiobook.backends.kokoro_backend import save_kokoro_voices_file
        raw = self._convert_screen.kokoro_voices_edit.text().strip()
        voices = normalize_voice_names([raw])
        if not voices:
            QMessageBox.warning(self, "No voices", "Add at least one voice.")
            return
        model_dir = Path(self._convert_screen.kokoro_model_dir_edit.text().strip())
        try:
            target = save_kokoro_voices_file(model_dir, voices)
            QMessageBox.information(self, "Saved", f"Saved voices to {target}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    # ===================================================================
    # Chapter controls
    # ===================================================================
    def _move_chapter(self, offset: int):
        if not hasattr(self, "_chapter_model"):
            return
        idx = self._convert_screen.chapter_table.currentIndex()
        if idx.isValid():
            self._chapter_model.move_row(idx.row(), offset)

    def _combine_chapters(self):
        if not hasattr(self, "_chapter_model"):
            return
        sel = self._convert_screen.chapter_table.selectionModel()
        if sel is None:
            return
        rows = sorted({i.row() for i in sel.selectedRows()})
        if len(rows) < 2:
            QMessageBox.information(self, "Combine Chapters", "Select at least two.")
            return
        new_row = self._chapter_model.combine_rows(rows)
        if new_row is not None:
            self._convert_screen.chapter_table.selectRow(new_row)

    # ===================================================================
    # Conversion
    # ===================================================================
    def _collect_backend_kwargs(self) -> dict:
        cs = self._convert_screen
        return {
            "kokoro_model_dir": cs.kokoro_model_dir_edit.text().strip(),
            "kokoro_model_filename": cs.kokoro_model_filename_edit.text().strip(),
            "kokoro_voices": cs.kokoro_voices_edit.text().strip(),
            "openrouter_model": cs.openrouter_model_edit.text().strip(),
            "openrouter_voices": cs.openrouter_voices_edit.text().strip(),
        }

    def _start_conversion(self):
        state = self._state.state
        if not state.has_book:
            QMessageBox.warning(self, "No book", "Import a book first.")
            return

        cs = self._convert_screen
        voice_id = cs.voice_combo.currentText().strip()
        if not voice_id:
            QMessageBox.warning(self, "No voice", "Select a voice.")
            return

        backend_str = self._header.current_backend()
        fmt_data = cs.format_combo.currentData()
        bitrate = cs.bitrate_combo.currentData()

        started = self._controller.start_conversion(
            backend_str=backend_str,
            voice_id=voice_id,
            speed=cs.speed_slider.value() / 100.0,
            prosody=cs.prosody_spin.value() / 100.0,
            pause_strength=cs.pause_spin.value() / 100.0,
            output_dir=cs.output_dir_label.text(),
            output_format_str=fmt_data,
            bitrate_kbps=int(bitrate),
            metadata=state.metadata,
            chapters=state.chapters,
            **self._collect_backend_kwargs(),
        )
        if started:
            self._toast.show("Conversion started", "info")

    def _cancel_conversion(self):
        reply = QMessageBox.question(
            self, "Cancel Conversion",
            "Are you sure you want to stop the conversion?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._controller.cancel()

    def _on_conversion_finished(self, job_id: str, outputs: dict):
        output_path = outputs.get("output", "")
        self._toast.show(f"Done! Output: {output_path}", "success", 5000)
        QMessageBox.information(self, "Completed", f"Output written to {output_path}")

    def _on_conversion_error(self, job_id: str, message: str):
        self._toast.show("Conversion failed", "error")
        QMessageBox.critical(
            self, "Conversion Failed",
            f"What happened: The conversion pipeline encountered an error.\n\n"
            f"Details:\n{message}\n\n"
            f"How to fix:\n"
            f"• Check the Logs screen for more details\n"
            f"• Verify your backend settings\n"
            f"• Ensure ffmpeg is installed\n"
            f"• Try a different voice or backend"
        )

    def _on_conversion_canceled(self, job_id: str):
        self._toast.show("Conversion canceled", "warning")

    def _on_gpu_fallback(self, reason: str):
        warning = QMessageBox(self)
        warning.setIcon(QMessageBox.Warning)
        warning.setWindowTitle("GPU/Metal Unavailable")
        warning.setText("Kokoro acceleration is unavailable for this run.")
        warning.setInformativeText(
            "Continuing on CPU will be significantly slower.\n\n"
            f"Reason: {reason}"
        )
        continue_btn = warning.addButton("Continue on CPU", QMessageBox.AcceptRole)
        cancel_btn = warning.addButton("Cancel", QMessageBox.RejectRole)
        warning.setDefaultButton(cancel_btn)
        warning.exec()
        if warning.clickedButton() is continue_btn:
            # Retry without GPU check — TODO: pass a skip_gpu_check flag
            self._toast.show("Proceeding on CPU…", "warning")

    # ===================================================================
    # Logging
    # ===================================================================
    def _on_log_line(self, line: str):
        self._convert_screen.log_console.append_line(line)
        self._logs_screen.log_console.append_line(line)

    # ===================================================================
    # Theme
    # ===================================================================
    def _toggle_theme(self):
        if self._theme_manager:
            new_mode = self._theme_manager.cycle_mode()
            labels = {
                ThemeMode.LIGHT: "☀️  Light",
                ThemeMode.DARK: "🌙  Dark",
                ThemeMode.SYSTEM: "🖥  System",
            }
            self._toast.show(f"Theme: {labels.get(new_mode, str(new_mode))}", "info", 1500)

    # ===================================================================
    # Preferences
    # ===================================================================
    def _open_preferences(self):
        dlg = PreferencesDialog(self._config, self)
        dlg.exec()
