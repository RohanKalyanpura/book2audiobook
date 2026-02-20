from __future__ import annotations

import hashlib
import json
from pathlib import Path


def compute_cache_key(
    *,
    text: str,
    backend: str,
    voice: str,
    speed: float,
    prosody: float | None,
    pause_strength: float | None,
) -> str:
    payload = {
        "text": text,
        "backend": backend,
        "voice": voice,
        "speed": speed,
        "prosody": prosody,
        "pause_strength": pause_strength,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def cache_path(cache_dir: Path, cache_key: str, extension: str = "wav") -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{cache_key}.{extension}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
