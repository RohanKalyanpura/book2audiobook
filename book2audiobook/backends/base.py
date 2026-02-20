from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TTSBackend(Protocol):
    def list_voices(self) -> list[str]:
        ...

    def synthesize_to_file(self, text: str, voice: str, speed: float, out_path: Path, **kwargs) -> None:
        ...

    def max_chars(self) -> int:
        ...
