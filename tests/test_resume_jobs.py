from pathlib import Path

from book2audiobook import BackendType, Chapter, OutputFormat, OutputSettings, VoiceSettings
from book2audiobook.core.jobs import JobStore


def _sample_chapters() -> list[Chapter]:
    return [
        Chapter(id="c1", title="One", text="hello", include=True, order_index=0, preview="hello"),
        Chapter(id="c2", title="Two", text="world", include=True, order_index=1, preview="world"),
    ]


def test_running_chunks_reset_on_resume(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite")
    store.create_job(
        job_id="job1",
        book_id="book",
        input_hash="hash",
        chapters=_sample_chapters(),
        output_settings=OutputSettings(output_dir=tmp_path, format=OutputFormat.M4B),
        voice_settings=VoiceSettings(backend=BackendType.KOKORO, voice_id="alloy"),
        snapshot={"ok": True},
    )
    store.insert_chunk(job_id="job1", chapter_id="c1", chunk_index=0, text_hash="x", output_path="/tmp/a.wav", state="RUNNING")
    store.mark_running_chunks_pending("job1")

    rows = store.load_chunks("job1")
    assert len(rows) == 1
    assert rows[0]["state"] == "PENDING"


def test_non_terminal_job_listing(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite")
    store.create_job(
        job_id="job1",
        book_id="book",
        input_hash="hash",
        chapters=_sample_chapters(),
        output_settings=OutputSettings(output_dir=tmp_path),
        voice_settings=VoiceSettings(backend=BackendType.KOKORO, voice_id="alloy"),
        snapshot={"ok": True},
    )
    store.update_job_state("job1", "RUNNING", 0.5)
    jobs = store.list_non_terminal_jobs()
    assert jobs
    assert jobs[0].job_id == "job1"
    assert jobs[0].status == "RUNNING"
