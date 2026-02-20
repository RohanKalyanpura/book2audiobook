from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QComboBox,
    QProgressBar,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTableView,
    QAbstractItemView,
    QVBoxLayout,
    QWidget,
)

from book2audiobook import BackendType, OutputFormat, OutputSettings, VoiceSettings, app_data_dir
from book2audiobook.backends.kokoro_backend import (
    KokoroBackend,
    load_kokoro_voices_file,
    normalize_voice_names,
    resolve_kokoro_model_dir,
    save_kokoro_voices_file,
)
from book2audiobook.backends.openai_backend import OpenAIBackend
from book2audiobook.backends.openrouter_backend import OpenRouterBackend
from book2audiobook.core.ffmpeg_packager import verify_ffmpeg
from book2audiobook.core.jobs import JobStore
from book2audiobook.core.pipeline import PipelineWorker
from book2audiobook.io.metadata import parse_book
from book2audiobook.ui.models import ChapterTableModel, JobTableModel
from book2audiobook.ui.widgets import (
    ProviderApiKeysDialog,
    FfmpegMissingDialog,
    LogConsole,
    add_copy_log_button,
)

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Book2Audiobook")
        self.resize(1200, 800)

        self._config = self._load_config()
        self._app_data = app_data_dir()
        self._kokoro_model_dir = resolve_kokoro_model_dir(self._app_data)
        self._kokoro_default_model_dir = self._kokoro_model_dir
        kokoro_cfg = self._config.get("kokoro", {})
        openrouter_cfg = self._config.get("openrouter", {})
        self._kokoro_model_filename = (
            str(kokoro_cfg.get("model_filename", "kokoro-v1_0.pth")).strip() or "kokoro-v1_0.pth"
        )
        self._kokoro_default_voices = normalize_voice_names(kokoro_cfg.get("voices", ["af_bella", "af_nicole"]))
        folder_voices = load_kokoro_voices_file(self._kokoro_model_dir)
        if folder_voices:
            self._kokoro_default_voices = folder_voices
        self._openrouter_model_default = (
            str(openrouter_cfg.get("model", "openai/gpt-audio-mini")).strip() or "openai/gpt-audio-mini"
        )
        self._openrouter_default_voices = normalize_voice_names(
            openrouter_cfg.get("voices", ["alloy", "verse", "sage", "nova"])
        )
        self._job_store = JobStore(self._app_data / "jobs.sqlite3")

        self._metadata = None
        self._chapters = []
        self._worker_thread: QThread | None = None
        self._worker: PipelineWorker | None = None
        self.pause_btn: QPushButton | None = None
        self.resume_btn: QPushButton | None = None
        self.cancel_btn: QPushButton | None = None

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._start_page = self._build_start_page()
        self._editor_page = self._build_editor_page()
        self._progress_page = self._build_progress_page()

        self._stack.addWidget(self._start_page)
        self._stack.addWidget(self._editor_page)
        self._stack.addWidget(self._progress_page)

        self.backend_combo.currentIndexChanged.connect(self._on_backend_selection_changed)

        ffmpeg_bin, ffprobe_bin = verify_ffmpeg()
        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin
        if not ffmpeg_bin or not ffprobe_bin:
            FfmpegMissingDialog(self).exec()

    def _load_config(self) -> dict:
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS"))
            resources = base / "book2audiobook" / "resources" / "default_config.json"
        else:
            resources = Path(__file__).resolve().parents[1] / "resources" / "default_config.json"
        return json.loads(resources.read_text(encoding="utf-8"))

    def _build_start_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Book2Audiobook")
        title.setStyleSheet("font-size: 30px; font-weight: bold;")
        warning = QLabel("Only convert content you have rights to.")
        warning.setStyleSheet("color: #b24020; font-size: 16px;")

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Kokoro (Local)", BackendType.KOKORO.value)
        self.backend_combo.addItem("OpenAI (Cloud)", BackendType.OPENAI.value)
        self.backend_combo.addItem("OpenRouter (Cloud)", BackendType.OPENROUTER.value)

        import_btn = QPushButton("Import Book")
        import_btn.clicked.connect(self._import_book)

        jobs_btn = QPushButton("Open Existing Job")
        jobs_btn.clicked.connect(self._open_existing_job_dialog)

        key_btn = QPushButton("Configure API Keys")
        key_btn.clicked.connect(self._open_key_dialog)

        layout.addWidget(title)
        layout.addWidget(warning)
        layout.addWidget(QLabel("Backend:"))
        layout.addWidget(self.backend_combo)
        layout.addWidget(import_btn)
        layout.addWidget(jobs_btn)
        layout.addWidget(key_btn)
        layout.addStretch(1)
        return page

    def _build_editor_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)

        meta_box = QGroupBox("Book Metadata")
        meta_layout = QFormLayout(meta_box)
        self.title_label = QLabel("-")
        self.author_label = QLabel("-")
        self.cover_label = QLabel("No cover")
        meta_layout.addRow("Title", self.title_label)
        meta_layout.addRow("Author", self.author_label)
        meta_layout.addRow("Cover", self.cover_label)

        chapter_box = QGroupBox("Chapters")
        chapter_layout = QVBoxLayout(chapter_box)
        self.chapter_table = QTableView()
        self.chapter_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.chapter_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        chapter_layout.addWidget(self.chapter_table)
        row_controls = QHBoxLayout()
        up_btn = QPushButton("Move Up")
        down_btn = QPushButton("Move Down")
        combine_btn = QPushButton("Combine Selected")
        up_btn.clicked.connect(lambda: self._move_selected_chapter(-1))
        down_btn.clicked.connect(lambda: self._move_selected_chapter(1))
        combine_btn.clicked.connect(self._combine_selected_chapters)
        row_controls.addWidget(up_btn)
        row_controls.addWidget(down_btn)
        row_controls.addWidget(combine_btn)
        row_controls.addStretch(1)
        chapter_layout.addLayout(row_controls)

        voice_box = QGroupBox("Voice Settings")
        voice_layout = QFormLayout(voice_box)
        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(50)
        self.speed_slider.setMaximum(150)
        self.speed_slider.setValue(100)
        self.prosody_spin = QSpinBox()
        self.prosody_spin.setRange(0, 200)
        self.prosody_spin.setValue(100)
        self.pause_spin = QSpinBox()
        self.pause_spin.setRange(0, 200)
        self.pause_spin.setValue(100)
        voice_layout.addRow("Voice", self.voice_combo)
        voice_layout.addRow("Speed (%)", self.speed_slider)
        voice_layout.addRow("Prosody (%)", self.prosody_spin)
        voice_layout.addRow("Pause Strength (%)", self.pause_spin)

        backend_options_box = QGroupBox("Backend Options")
        backend_options_layout = QVBoxLayout(backend_options_box)

        self.kokoro_options_box = QGroupBox("Kokoro")
        kokoro_layout = QFormLayout(self.kokoro_options_box)
        self.kokoro_model_dir_edit = QLineEdit(str(self._kokoro_model_dir))
        kokoro_dir_row = QWidget()
        kokoro_dir_row_layout = QHBoxLayout(kokoro_dir_row)
        kokoro_dir_row_layout.setContentsMargins(0, 0, 0, 0)
        kokoro_dir_row_layout.addWidget(self.kokoro_model_dir_edit)
        kokoro_browse_btn = QPushButton("Browse...")
        kokoro_browse_btn.clicked.connect(self._choose_kokoro_model_folder)
        kokoro_default_btn = QPushButton("Use Default")
        kokoro_default_btn.clicked.connect(self._use_default_kokoro_model_folder)
        kokoro_dir_row_layout.addWidget(kokoro_browse_btn)
        kokoro_dir_row_layout.addWidget(kokoro_default_btn)
        kokoro_layout.addRow("Model Folder", kokoro_dir_row)

        self.kokoro_model_filename_edit = QLineEdit(self._kokoro_model_filename)
        kokoro_layout.addRow("Model Filename", self.kokoro_model_filename_edit)

        self.kokoro_voices_edit = QLineEdit(", ".join(self._kokoro_default_voices))
        kokoro_layout.addRow("Voices", self.kokoro_voices_edit)
        kokoro_voice_files_row = QWidget()
        kokoro_voice_files_layout = QHBoxLayout(kokoro_voice_files_row)
        kokoro_voice_files_layout.setContentsMargins(0, 0, 0, 0)
        kokoro_load_voices_btn = QPushButton("Load voices.txt")
        kokoro_save_voices_btn = QPushButton("Save voices.txt")
        kokoro_load_voices_btn.clicked.connect(self._load_kokoro_voices_from_folder)
        kokoro_save_voices_btn.clicked.connect(self._save_kokoro_voices_to_folder)
        kokoro_voice_files_layout.addWidget(kokoro_load_voices_btn)
        kokoro_voice_files_layout.addWidget(kokoro_save_voices_btn)
        kokoro_voice_files_layout.addStretch(1)
        kokoro_layout.addRow("", kokoro_voice_files_row)
        kokoro_note = QLabel("Drop your Kokoro model file (.pth/.onnx/.bin) and optional voices.txt into this folder.")
        kokoro_note.setWordWrap(True)
        kokoro_layout.addRow("", kokoro_note)

        self.openrouter_options_box = QGroupBox("OpenRouter")
        openrouter_layout = QFormLayout(self.openrouter_options_box)
        self.openrouter_model_edit = QLineEdit(self._openrouter_model_default)
        self.openrouter_voices_edit = QLineEdit(", ".join(self._openrouter_default_voices))
        openrouter_layout.addRow("Model ID", self.openrouter_model_edit)
        openrouter_layout.addRow("Voices", self.openrouter_voices_edit)
        openrouter_note = QLabel("Paste any OpenRouter model id (example: qwen/qwen3.5-plus-02-15).")
        openrouter_note.setWordWrap(True)
        openrouter_layout.addRow("", openrouter_note)

        self.no_backend_options_label = QLabel("No extra backend options.")

        backend_options_layout.addWidget(self.kokoro_options_box)
        backend_options_layout.addWidget(self.openrouter_options_box)
        backend_options_layout.addWidget(self.no_backend_options_label)

        self.kokoro_model_dir_edit.editingFinished.connect(self._on_kokoro_folder_edited)
        self.kokoro_model_filename_edit.editingFinished.connect(self._refresh_voice_options)
        self.kokoro_voices_edit.editingFinished.connect(self._refresh_voice_options)
        self.openrouter_model_edit.editingFinished.connect(self._refresh_voice_options)
        self.openrouter_voices_edit.editingFinished.connect(self._refresh_voice_options)

        output_box = QGroupBox("Output Settings")
        output_layout = QFormLayout(output_box)
        self.output_dir_btn = QPushButton("Choose Output Folder")
        self.output_dir_btn.clicked.connect(self._choose_output_dir)
        self.output_dir_label = QLabel(str(Path.home()))
        self.format_combo = QComboBox()
        self.format_combo.addItem("M4B", OutputFormat.M4B)
        self.format_combo.addItem("MP3", OutputFormat.MP3)
        self.format_combo.addItem("WAV", OutputFormat.WAV)
        self.bitrate_combo = QComboBox()
        for kbps in [48, 64, 96, 128, 192]:
            self.bitrate_combo.addItem(f"{kbps} kbps", kbps)
        output_layout.addRow(self.output_dir_btn, self.output_dir_label)
        output_layout.addRow("Format", self.format_combo)
        output_layout.addRow("Quality", self.bitrate_combo)

        controls = QHBoxLayout()
        back_btn = QPushButton("Back")
        run_btn = QPushButton("Start Conversion")
        back_btn.clicked.connect(lambda: self._stack.setCurrentWidget(self._start_page))
        run_btn.clicked.connect(self._start_conversion)
        controls.addWidget(back_btn)
        controls.addWidget(run_btn)
        controls.addStretch(1)

        root.addWidget(meta_box)
        root.addWidget(chapter_box)
        root.addWidget(voice_box)
        root.addWidget(backend_options_box)
        root.addWidget(output_box)
        root.addLayout(controls)
        self._on_backend_selection_changed()
        return page

    def _build_progress_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)

        self.overall_bar = QProgressBar()
        self.overall_bar.setMinimum(0)
        self.overall_bar.setMaximum(100)

        self.chapter_bar = QProgressBar()
        self.chapter_bar.setMinimum(0)
        self.chapter_bar.setMaximum(100)

        self.log_console = LogConsole()

        controls = QHBoxLayout()
        self.pause_btn = QPushButton("Pause")
        self.resume_btn = QPushButton("Resume")
        self.cancel_btn = QPushButton("Cancel")
        self.pause_btn.clicked.connect(lambda: self._worker.pause() if self._worker else None)
        self.resume_btn.clicked.connect(lambda: self._worker.resume() if self._worker else None)
        self.cancel_btn.clicked.connect(self._cancel_current_job)
        controls.addWidget(self.pause_btn)
        controls.addWidget(self.resume_btn)
        controls.addWidget(self.cancel_btn)
        controls.addStretch(1)

        root.addWidget(QLabel("Overall Progress"))
        root.addWidget(self.overall_bar)
        root.addWidget(QLabel("Current Chapter Progress"))
        root.addWidget(self.chapter_bar)
        root.addWidget(self.log_console)
        add_copy_log_button(self.log_console, root)
        root.addLayout(controls)
        self._set_progress_controls_enabled(False)
        return page

    def _import_book(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Select Book", str(Path.home()), "Books (*.epub *.pdf *.txt)")
        if not path_str:
            return

        path = Path(path_str)
        try:
            metadata, chapters = parse_book(path)
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return

        self._metadata = metadata
        self._chapters = chapters
        self.title_label.setText(metadata.title)
        self.author_label.setText(metadata.author)
        self.cover_label.setText(str(metadata.cover_image_path) if metadata.cover_image_path else "No cover")
        self.chapter_model = ChapterTableModel(chapters)
        self.chapter_table.setModel(self.chapter_model)
        self._refresh_voice_options()
        self._stack.setCurrentWidget(self._editor_page)

    def _move_selected_chapter(self, offset: int) -> None:
        if not hasattr(self, "chapter_model"):
            return
        index = self.chapter_table.currentIndex()
        if not index.isValid():
            return
        self.chapter_model.move_row(index.row(), offset)

    def _choose_output_dir(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(self, "Output Directory", str(Path.home()))
        if output_dir:
            self.output_dir_label.setText(output_dir)

    def _open_key_dialog(self) -> None:
        ProviderApiKeysDialog(self).exec()

    def _on_backend_selection_changed(self, _index: int | None = None) -> None:
        self._sync_backend_option_panels()
        self._refresh_voice_options()

    def _sync_backend_option_panels(self) -> None:
        if not hasattr(self, "kokoro_options_box"):
            return
        backend = self._selected_backend()
        self.kokoro_options_box.setVisible(backend == BackendType.KOKORO)
        self.openrouter_options_box.setVisible(backend == BackendType.OPENROUTER)
        self.no_backend_options_label.setVisible(backend == BackendType.OPENAI)

    def _choose_kokoro_model_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Kokoro Model Folder",
            str(self._current_kokoro_model_dir()),
        )
        if not selected:
            return
        self.kokoro_model_dir_edit.setText(selected)
        self._load_kokoro_voices_from_folder(silent=True)
        self._refresh_voice_options()

    def _use_default_kokoro_model_folder(self) -> None:
        self.kokoro_model_dir_edit.setText(str(self._kokoro_default_model_dir))
        self._load_kokoro_voices_from_folder(silent=True)
        self._refresh_voice_options()

    def _on_kokoro_folder_edited(self) -> None:
        self._load_kokoro_voices_from_folder(silent=True)
        self._refresh_voice_options()

    def _current_kokoro_model_dir(self) -> Path:
        if not hasattr(self, "kokoro_model_dir_edit"):
            return self._kokoro_model_dir
        raw = self.kokoro_model_dir_edit.text().strip()
        if not raw:
            return self._kokoro_model_dir
        return Path(raw).expanduser()

    def _current_kokoro_model_filename(self) -> str:
        if not hasattr(self, "kokoro_model_filename_edit"):
            return self._kokoro_model_filename
        name = self.kokoro_model_filename_edit.text().strip()
        return name or self._kokoro_model_filename

    @staticmethod
    def _parse_voice_text(raw: str) -> list[str]:
        return normalize_voice_names([raw])

    def _kokoro_custom_voices(self) -> list[str]:
        if not hasattr(self, "kokoro_voices_edit"):
            return list(self._kokoro_default_voices)
        return self._parse_voice_text(self.kokoro_voices_edit.text())

    def _openrouter_custom_voices(self) -> list[str]:
        if not hasattr(self, "openrouter_voices_edit"):
            return list(self._openrouter_default_voices)
        return self._parse_voice_text(self.openrouter_voices_edit.text())

    def _build_backend(self, backend: BackendType):
        if backend == BackendType.KOKORO:
            voices = self._kokoro_custom_voices()
            return KokoroBackend(
                self._current_kokoro_model_dir(),
                self._config,
                voices=voices or None,
                model_filename=self._current_kokoro_model_filename(),
            )
        if backend == BackendType.OPENROUTER:
            model = self.openrouter_model_edit.text().strip() if hasattr(self, "openrouter_model_edit") else ""
            if not model:
                raise RuntimeError("OpenRouter model id is required.")
            voices = self._openrouter_custom_voices()
            return OpenRouterBackend(
                self._config,
                model=model,
                voices=voices or None,
            )
        return OpenAIBackend(self._config)

    def _load_kokoro_voices_from_folder(self, *, silent: bool = False) -> None:
        if not hasattr(self, "kokoro_voices_edit"):
            return
        voices = load_kokoro_voices_file(self._current_kokoro_model_dir())
        if voices:
            self.kokoro_voices_edit.setText(", ".join(voices))
            return
        if not silent:
            QMessageBox.information(
                self,
                "voices.txt not found",
                f"No voices.txt found in `{self._current_kokoro_model_dir()}`.",
            )

    def _save_kokoro_voices_to_folder(self) -> None:
        voices = self._kokoro_custom_voices()
        if not voices:
            QMessageBox.warning(self, "No voices", "Add at least one voice before saving voices.txt.")
            return
        model_dir = self._current_kokoro_model_dir()
        try:
            target = save_kokoro_voices_file(model_dir, voices)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        QMessageBox.information(self, "Saved", f"Saved voices to {target}")

    def _refresh_voice_options(self) -> None:
        if not hasattr(self, "voice_combo"):
            return
        selected_voice = self.voice_combo.currentText().strip()
        self.voice_combo.clear()
        backend = self._selected_backend()
        try:
            instance = self._build_backend(backend)
            voices = instance.list_voices()
            for voice in voices:
                self.voice_combo.addItem(voice)
            if selected_voice:
                if selected_voice not in voices:
                    self.voice_combo.addItem(selected_voice)
                self.voice_combo.setCurrentText(selected_voice)
        except Exception as exc:
            logger.warning("voice refresh failed: %s", exc)

    def _open_existing_job_dialog(self) -> None:
        jobs = self._job_store.list_jobs()
        dlg = QDialog(self)
        dlg.setWindowTitle("Existing Jobs")
        layout = QVBoxLayout(dlg)
        table = QTableView()
        table.setModel(JobTableModel(jobs))
        layout.addWidget(table)
        dlg.resize(800, 400)
        dlg.exec()

    def _start_conversion(self) -> None:
        if not self._metadata or not self._chapters:
            QMessageBox.warning(self, "Missing input", "Please import a book first.")
            return
        if not self._ffmpeg_bin or not self._ffprobe_bin:
            FfmpegMissingDialog(self).exec()
            return
        if self._worker_thread and self._worker_thread.isRunning():
            QMessageBox.warning(self, "Job already running", "Wait for the current job to finish or cancel it.")
            return

        backend_type = self._selected_backend()
        try:
            backend = self._build_backend(backend_type)
        except Exception as exc:
            QMessageBox.critical(self, "Backend init failed", str(exc))
            return

        if backend_type == BackendType.KOKORO and hasattr(backend, "diagnose_runtime"):
            try:
                runtime_diag = backend.diagnose_runtime()
            except Exception as exc:
                QMessageBox.critical(self, "Backend init failed", str(exc))
                return

            require_confirm = bool(
                self._config.get("kokoro", {}).get("require_gpu_confirm_on_cpu_fallback", True)
            )
            if require_confirm and bool(runtime_diag.get("is_gpu_fallback_to_cpu", False)):
                reason = str(runtime_diag.get("reason", "")).strip()
                warning = QMessageBox(self)
                warning.setIcon(QMessageBox.Warning)
                warning.setWindowTitle("GPU/Metal Unavailable")
                warning.setText("Kokoro acceleration is unavailable for this run.")
                warning.setInformativeText(
                    "Continuing on CPU will be significantly slower.\n\n"
                    f"Reason: {reason or 'No compatible GPU/Metal backend detected.'}"
                )
                continue_btn = warning.addButton("Continue on CPU", QMessageBox.AcceptRole)
                cancel_btn = warning.addButton("Cancel", QMessageBox.RejectRole)
                warning.setDefaultButton(cancel_btn)
                warning.exec()
                if warning.clickedButton() is not continue_btn:
                    return

        voice_id = self.voice_combo.currentText().strip()
        if not voice_id:
            QMessageBox.warning(self, "Missing voice", "Select or type a voice.")
            return

        voice_settings = VoiceSettings(
            backend=backend_type,
            voice_id=voice_id,
            speed=self.speed_slider.value() / 100.0,
            prosody=self.prosody_spin.value() / 100.0,
            pause_strength=self.pause_spin.value() / 100.0,
        )
        try:
            output_format = self._selected_output_format()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid output format", str(exc))
            return

        output_settings = OutputSettings(
            output_dir=Path(self.output_dir_label.text()),
            format=output_format,
            bitrate_kbps=int(self.bitrate_combo.currentData()),
            export_chapter_mp3=False,
            export_chapter_wav=False,
        )

        self._worker = PipelineWorker(
            job_store=self._job_store,
            backend=backend,
            ffmpeg_bin=self._ffmpeg_bin,
            ffprobe_bin=self._ffprobe_bin,
            cache_dir=self._app_data / "cache",
            job_dir=self._app_data / "jobs" / self._metadata.title,
            metadata=self._metadata,
            chapters=self._chapters,
            voice_settings=voice_settings,
            output_settings=output_settings,
        )

        self._worker_thread = QThread(self)
        # Kokoro runtimes may invoke heavy NumPy/OpenBLAS paths in this worker.
        # Give the Qt worker thread more stack space to avoid stack-guard crashes on macOS.
        self._worker_thread.setStackSize(16 * 1024 * 1024)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.log.connect(self.log_console.append_line)
        self._worker.chapter_progress.connect(self._on_chapter_progress)
        self._worker.overall_progress.connect(self._on_overall_progress)
        self._worker.finished.connect(self._on_job_finished)
        self._worker.error.connect(self._on_job_error)
        self._worker.canceled.connect(self._on_job_canceled)
        self._worker.state_changed.connect(lambda _job_id, state: self.log_console.append_line(f"State: {state}"))

        self._set_progress_controls_enabled(True)
        self.overall_bar.setValue(0)
        self.chapter_bar.setValue(0)
        self._stack.setCurrentWidget(self._progress_page)
        self._worker_thread.start()

    def _selected_backend(self) -> BackendType:
        raw = self.backend_combo.currentData()
        if isinstance(raw, BackendType):
            return raw
        text = str(raw).strip().lower()
        if text.startswith("backendtype."):
            text = text.split(".", 1)[1]
        return BackendType(text)

    def _selected_output_format(self) -> OutputFormat:
        raw = self.format_combo.currentData()
        if isinstance(raw, OutputFormat):
            return raw
        text = str(raw).strip().lower()
        if text.startswith("outputformat."):
            text = text.split(".", 1)[1]
        return OutputFormat(text)

    def _combine_selected_chapters(self) -> None:
        if not hasattr(self, "chapter_model") or self.chapter_table.selectionModel() is None:
            return
        rows = sorted({idx.row() for idx in self.chapter_table.selectionModel().selectedRows()})
        if len(rows) < 2:
            QMessageBox.information(self, "Combine Chapters", "Select at least two chapters.")
            return
        new_row = self.chapter_model.combine_rows(rows)
        if new_row is not None:
            self.chapter_table.selectRow(new_row)

    def _on_chapter_progress(self, _chapter_id: str, pct: float) -> None:
        self.chapter_bar.setValue(int(pct * 100))

    def _on_overall_progress(self, pct: float) -> None:
        self.overall_bar.setValue(int(pct * 100))

    def _on_job_finished(self, _job_id: str, outputs: dict) -> None:
        self._teardown_worker()
        self.log_console.append_line(f"Done: {outputs}")
        QMessageBox.information(self, "Completed", f"Output written to {outputs.get('output')}")
        self._stack.setCurrentWidget(self._editor_page)

    def _on_job_error(self, _job_id: str, message: str) -> None:
        self._teardown_worker()
        self.log_console.append_line(f"ERROR: {message}")
        QMessageBox.critical(self, "Job Failed", message)
        self._stack.setCurrentWidget(self._editor_page)

    def _on_job_canceled(self, _job_id: str) -> None:
        self._teardown_worker()
        self.log_console.append_line("Job canceled.")
        QMessageBox.information(self, "Canceled", "Conversion was canceled.")
        self._stack.setCurrentWidget(self._editor_page)

    def _cancel_current_job(self) -> None:
        if not self._worker:
            self._stack.setCurrentWidget(self._editor_page if self._metadata else self._start_page)
            return
        self.log_console.append_line("Cancel requested.")
        self._set_progress_controls_enabled(False)
        self._worker.cancel()

    def _set_progress_controls_enabled(self, enabled: bool) -> None:
        if self.pause_btn is not None:
            self.pause_btn.setEnabled(enabled)
        if self.resume_btn is not None:
            self.resume_btn.setEnabled(enabled)
        if self.cancel_btn is not None:
            self.cancel_btn.setEnabled(enabled)

    def _teardown_worker(self) -> None:
        worker = self._worker
        thread = self._worker_thread
        self._worker = None
        self._worker_thread = None
        self._set_progress_controls_enabled(False)

        if thread is not None:
            thread.quit()
            thread.wait(2000)
            thread.deleteLater()
        if worker is not None:
            worker.deleteLater()
