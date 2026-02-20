from __future__ import annotations

import re
import uuid
from pathlib import Path

from book2audiobook import BookMetadata, Chapter
from book2audiobook.core.cleaning import clean_text


def parse_txt(path: Path, marker_regex: str | None = None, split_chars: int = 12000) -> tuple[BookMetadata, list[Chapter]]:
    text = clean_text(path.read_text(encoding="utf-8", errors="ignore"))

    chapters: list[tuple[str, str]] = []
    if marker_regex:
        pattern = re.compile(marker_regex, re.MULTILINE)
        parts = pattern.split(text)
        headers = pattern.findall(text)
        for i, body in enumerate(parts):
            if not body.strip():
                continue
            title = headers[i - 1] if i > 0 and i - 1 < len(headers) else f"Chapter {len(chapters) + 1}"
            chapters.append((str(title).strip(), body.strip()))
    else:
        for i in range(0, len(text), split_chars):
            section = text[i : i + split_chars].strip()
            if section:
                chapters.append((f"Chapter {len(chapters) + 1}", section))

    chapter_objs: list[Chapter] = []
    for idx, (title, body) in enumerate(chapters):
        chapter_objs.append(
            Chapter(
                id=uuid.uuid4().hex,
                title=title,
                text=body,
                include=True,
                order_index=idx,
                preview=body[:180],
            )
        )

    metadata = BookMetadata(
        title=path.stem,
        author="Unknown",
        cover_image_path=None,
        source_path=path,
        source_type="txt",
    )
    return metadata, chapter_objs
