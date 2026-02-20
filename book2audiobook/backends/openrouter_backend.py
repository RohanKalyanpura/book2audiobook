from __future__ import annotations

import base64
import io
import json
import os
import time
import wave
from pathlib import Path

import keyring
from openai import OpenAI

SERVICE_NAME = "Book2Audiobook"
ACCOUNT_NAME = "openrouter_api_key"


class OpenRouterBackend:
    def __init__(self, config: dict, *, model: str | None = None, voices: list[str] | None = None):
        self.config = config
        router_cfg = self.config.get("openrouter", {})
        self.base_url = router_cfg.get("base_url", "https://openrouter.ai/api/v1")
        configured_model = str(model or router_cfg.get("model", "openai/gpt-audio-mini")).strip()
        self.model = configured_model or "openai/gpt-audio-mini"
        self._voices = list(voices) if voices else router_cfg.get("voices", ["alloy", "verse", "sage", "nova"])
        self._max_chars = int(router_cfg.get("max_chars", 3500))
        self._retries = int(router_cfg.get("retries", 4))
        self._app_name = router_cfg.get("app_name", "Book2Audiobook")
        self._app_url = router_cfg.get("app_url", "")
        self._timeout = float(router_cfg.get("timeout_seconds", 60))
        self._stream_pcm_sample_rate_hz = int(router_cfg.get("stream_pcm_sample_rate_hz", 24000))
        self._preferred_variant_name: str | None = None

        self.client = OpenAI(api_key=self._api_key(), base_url=self.base_url, timeout=self._timeout)

    def list_voices(self) -> list[str]:
        return list(self._voices)

    def max_chars(self) -> int:
        return self._max_chars

    def synthesize_to_file(self, text: str, voice: str, speed: float, out_path: Path, **kwargs) -> None:
        delay = 1.0
        last_err: str | None = None

        headers = {"X-Title": self._app_name}
        if self._app_url:
            headers["HTTP-Referer"] = self._app_url

        variants = self._ordered_request_variants(text=text, voice=voice, speed=speed)
        for _ in range(self._retries):
            for variant_name, variant in variants:
                try:
                    payload: dict = {}
                    if variant["stream"]:
                        stream = self.client.chat.completions.create(
                            model=self.model,
                            messages=variant["messages"],
                            stream=True,
                            extra_headers=headers,
                            extra_body=variant["extra_body"],
                        )
                        for chunk in stream:
                            chunk_payload = chunk.model_dump() if hasattr(chunk, "model_dump") else {}
                            payload = self._merge_chunk_payload(payload, chunk_payload)
                    else:
                        completion = self.client.chat.completions.create(
                            model=self.model,
                            messages=variant["messages"],
                            extra_headers=headers,
                            extra_body=variant["extra_body"],
                        )
                        payload = completion.model_dump() if hasattr(completion, "model_dump") else {}

                    audio_chunks = self._collect_audio_chunks_from_payload(payload)
                    if not audio_chunks:
                        raise RuntimeError(
                            "OpenRouter response did not include audio data. "
                            f"Model `{self.model}` may not support audio output on chat completions."
                        )

                    audio_bytes = self._decode_audio_chunks(audio_chunks)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    self._write_output_audio(
                        out_path=out_path,
                        audio_bytes=audio_bytes,
                        audio_format=variant["audio_format"],
                    )
                    self._preferred_variant_name = variant_name
                    return
                except Exception as exc:  # pragma: no cover
                    last_err = f"{variant_name}: {self._format_error(exc)}"

            if last_err:
                time.sleep(delay)
                delay *= 2

        raise RuntimeError(f"OpenRouter speech generation failed after retries: {last_err or 'unknown error'}")

    @staticmethod
    def _api_key() -> str:
        env = os.getenv("OPENROUTER_API_KEY")
        if env:
            return env
        saved = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
        if saved:
            return saved
        raise RuntimeError("OPENROUTER_API_KEY missing. Set env var or save key in app settings.")

    @staticmethod
    def _extract_audio_b64_chunks(payload: dict, container_key: str) -> list[str]:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return []

        audio_chunks: list[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            container = choice.get(container_key)
            if not isinstance(container, dict):
                continue
            audio = container.get("audio")
            if not isinstance(audio, dict):
                continue
            data = audio.get("data")
            if isinstance(data, str) and data:
                audio_chunks.append(data)
        return audio_chunks

    @staticmethod
    def _extract_audio_b64_from_content_parts(payload: dict) -> list[str]:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return []

        audio_chunks: list[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue

            for part in content:
                if not isinstance(part, dict):
                    continue
                audio = part.get("audio")
                if isinstance(audio, dict):
                    data = audio.get("data")
                    if isinstance(data, str) and data:
                        audio_chunks.append(data)
                        continue

                output_audio = part.get("output_audio")
                if isinstance(output_audio, dict):
                    data = output_audio.get("data")
                    if isinstance(data, str) and data:
                        audio_chunks.append(data)

        return audio_chunks

    @staticmethod
    def _collect_audio_chunks_from_payload(payload: dict) -> list[str]:
        chunks: list[str] = []
        chunks.extend(OpenRouterBackend._extract_audio_b64_chunks(payload, "delta"))
        chunks.extend(OpenRouterBackend._extract_audio_b64_chunks(payload, "message"))
        chunks.extend(OpenRouterBackend._extract_audio_b64_from_content_parts(payload))
        return chunks

    @staticmethod
    def _merge_chunk_payload(base: dict, incoming: dict) -> dict:
        merged = base if isinstance(base, dict) else {}
        choices = incoming.get("choices")
        if not isinstance(choices, list):
            return merged

        if not isinstance(merged.get("choices"), list):
            merged["choices"] = []

        while len(merged["choices"]) < len(choices):
            merged["choices"].append({})

        for idx, incoming_choice in enumerate(choices):
            if not isinstance(incoming_choice, dict):
                continue

            target = merged["choices"][idx]
            if not isinstance(target, dict):
                target = {}
                merged["choices"][idx] = target

            for key in ("delta", "message"):
                container = incoming_choice.get(key)
                if not isinstance(container, dict):
                    continue
                existing = target.get(key)
                if not isinstance(existing, dict):
                    existing = {}
                    target[key] = existing

                audio = container.get("audio")
                if isinstance(audio, dict):
                    existing_audio = existing.get("audio")
                    if not isinstance(existing_audio, dict):
                        existing_audio = {}
                        existing["audio"] = existing_audio
                    data = audio.get("data")
                    if isinstance(data, str) and data:
                        existing_audio["data"] = existing_audio.get("data", "") + data

                content = container.get("content")
                if isinstance(content, list):
                    existing_content = existing.get("content")
                    if not isinstance(existing_content, list):
                        existing_content = []
                        existing["content"] = existing_content
                    existing_content.extend(content)

        return merged

    @staticmethod
    def _decode_audio_chunks(audio_chunks: list[str]) -> bytes:
        audio = bytearray()
        for chunk in audio_chunks:
            if not chunk:
                continue
            try:
                audio.extend(base64.b64decode(chunk, validate=False))
            except Exception:
                audio.clear()
                break

        if audio:
            return bytes(audio)

        merged = "".join(audio_chunks)
        if not merged:
            raise RuntimeError("OpenRouter returned empty audio chunks.")
        return base64.b64decode(merged, validate=False)

    def _write_output_audio(self, out_path: Path, audio_bytes: bytes, audio_format: str) -> None:
        if audio_format == "pcm16":
            wav_bytes = self._pcm16_to_wav(audio_bytes, sample_rate_hz=self._stream_pcm_sample_rate_hz)
            out_path.write_bytes(wav_bytes)
            return
        out_path.write_bytes(audio_bytes)

    @staticmethod
    def _pcm16_to_wav(pcm_bytes: bytes, sample_rate_hz: int) -> bytes:
        if not pcm_bytes:
            return b""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate_hz)
            wav_file.writeframes(pcm_bytes)
        return buffer.getvalue()

    @staticmethod
    def _format_error(exc: Exception) -> str:
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        body = getattr(exc, "body", None)

        if response is not None:
            try:
                body = response.json()
                return OpenRouterBackend._compact_json_error(status_code, body)
            except Exception:
                text = str(getattr(response, "text", "")).strip()
                if text.startswith("<!DOCTYPE html>") or text.startswith("<html"):
                    if status_code:
                        return f"HTTP {status_code} (HTML response). Check OpenRouter endpoint/model compatibility."
                    return "Received HTML error response. Check OpenRouter endpoint/model compatibility."
                snippet = text[:400] if text else str(exc)
                if status_code:
                    return f"HTTP {status_code}: {snippet}"
                return snippet

        if body is not None:
            return OpenRouterBackend._compact_json_error(status_code, body)

        if status_code:
            return f"HTTP {status_code}: {exc}"
        return str(exc)

    @staticmethod
    def _compact_json_error(status_code: int | None, body: object) -> str:
        try:
            encoded = json.dumps(body, ensure_ascii=True)
        except Exception:
            encoded = str(body)
        if len(encoded) > 400:
            encoded = f"{encoded[:400]}..."
        if status_code:
            return f"HTTP {status_code}: {encoded}"
        return encoded

    @staticmethod
    def _request_variants(text: str, voice: str, speed: float) -> list[tuple[str, dict]]:
        audio_cfg_wav = {"voice": voice, "format": "wav"}
        audio_cfg_pcm16 = {"voice": voice, "format": "pcm16"}
        if speed and speed != 1.0:
            audio_cfg_wav["speed"] = speed
            audio_cfg_pcm16["speed"] = speed

        typed_message = OpenRouterBackend._verbatim_messages(text)

        return [
            (
                "typed_non_stream_text_and_audio",
                {
                    "stream": False,
                    "audio_format": "wav",
                    "messages": typed_message,
                    "extra_body": {
                        "modalities": ["text", "audio"],
                        "audio": dict(audio_cfg_wav),
                        "temperature": 0,
                    },
                },
            ),
            (
                "typed_non_stream_audio_only",
                {
                    "stream": False,
                    "audio_format": "wav",
                    "messages": typed_message,
                    "extra_body": {
                        "modalities": ["audio"],
                        "audio": dict(audio_cfg_wav),
                        "temperature": 0,
                    },
                },
            ),
            (
                "typed_stream_text_and_audio",
                {
                    "stream": True,
                    "audio_format": "pcm16",
                    "messages": typed_message,
                    "extra_body": {
                        "modalities": ["text", "audio"],
                        "audio": dict(audio_cfg_pcm16),
                        "temperature": 0,
                    },
                },
            ),
            (
                "typed_stream_audio_only",
                {
                    "stream": True,
                    "audio_format": "pcm16",
                    "messages": typed_message,
                    "extra_body": {
                        "modalities": ["audio"],
                        "audio": dict(audio_cfg_pcm16),
                        "temperature": 0,
                    },
                },
            ),
        ]

    @staticmethod
    def _verbatim_messages(text: str) -> list[dict]:
        instruction = (
            "You are a narration engine. Read the provided text aloud verbatim. "
            "Do not summarize, paraphrase, answer questions, add commentary, translate, "
            "or omit details."
        )
        user_text = f"Read this exactly as written:\n\n{text}"
        return [
            {"role": "system", "content": [{"type": "text", "text": instruction}]},
            {"role": "user", "content": [{"type": "text", "text": user_text}]},
        ]

    def _ordered_request_variants(self, text: str, voice: str, speed: float) -> list[tuple[str, dict]]:
        variants = self._request_variants(text=text, voice=voice, speed=speed)
        if not self._preferred_variant_name:
            return variants

        preferred: list[tuple[str, dict]] = []
        others: list[tuple[str, dict]] = []
        for item in variants:
            if item[0] == self._preferred_variant_name:
                preferred.append(item)
            else:
                others.append(item)
        return preferred + others


def save_openrouter_api_key(api_key: str) -> None:
    keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, api_key)


def clear_openrouter_api_key() -> None:
    try:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
    except keyring.errors.PasswordDeleteError:
        pass
