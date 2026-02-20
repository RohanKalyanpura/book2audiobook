from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from platformdirs import user_data_dir

APP_NAME = "Book2Audiobook"
APP_AUTHOR = "Book2Audiobook"


class BackendType(str, Enum):
    KOKORO = "kokoro"
    OPENAI = "openai"
    OPENROUTER = "openrouter"


class OutputFormat(str, Enum):
    M4B = "m4b"
    MP3 = "mp3"
    WAV = "wav"


@dataclass
class BookMetadata:
    title: str
    author: str
    cover_image_path: Path | None
    source_path: Path
    source_type: str


@dataclass
class Chapter:
    id: str
    title: str
    text: str
    include: bool
    order_index: int
    preview: str


@dataclass
class VoiceSettings:
    backend: BackendType
    voice_id: str
    speed: float = 1.0
    prosody: float | None = None
    pause_strength: float | None = None


@dataclass
class OutputSettings:
    output_dir: Path
    format: OutputFormat = OutputFormat.M4B
    bitrate_kbps: int = 64
    export_chapter_wav: bool = False
    export_chapter_mp3: bool = False


@dataclass
class ChunkTask:
    chapter_id: str
    chunk_index: int
    text: str
    cache_key: str
    target_path: Path
    state: str = "PENDING"


@dataclass
class JobRecord:
    job_id: str
    book_id: str
    status: str
    created_at: str
    updated_at: str
    progress: float


def app_data_dir() -> Path:
    path = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = [
    "APP_NAME",
    "APP_AUTHOR",
    "BackendType",
    "OutputFormat",
    "BookMetadata",
    "Chapter",
    "VoiceSettings",
    "OutputSettings",
    "ChunkTask",
    "JobRecord",
    "app_data_dir",
]
