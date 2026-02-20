"""Conversion controller — bridges UI actions to PipelineWorker."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from book2audiobook import (
    BackendType, BookMetadata, Chapter, OutputFormat,
    OutputSettings, VoiceSettings, app_data_dir,
)
from book2audiobook.backends.kokoro_backend import (
    KokoroBackend, load_kokoro_voices_file, normalize_voice_names,
    resolve_kokoro_model_dir, save_kokoro_voices_file,
)
from book2audiobook.backends.openai_backend import OpenAIBackend
from book2audiobook.backends.openrouter_backend import OpenRouterBackend
from book2audiobook.core.ffmpeg_packager import verify_ffmpeg
from book2audiobook.core.jobs import JobStore
from book2audiobook.core.pipeline import PipelineWorker
from book2audiobook.io.metadata import parse_book
from book2audiobook.ui.state import StateManager

logger = logging.getLogger(__name__)


class ConversionController(QObject):
    """
    Orchestrates the conversion pipeline without touching UI widgets directly.
    Communicates via signals and the shared StateManager.
    """

    # Signals for the UI to listen to
    log_line = Signal(str)
    import_success = Signal(object, list)       # (BookMetadata, list[Chapter])
    import_error = Signal(str)
    conversion_finished = Signal(str, dict)     # job_id, outputs
    conversion_error = Signal(str, str)         # job_id, message
    conversion_canceled = Signal(str)           # job_id
    voices_loaded = Signal(str, list)           # backend, voices list
    gpu_fallback_warning = Signal(str)          # reason
    ffmpeg_missing = Signal()

    def __init__(self, state: StateManager, config: dict, parent=None):
        super().__init__(parent)
        self._state = state
        self._config = config
        self._app_data = app_data_dir()
        self._job_store = JobStore(self._app_data / "jobs.sqlite3")

        # FFmpeg
        ffmpeg_bin, ffprobe_bin = verify_ffmpeg()
        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin
        if not ffmpeg_bin or not ffprobe_bin:
            self.ffmpeg_missing.emit()

        # Kokoro defaults
        self._kokoro_model_dir = resolve_kokoro_model_dir(self._app_data)
        kokoro_cfg = config.get("kokoro", {})
        self._kokoro_model_filename = (
            str(kokoro_cfg.get("model_filename", "kokoro-v1_0.pth")).strip()
            or "kokoro-v1_0.pth"
        )
        self._kokoro_default_voices = normalize_voice_names(
            kokoro_cfg.get("voices", ["af_bella", "af_nicole"])
        )
        folder_voices = load_kokoro_voices_file(self._kokoro_model_dir)
        if folder_voices:
            self._kokoro_default_voices = folder_voices

        # OpenRouter defaults
        openrouter_cfg = config.get("openrouter", {})
        self._openrouter_model_default = (
            str(openrouter_cfg.get("model", "openai/gpt-audio-mini")).strip()
            or "openai/gpt-audio-mini"
        )
        self._openrouter_default_voices = normalize_voice_names(
            openrouter_cfg.get("voices", ["alloy", "verse", "sage", "nova"])
        )

        # Worker state
        self._worker: PipelineWorker | None = None
        self._worker_thread: QThread | None = None

        # Initialize state with defaults
        state.set_many(
            kokoro_model_dir=str(self._kokoro_model_dir),
            kokoro_model_filename=self._kokoro_model_filename,
            kokoro_voices=self._kokoro_default_voices,
            openrouter_model=self._openrouter_model_default,
            openrouter_voices=self._openrouter_default_voices,
        )

    # -----------------------------------------------------------------------
    # Book import
    # -----------------------------------------------------------------------
    def import_book(self, path: str) -> None:
        book_path = Path(path)
        try:
            metadata, chapters = parse_book(book_path)
        except Exception as exc:
            self.import_error.emit(str(exc))
            return

        self._state.set_many(
            book_path=book_path,
            metadata=metadata,
            chapters=chapters,
        )
        self._state.book_loaded.emit()
        self.import_success.emit(metadata, chapters)

    # -----------------------------------------------------------------------
    # Voice listing
    # -----------------------------------------------------------------------
    def refresh_voices(self, backend_str: str, **kwargs) -> list[str]:
        """Load voices for the given backend. Returns the voice list."""
        backend_type = BackendType(backend_str)
        try:
            instance = self._build_backend(backend_type, **kwargs)
            voices = instance.list_voices()
            self.voices_loaded.emit(backend_str, voices)
            return voices
        except Exception as exc:
            logger.warning("Voice refresh failed for %s: %s", backend_str, exc)
            return []

    # -----------------------------------------------------------------------
    # Conversion
    # -----------------------------------------------------------------------
    def start_conversion(
        self,
        backend_str: str,
        voice_id: str,
        speed: float,
        prosody: float,
        pause_strength: float,
        output_dir: str,
        output_format_str: str,
        bitrate_kbps: int,
        metadata: BookMetadata,
        chapters: list[Chapter],
        **backend_kwargs,
    ) -> bool:
        """Start the conversion pipeline. Returns True if started."""
        if self._worker_thread and self._worker_thread.isRunning():
            self.log_line.emit("A job is already running.")
            return False

        if not self._ffmpeg_bin or not self._ffprobe_bin:
            self.ffmpeg_missing.emit()
            return False

        backend_type = BackendType(backend_str)
        try:
            backend = self._build_backend(backend_type, **backend_kwargs)
        except Exception as exc:
            self.conversion_error.emit("", f"Backend init failed: {exc}")
            return False

        # GPU fallback check for Kokoro
        if backend_type == BackendType.KOKORO and hasattr(backend, "diagnose_runtime"):
            try:
                diag = backend.diagnose_runtime()
                require_confirm = bool(
                    self._config.get("kokoro", {}).get("require_gpu_confirm_on_cpu_fallback", True)
                )
                if require_confirm and bool(diag.get("is_gpu_fallback_to_cpu", False)):
                    reason = str(diag.get("reason", "")).strip()
                    self.gpu_fallback_warning.emit(
                        reason or "No compatible GPU/Metal backend detected."
                    )
                    return False  # caller should show confirm dialog then retry
            except Exception as exc:
                self.conversion_error.emit("", f"Backend runtime check failed: {exc}")
                return False

        voice_settings = VoiceSettings(
            backend=backend_type,
            voice_id=voice_id,
            speed=speed,
            prosody=prosody,
            pause_strength=pause_strength,
        )
        output_format = OutputFormat(output_format_str)
        output_settings = OutputSettings(
            output_dir=Path(output_dir),
            format=output_format,
            bitrate_kbps=bitrate_kbps,
            export_chapter_mp3=False,
            export_chapter_wav=False,
        )

        self._worker = PipelineWorker(
            job_store=self._job_store,
            backend=backend,
            ffmpeg_bin=self._ffmpeg_bin,
            ffprobe_bin=self._ffprobe_bin,
            cache_dir=self._app_data / "cache",
            job_dir=self._app_data / "jobs" / metadata.title,
            metadata=metadata,
            chapters=chapters,
            voice_settings=voice_settings,
            output_settings=output_settings,
        )

        self._worker_thread = QThread()
        self._worker_thread.setStackSize(16 * 1024 * 1024)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)

        # Connect signals
        self._worker.log.connect(self.log_line.emit)
        self._worker.chapter_progress.connect(self._on_chapter_progress)
        self._worker.overall_progress.connect(self._on_overall_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.canceled.connect(self._on_canceled)
        self._worker.state_changed.connect(
            lambda _jid, s: self.log_line.emit(f"State: {s}")
        )

        self._state.set("is_converting", True)
        self._state.conversion_started.emit()
        self._worker_thread.start()
        return True

    def cancel(self) -> None:
        if self._worker:
            self.log_line.emit("Cancel requested.")
            self._worker.cancel()

    def pause(self) -> None:
        if self._worker:
            self._worker.pause()

    def resume(self) -> None:
        if self._worker:
            self._worker.resume()

    @property
    def job_store(self) -> JobStore:
        return self._job_store

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------
    def _build_backend(self, backend_type: BackendType, **kwargs):
        if backend_type == BackendType.KOKORO:
            model_dir = kwargs.get("kokoro_model_dir", str(self._kokoro_model_dir))
            model_filename = kwargs.get("kokoro_model_filename", self._kokoro_model_filename)
            voices_raw = kwargs.get("kokoro_voices", self._kokoro_default_voices)
            if isinstance(voices_raw, str):
                voices = normalize_voice_names([voices_raw])
            else:
                voices = list(voices_raw)
            return KokoroBackend(
                Path(model_dir),
                self._config,
                voices=voices or None,
                model_filename=model_filename,
            )
        if backend_type == BackendType.OPENROUTER:
            model = kwargs.get("openrouter_model", self._openrouter_model_default)
            voices_raw = kwargs.get("openrouter_voices", self._openrouter_default_voices)
            if isinstance(voices_raw, str):
                voices = normalize_voice_names([voices_raw])
            else:
                voices = list(voices_raw)
            return OpenRouterBackend(
                self._config,
                model=model,
                voices=voices or None,
            )
        return OpenAIBackend(self._config)

    def _on_chapter_progress(self, chapter_id: str, pct: float) -> None:
        self._state.set("chapter_progress", pct)

    def _on_overall_progress(self, pct: float) -> None:
        self._state.set("overall_progress", pct)

    def _on_finished(self, job_id: str, outputs: dict) -> None:
        self._teardown()
        self.conversion_finished.emit(job_id, outputs)

    def _on_error(self, job_id: str, message: str) -> None:
        self._teardown()
        self.conversion_error.emit(job_id, message)

    def _on_canceled(self, job_id: str) -> None:
        self._teardown()
        self.conversion_canceled.emit(job_id)

    def _teardown(self) -> None:
        worker = self._worker
        thread = self._worker_thread
        self._worker = None
        self._worker_thread = None
        self._state.reset_conversion()

        if thread is not None:
            thread.quit()
            thread.wait(2000)
            thread.deleteLater()
        if worker is not None:
            worker.deleteLater()
