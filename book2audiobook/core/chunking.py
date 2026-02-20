from __future__ import annotations

import re

SENTENCE_REGEX = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = SENTENCE_REGEX.split(text)
    return [p.strip() for p in parts if p.strip()]


def hard_split(text: str, hard_max_chars: int) -> list[str]:
    out: list[str] = []
    cursor = 0
    while cursor < len(text):
        out.append(text[cursor : cursor + hard_max_chars].strip())
        cursor += hard_max_chars
    return [c for c in out if c]


def backend_chunk_target(hard_max_chars: int, base_target: int = 1400) -> int:
    return min(hard_max_chars, max(base_target, int(hard_max_chars * 0.9)))


def chunk_text(text: str, target_chars: int, hard_max_chars: int) -> list[str]:
    if len(text) <= hard_max_chars:
        return [text.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in split_sentences(text):
        s_len = len(sentence)
        if s_len > hard_max_chars:
            if current:
                chunks.append("\n".join(current).strip())
                current = []
                current_len = 0
            chunks.extend(hard_split(sentence, hard_max_chars))
            continue

        if current_len + s_len + 1 > target_chars and current:
            chunks.append("\n".join(current).strip())
            current = [sentence]
            current_len = s_len
        else:
            current.append(sentence)
            current_len += s_len + 1

    if current:
        chunks.append("\n".join(current).strip())

    final: list[str] = []
    for chunk in chunks:
        if len(chunk) > hard_max_chars:
            final.extend(hard_split(chunk, hard_max_chars))
        else:
            final.append(chunk)
    return [c for c in final if c]
