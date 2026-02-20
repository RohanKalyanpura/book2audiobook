from __future__ import annotations

import re
import uuid
from pathlib import Path

import fitz
import pdfplumber

from book2audiobook import BookMetadata, Chapter
from book2audiobook.core.cleaning import clean_text, strip_repeating_headers_footers

CHAPTER_RE = re.compile(r"^(chapter|part|section)\s+\w+", re.IGNORECASE)


def _extract_with_pymupdf(path: Path) -> list[str]:
    pages: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            pages.append(page.get_text("text"))
    return pages


def _extract_with_pdfplumber(path: Path) -> list[str]:
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return pages


def _chapterize(text: str) -> list[tuple[str, str]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    chapters: list[tuple[str, list[str]]] = []
    current_title = "Introduction"
    current_lines: list[str] = []

    for line in lines:
        if CHAPTER_RE.match(line) and len(line) < 100:
            if current_lines:
                chapters.append((current_title, current_lines))
            current_title = line
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        chapters.append((current_title, current_lines))

    if len(chapters) <= 1:
        chunk_size = max(len(lines) // 10, 120)
        out: list[tuple[str, str]] = []
        for idx in range(0, len(lines), chunk_size):
            chunk_lines = lines[idx : idx + chunk_size]
            out.append((f"Chapter {len(out) + 1}", "\n".join(chunk_lines)))
        return out

    return [(title, "\n".join(lines_)) for title, lines_ in chapters]


def parse_pdf(path: Path) -> tuple[BookMetadata, list[Chapter]]:
    pages = _extract_with_pymupdf(path)
    joined = "\n\n".join(pages).strip()
    if len(joined) < 500:
        pages = _extract_with_pdfplumber(path)

    pages = strip_repeating_headers_footers(pages)
    text = clean_text("\n\n".join(pages))
    chapter_parts = _chapterize(text)

    chapters: list[Chapter] = []
    for idx, (title, chunk_text) in enumerate(chapter_parts):
        chapters.append(
            Chapter(
                id=uuid.uuid4().hex,
                title=title,
                text=chunk_text,
                include=True,
                order_index=idx,
                preview=chunk_text[:180],
            )
        )

    metadata = BookMetadata(
        title=path.stem,
        author="Unknown",
        cover_image_path=None,
        source_path=path,
        source_type="pdf",
    )
    return metadata, chapters
