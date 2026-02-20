from __future__ import annotations

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qtcore_module = types.ModuleType("PySide6.QtCore")


class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, callback):
        self._slots.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._slots):
            callback(*args, **kwargs)


class _QObject:
    def __init__(self, *args, **kwargs):
        pass


qtcore_module.Signal = lambda *args, **kwargs: _Signal()
qtcore_module.QObject = _QObject
sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
sys.modules["PySide6.QtCore"] = qtcore_module
sys.modules["PySide6"].QtCore = qtcore_module  # type: ignore[attr-defined]

from book2audiobook import (
    BackendType,
    BookMetadata,
    Chapter,
    OutputFormat,
    OutputSettings,
    VoiceSettings,
)
from book2audiobook.core.jobs import JobStore
from book2audiobook.core.pipeline import PipelineWorker


class _FakeBackend:
    def max_chars(self) -> int:
        return 500

    def synthesize_to_file(self, text: str, voice: str, speed: float, out_path: Path, **kwargs) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(f"{voice}:{text}:{speed}".encode("utf-8"))

    def diagnose_runtime(self) -> dict[str, object]:
        return {
            "runtime": "modern",
            "device": "cpu",
            "is_gpu_fallback_to_cpu": True,
            "reason": "No GPU backend available.",
        }


def test_pipeline_throttles_job_state_progress_updates(tmp_path: Path, monkeypatch) -> None:
    chapter = Chapter(
        id="c1",
        title="One",
        text="placeholder",
        include=True,
        order_index=0,
        preview="placeholder",
    )
    metadata = BookMetadata(
        title="Book",
        author="Author",
        cover_image_path=None,
        source_path=tmp_path / "book.txt",
        source_type="txt",
    )
    voice_settings = VoiceSettings(backend=BackendType.KOKORO, voice_id="af_bella", speed=1.0)
    output_settings = OutputSettings(output_dir=tmp_path, format=OutputFormat.M4B)
    store = JobStore(tmp_path / "jobs.sqlite3")

    worker = PipelineWorker(
        job_store=store,
        backend=_FakeBackend(),
        ffmpeg_bin="ffmpeg",
        ffprobe_bin="ffprobe",
        cache_dir=tmp_path / "cache",
        job_dir=tmp_path / "jobs",
        metadata=metadata,
        chapters=[chapter],
        voice_settings=voice_settings,
        output_settings=output_settings,
    )

    chunk_count = 20
    monkeypatch.setattr("book2audiobook.core.pipeline.clean_text", lambda text: text)
    monkeypatch.setattr(
        "book2audiobook.core.pipeline.chunk_text",
        lambda text, target_chars, hard_max_chars: [f"chunk-{idx}" for idx in range(chunk_count)],
    )
    monkeypatch.setattr(
        "book2audiobook.core.pipeline.concat_audio_files",
        lambda _ffmpeg, files, output: output.write_bytes(b"".join(path.read_bytes() for path in files)),
    )
    monkeypatch.setattr(
        "book2audiobook.core.pipeline.loudnorm_chapter",
        lambda _ffmpeg, source, target: target.write_bytes(source.read_bytes()),
    )
    monkeypatch.setattr("book2audiobook.core.pipeline.ffprobe_duration", lambda _ffprobe, _path: 1.0)
    monkeypatch.setattr(
        "book2audiobook.core.pipeline.build_ffmetadata",
        lambda durations, out_path: out_path.write_text(str(durations), encoding="utf-8"),
    )
    monkeypatch.setattr(
        "book2audiobook.core.pipeline.package_m4b",
        lambda _ffmpeg, chapter_audio_file, ffmetadata_file, output_file, bitrate_kbps, title, author, cover_file: output_file.write_bytes(
            chapter_audio_file.read_bytes() + ffmetadata_file.read_bytes()
        ),
    )

    progress_updates: list[float] = []
    original_update_job_state = store.update_job_state

    def _record_progress(job_id: str, state: str, progress: float | None = None) -> None:
        if state == "RUNNING" and progress is not None:
            progress_updates.append(progress)
        original_update_job_state(job_id, state, progress)

    store.update_job_state = _record_progress  # type: ignore[assignment]
    worker.run()

    assert progress_updates
    assert progress_updates[-1] == 1.0
    assert len(progress_updates) < chunk_count
