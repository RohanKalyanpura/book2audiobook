from __future__ import annotations

import uuid
from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub

from book2audiobook import BookMetadata, Chapter


def parse_epub(path: Path) -> tuple[BookMetadata, list[Chapter]]:
    book = epub.read_epub(str(path))
    title = str(book.get_metadata("DC", "title")[0][0]) if book.get_metadata("DC", "title") else path.stem
    author = str(book.get_metadata("DC", "creator")[0][0]) if book.get_metadata("DC", "creator") else "Unknown"

    cover_path = None
    for item in book.get_items():
        if item.get_type() == 10 and "cover" in item.get_name().lower():
            out = path.parent / f"{path.stem}_cover.jpg"
            out.write_bytes(item.get_content())
            cover_path = out
            break

    chapters: list[Chapter] = []
    order = 0
    for item in book.get_items_of_type(9):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        heading = soup.find(["h1", "h2", "h3"])
        text = soup.get_text(" ", strip=True)
        if not text:
            continue
        chapter_title = heading.get_text(strip=True) if heading else f"Chapter {order + 1}"
        chapters.append(
            Chapter(
                id=uuid.uuid4().hex,
                title=chapter_title,
                text=text,
                include=True,
                order_index=order,
                preview=text[:180],
            )
        )
        order += 1

    metadata = BookMetadata(
        title=title,
        author=author,
        cover_image_path=cover_path,
        source_path=path,
        source_type="epub",
    )
    return metadata, chapters
