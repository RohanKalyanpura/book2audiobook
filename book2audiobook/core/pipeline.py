from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from book2audiobook import Chapter, OutputFormat
from book2audiobook.core.audio_concat import concat_audio_files
from book2audiobook.core.cache import cache_path, compute_cache_key, sha256_file
from book2audiobook.core.chunking import backend_chunk_target, chunk_text
from book2audiobook.core.cleaning import clean_text
from book2audiobook.core.ffmpeg_packager import (
    build_ffmetadata,
    ffprobe_duration,
    loudnorm_chapter,
    package_m4b,
)
from book2audiobook.core.jobs import JobStore

logger = logging.getLogger(__name__)


class PipelineWorker(QObject):
    log = Signal(str)
    chapter_progress = Signal(str, float)
    overall_progress = Signal(float)
    state_changed = Signal(str, str)
    error = Signal(str, str)
    finished = Signal(str, dict)
    canceled = Signal(str)

    def __init__(
        self,
        *,
        job_store: JobStore,
        backend,
        ffmpeg_bin: str,
        ffprobe_bin: str,
        cache_dir: Path,
        job_dir: Path,
        metadata,
        chapters: list[Chapter],
        voice_settings,
        output_settings,
    ):
        super().__init__()
        self.job_store = job_store
        self.backend = backend
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.cache_dir = cache_dir
        self.job_dir = job_dir
        self.metadata = metadata
        self.chapters = [c for c in chapters if c.include]
        self.voice_settings = voice_settings
        self.output_settings = output_settings
        self.job_id = uuid.uuid4().hex
        self._pause = threading.Event()
        self._cancel = threading.Event()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            self._run_internal()
        except Exception as exc:
            logger.exception("Pipeline failed")
            self.job_store.update_job_state(self.job_id, "FAILED")
            self.state_changed.emit(self.job_id, "FAILED")
            self.error.emit(self.job_id, str(exc))

    def _run_internal(self) -> None:
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.job_store.create_job(
            job_id=self.job_id,
            book_id=self.metadata.title,
            input_hash=self.metadata.source_path.as_posix(),
            chapters=self.chapters,
            output_settings=self.output_settings,
            voice_settings=self.voice_settings,
            snapshot={
                "metadata": {
                    "title": self.metadata.title,
                    "author": self.metadata.author,
                },
                "chapter_count": len(self.chapters),
            },
        )

        self.job_store.update_job_state(self.job_id, "RUNNING", 0)
        self.state_changed.emit(self.job_id, "RUNNING")
        self._log_runtime_diagnostics()
        chapter_outputs: list[tuple[str, Path]] = []
        total_chunks = 0
        chapter_chunks: dict[str, list[str]] = {}

        for chapter in self.chapters:
            cleaned = clean_text(chapter.text)
            hard_max = self.backend.max_chars()
            target = backend_chunk_target(hard_max)
            chunks = chunk_text(cleaned, target_chars=target, hard_max_chars=hard_max)
            chapter_chunks[chapter.id] = chunks
            total_chunks += len(chunks)

        done_chunks = 0
        last_job_progress_update = time.monotonic()
        for chapter in self.chapters:
            if self._cancel.is_set():
                self._emit_canceled()
                return

            chunks = chapter_chunks[chapter.id]
            chunk_files: list[Path] = []
            for idx, text in enumerate(chunks):
                while self._pause.is_set() and not self._cancel.is_set():
                    time.sleep(0.2)
                if self._cancel.is_set():
                    self._emit_canceled(chapter_id=chapter.id, chunk_index=idx)
                    return

                cache_key = compute_cache_key(
                    text=text,
                    backend=self._backend_name(),
                    voice=self.voice_settings.voice_id,
                    speed=self.voice_settings.speed,
                    prosody=self.voice_settings.prosody,
                    pause_strength=self.voice_settings.pause_strength,
                )
                cached = cache_path(self.cache_dir, cache_key, "wav")
                self.job_store.insert_chunk(
                    job_id=self.job_id,
                    chapter_id=chapter.id,
                    chunk_index=idx,
                    text_hash=cache_key,
                    output_path=str(cached),
                    state="RUNNING",
                )

                if not cached.exists():
                    tmp = cached.with_suffix(".tmp.wav")
                    self.backend.synthesize_to_file(
                        text=text,
                        voice=self.voice_settings.voice_id,
                        speed=self.voice_settings.speed,
                        out_path=tmp,
                        prosody=self.voice_settings.prosody,
                        pause_strength=self.voice_settings.pause_strength,
                    )
                    tmp.replace(cached)

                self.job_store.update_chunk_state(
                    job_id=self.job_id,
                    chapter_id=chapter.id,
                    chunk_index=idx,
                    state="DONE",
                )
                chunk_files.append(cached)
                done_chunks += 1
                chapter_pct = done_chunks / max(total_chunks, 1)
                self.chapter_progress.emit(chapter.id, chapter_pct)
                self.overall_progress.emit(chapter_pct)
                now = time.monotonic()
                if chapter_pct >= 1.0 or (now - last_job_progress_update) >= 0.5:
                    self.job_store.update_job_state(self.job_id, "RUNNING", chapter_pct)
                    last_job_progress_update = now

            chapter_out = self.job_dir / f"chapter_{chapter.order_index:03d}.wav"
            concat_audio_files(self.ffmpeg_bin, chunk_files, chapter_out)
            # Skip per-chapter loudnorm. Do it globally instead to save I/O and process spawn.
            chapter_outputs.append((chapter.title, chapter_out))
            self.log.emit(f"Finished chapter: {chapter.title}")

        durations: list[tuple[str, float]] = []
        normalized_files: list[Path] = []
        for title, path in chapter_outputs:
            import wave
            with wave.open(str(path), "rb") as wf:
                dur_s = wf.getnframes() / float(wf.getframerate())
            durations.append((title, dur_s))
            normalized_files.append(path)

        merged = self.job_dir / "book_merged.wav"
        concat_audio_files(self.ffmpeg_bin, normalized_files, merged)

        metadata_path = self.job_dir / "chapters.ffmeta"
        build_ffmetadata(durations, metadata_path)

        output_format = self._output_format()
        output_ext = output_format.value
        output_path = self.output_settings.output_dir / f"{self.metadata.title}.{output_ext}"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_format == OutputFormat.M4B:
            package_m4b(
                self.ffmpeg_bin,
                chapter_audio_file=merged,
                ffmetadata_file=metadata_path,
                output_file=output_path,
                bitrate_kbps=self.output_settings.bitrate_kbps,
                title=self.metadata.title,
                author=self.metadata.author,
                cover_file=self.metadata.cover_image_path,
            )
        elif output_format == OutputFormat.MP3:
            self._transcode(merged, output_path, codec="libmp3lame")
        else:
            self._transcode(merged, output_path, codec="pcm_s16le")

        if self.output_settings.export_chapter_mp3:
            for title, path in chapter_outputs:
                safe = "".join(ch for ch in title if ch.isalnum() or ch in " _-").strip() or "chapter"
                self._transcode(path, self.output_settings.output_dir / f"{safe}.mp3", codec="libmp3lame")
        if self.output_settings.export_chapter_wav:
            for title, path in chapter_outputs:
                safe = "".join(ch for ch in title if ch.isalnum() or ch in " _-").strip() or "chapter"
                self._transcode(path, self.output_settings.output_dir / f"{safe}.wav", codec="pcm_s16le")

        checksum = sha256_file(output_path)
        self.job_store.record_artifact(self.job_id, "final", str(output_path), checksum)
        self.job_store.update_job_state(self.job_id, "COMPLETED", 1.0)
        self.state_changed.emit(self.job_id, "COMPLETED")
        self.finished.emit(self.job_id, {"output": str(output_path), "checksum": checksum})

    def _transcode(self, source: Path, target: Path, codec: str) -> None:
        import subprocess

        cmd = [self.ffmpeg_bin, "-y", "-i", str(source), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", codec]
        if codec == "libmp3lame":
            cmd.extend(["-b:a", f"{self.output_settings.bitrate_kbps}k"])
        cmd.append(str(target))
        subprocess.run(cmd, check=True, capture_output=True)

    def _backend_name(self) -> str:
        backend = getattr(self.voice_settings, "backend", "")
        if hasattr(backend, "value"):
            return str(backend.value)
        text = str(backend).strip().lower()
        if text.startswith("backendtype."):
            return text.split(".", 1)[1]
        return text

    def _output_format(self) -> OutputFormat:
        value = getattr(self.output_settings, "format", OutputFormat.M4B)
        if isinstance(value, OutputFormat):
            return value
        text = str(value).strip().lower()
        if text.startswith("outputformat."):
            text = text.split(".", 1)[1]
        return OutputFormat(text)

    def _emit_canceled(self, chapter_id: str | None = None, chunk_index: int | None = None) -> None:
        if chapter_id is not None and chunk_index is not None:
            self.job_store.update_chunk_state(
                job_id=self.job_id,
                chapter_id=chapter_id,
                chunk_index=chunk_index,
                state="CANCELED",
            )
        self.job_store.update_job_state(self.job_id, "CANCELED")
        self.state_changed.emit(self.job_id, "CANCELED")
        self.canceled.emit(self.job_id)

    def _log_runtime_diagnostics(self) -> None:
        diagnose = getattr(self.backend, "diagnose_runtime", None)
        if not callable(diagnose):
            return
        details = diagnose()
        runtime = str(details.get("runtime", "unknown"))
        device = str(details.get("device", "unknown"))
        fallback = bool(details.get("is_gpu_fallback_to_cpu", False))
        reason = str(details.get("reason", "")).strip()
        if fallback:
            message = f"Backend runtime: {runtime} on {device}. GPU fallback to CPU."
        else:
            message = f"Backend runtime: {runtime} on {device}."
        if reason:
            message = f"{message} {reason}"
        self.log.emit(message)
