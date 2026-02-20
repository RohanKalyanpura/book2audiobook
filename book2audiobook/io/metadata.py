from __future__ import annotations

from pathlib import Path

from book2audiobook import BookMetadata, Chapter
from book2audiobook.io.epub_parser import parse_epub
from book2audiobook.io.pdf_parser import parse_pdf
from book2audiobook.io.txt_parser import parse_txt


def parse_book(path: Path, txt_marker_regex: str | None = None) -> tuple[BookMetadata, list[Chapter]]:
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return parse_epub(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".txt":
        return parse_txt(path, marker_regex=txt_marker_regex)
    raise ValueError(f"Unsupported file type: {suffix}")
