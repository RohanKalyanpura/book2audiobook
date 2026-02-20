"""Application state management — single source of truth."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal

from book2audiobook import BackendType, BookMetadata, Chapter, OutputFormat


@dataclass
class AppState:
    """Holds all mutable UI state in one place."""
    # Backend
    backend: BackendType = BackendType.KOKORO

    # Book
    book_path: Optional[Path] = None
    metadata: Optional[BookMetadata] = None
    chapters: list[Chapter] = field(default_factory=list)

    # Voice
    voice_id: str = ""
    speed: float = 1.0
    prosody: float = 1.0
    pause_strength: float = 1.0

    # Output
    output_dir: Path = field(default_factory=Path.home)
    output_format: OutputFormat = OutputFormat.M4B
    bitrate_kbps: int = 64

    # Backend-specific
    kokoro_model_dir: str = ""
    kokoro_model_filename: str = "kokoro-v1_0.pth"
    kokoro_voices: list[str] = field(default_factory=lambda: ["af_bella", "af_nicole"])
    openrouter_model: str = "openai/gpt-audio-mini"
    openrouter_voices: list[str] = field(default_factory=lambda: ["alloy", "verse", "sage", "nova"])

    # Conversion
    is_converting: bool = False
    conversion_step: int = -1       # -1 = not started
    conversion_step_name: str = ""
    overall_progress: float = 0.0
    chapter_progress: float = 0.0

    @property
    def has_book(self) -> bool:
        return self.metadata is not None and len(self.chapters) > 0

    @property
    def can_convert(self) -> bool:
        return self.has_book and bool(self.voice_id) and not self.is_converting


class StateManager(QObject):
    """Observable state container. Screens listen to signals."""

    state_changed = Signal(str, object)  # key, new_value
    book_loaded = Signal()
    conversion_started = Signal()
    conversion_stopped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = AppState()

    def get(self, key: str) -> Any:
        return getattr(self.state, key, None)

    def set(self, key: str, value: Any) -> None:
        if hasattr(self.state, key):
            setattr(self.state, key, value)
            self.state_changed.emit(key, value)

    def set_many(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)
        for key, value in kwargs.items():
            self.state_changed.emit(key, value)

    def reset_conversion(self) -> None:
        self.set_many(
            is_converting=False,
            conversion_step=-1,
            conversion_step_name="",
            overall_progress=0.0,
            chapter_progress=0.0,
        )
        self.conversion_stopped.emit()
