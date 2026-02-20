from __future__ import annotations

import os
import time
from pathlib import Path

import keyring
from openai import OpenAI

SERVICE_NAME = "Book2Audiobook"
ACCOUNT_NAME = "openai_api_key"


class OpenAIBackend:
    def __init__(self, config: dict):
        self.config = config
        self.client = OpenAI(api_key=self._api_key())
        cloud_cfg = self.config.get("openai", {})
        self.model = cloud_cfg.get("model", "gpt-4o-mini-tts")
        self._voices = cloud_cfg.get("voices", ["alloy", "verse", "sage", "nova"])
        self._max_chars = int(cloud_cfg.get("max_chars", 3500))

    def list_voices(self) -> list[str]:
        return list(self._voices)

    def max_chars(self) -> int:
        return self._max_chars

    def synthesize_to_file(self, text: str, voice: str, speed: float, out_path: Path, **kwargs) -> None:
        retries = int(self.config.get("openai", {}).get("retries", 4))
        delay = 1.0
        last_err: Exception | None = None

        for _ in range(retries):
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with self.client.audio.speech.with_streaming_response.create(
                    model=self.model,
                    voice=voice,
                    input=text,
                    speed=speed,
                    response_format="wav",
                ) as response:
                    response.stream_to_file(str(out_path))
                return
            except Exception as exc:  # pragma: no cover
                last_err = exc
                time.sleep(delay)
                delay *= 2

        raise RuntimeError(f"OpenAI speech generation failed after retries: {last_err}")

    @staticmethod
    def _api_key() -> str:
        env = os.getenv("OPENAI_API_KEY")
        if env:
            return env
        saved = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
        if saved:
            return saved
        raise RuntimeError("OPENAI_API_KEY missing. Set env var or save key in app settings.")


def save_openai_api_key(api_key: str) -> None:
    keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, api_key)


def clear_openai_api_key() -> None:
    try:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
    except keyring.errors.PasswordDeleteError:
        pass
