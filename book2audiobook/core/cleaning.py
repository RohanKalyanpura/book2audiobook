from __future__ import annotations

import re
from collections import Counter


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def repair_hyphenation(text: str) -> str:
    return re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)


def strip_repeating_headers_footers(page_texts: list[str], threshold: float = 0.7) -> list[str]:
    if not page_texts:
        return page_texts

    top_lines: list[str] = []
    bottom_lines: list[str] = []
    for page in page_texts:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        if not lines:
            continue
        top_lines.append(lines[0])
        bottom_lines.append(lines[-1])

    page_count = max(len(page_texts), 1)
    top_counter = Counter(top_lines)
    bottom_counter = Counter(bottom_lines)

    blocked = {
        line
        for line, count in list(top_counter.items()) + list(bottom_counter.items())
        if count / page_count >= threshold
    }

    cleaned: list[str] = []
    for page in page_texts:
        lines = [line for line in page.splitlines() if line.strip()]
        lines = [line for line in lines if line.strip() not in blocked]
        cleaned.append("\n".join(lines).strip())
    return cleaned


def clean_text(text: str) -> str:
    text = repair_hyphenation(text)
    text = normalize_whitespace(text)
    return text
