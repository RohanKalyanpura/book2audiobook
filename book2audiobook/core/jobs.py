from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from book2audiobook import Chapter, JobRecord, OutputSettings, VoiceSettings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    output_settings_json TEXT NOT NULL,
    voice_settings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    title TEXT NOT NULL,
    chapter_order INTEGER NOT NULL,
    include_flag INTEGER NOT NULL,
    state TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    chapter_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text_hash TEXT NOT NULL,
    output_path TEXT NOT NULL,
    state TEXT NOT NULL,
    error TEXT,
    UNIQUE(job_id, chapter_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    checksum TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings_snapshot (
    job_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);
"""

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELED"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def create_job(
        self,
        *,
        job_id: str,
        book_id: str,
        input_hash: str,
        chapters: list[Chapter],
        output_settings: OutputSettings,
        voice_settings: VoiceSettings,
        snapshot: dict[str, Any],
    ) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(job_id, book_id, input_hash, status, output_settings_json, voice_settings_json, created_at, updated_at, progress)
                VALUES(?, ?, ?, 'PENDING', ?, ?, ?, ?, 0)
                """,
                (
                    job_id,
                    book_id,
                    input_hash,
                    json.dumps(asdict(output_settings), default=str),
                    json.dumps(asdict(voice_settings), default=str),
                    now,
                    now,
                ),
            )
            for chapter in chapters:
                conn.execute(
                    """
                    INSERT INTO chapters(id, job_id, title, chapter_order, include_flag, state)
                    VALUES (?, ?, ?, ?, ?, 'PENDING')
                    """,
                    (
                        chapter.id,
                        job_id,
                        chapter.title,
                        chapter.order_index,
                        1 if chapter.include else 0,
                    ),
                )
            conn.execute(
                "INSERT INTO settings_snapshot(job_id, payload_json) VALUES(?, ?)",
                (job_id, json.dumps(snapshot, default=str)),
            )
            conn.commit()

    def insert_chunk(
        self,
        *,
        job_id: str,
        chapter_id: str,
        chunk_index: int,
        text_hash: str,
        output_path: str,
        state: str = "PENDING",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO chunks(job_id, chapter_id, chunk_index, text_hash, output_path, state)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (job_id, chapter_id, chunk_index, text_hash, output_path, state),
            )
            conn.commit()

    def update_chunk_state(
        self,
        *,
        job_id: str,
        chapter_id: str,
        chunk_index: int,
        state: str,
        error: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE chunks
                SET state = ?, error = ?
                WHERE job_id = ? AND chapter_id = ? AND chunk_index = ?
                """,
                (state, error, job_id, chapter_id, chunk_index),
            )
            conn.commit()

    def update_job_state(self, job_id: str, state: str, progress: float | None = None) -> None:
        with self._connect() as conn:
            if progress is None:
                conn.execute(
                    "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                    (state, utc_now_iso(), job_id),
                )
            else:
                conn.execute(
                    "UPDATE jobs SET status = ?, progress = ?, updated_at = ? WHERE job_id = ?",
                    (state, progress, utc_now_iso(), job_id),
                )
            conn.commit()

    def mark_running_chunks_pending(self, job_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE chunks SET state = 'PENDING' WHERE job_id = ? AND state = 'RUNNING'",
                (job_id,),
            )
            conn.commit()

    def list_non_terminal_jobs(self) -> list[JobRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT job_id, book_id, status, created_at, updated_at, progress
                FROM jobs
                WHERE status NOT IN ('COMPLETED', 'FAILED', 'CANCELED')
                ORDER BY updated_at DESC
                """
            ).fetchall()
            return [
                JobRecord(
                    job_id=row["job_id"],
                    book_id=row["book_id"],
                    status=row["status"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    progress=float(row["progress"]),
                )
                for row in rows
            ]

    def list_jobs(self) -> list[JobRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT job_id, book_id, status, created_at, updated_at, progress FROM jobs ORDER BY created_at DESC"
            ).fetchall()
            return [
                JobRecord(
                    job_id=row["job_id"],
                    book_id=row["book_id"],
                    status=row["status"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    progress=float(row["progress"]),
                )
                for row in rows
            ]

    def load_chunks(self, job_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT job_id, chapter_id, chunk_index, text_hash, output_path, state, error
                FROM chunks
                WHERE job_id = ?
                ORDER BY chapter_id, chunk_index
                """,
                (job_id,),
            ).fetchall()

    def record_artifact(self, job_id: str, kind: str, path: str, checksum: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO artifacts(job_id, kind, path, checksum, created_at) VALUES (?, ?, ?, ?, ?)",
                (job_id, kind, path, checksum, utc_now_iso()),
            )
            conn.commit()

    def load_last_non_terminal_job_id(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT job_id FROM jobs
                WHERE status NOT IN ('COMPLETED', 'FAILED', 'CANCELED')
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()
            if row:
                return str(row["job_id"])
            return None
