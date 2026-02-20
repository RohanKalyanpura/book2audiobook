from __future__ import annotations

import subprocess
import wave
from pathlib import Path


def concat_audio_files(ffmpeg_bin: str, files: list[Path], output: Path) -> None:
    if not files:
        raise ValueError("No audio files provided")

    _concat_wav_in_memory(files, output)


def _concat_wav_in_memory(files: list[Path], output: Path) -> None:
    """Concatenate 24kHz PCM WAV chunks purely in python without ffmpeg sub-processes."""
    if not files:
        return

    # Read the first file to get format params (assuming all are exactly the same, e.g. Kokoro 24kHz Mono 16-bit PCM)
    with wave.open(str(files[0]), "rb") as first:
        params = first.getparams()

    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as out_wav:
        out_wav.setparams(params)
        for chunk_file in files:
            with wave.open(str(chunk_file), "rb") as cur:
                data = cur.readframes(cur.getnframes())
                out_wav.writeframes(data)
