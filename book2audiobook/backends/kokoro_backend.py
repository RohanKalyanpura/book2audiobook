from __future__ import annotations

from array import array
import hashlib
import os
import sys
from types import SimpleNamespace
import urllib.error
import urllib.request
import wave
import warnings
from pathlib import Path
from typing import Any

NATIVE_DROPIN_PLATFORMS = {"darwin", "win32"}
KOKORO_VOICES_FILENAME = "voices.txt"
MODEL_HELPER_FILENAMES = {KOKORO_VOICES_FILENAME, "voices.json"}
MODEL_FILE_EXTENSIONS = {".bin", ".onnx", ".pth", ".pt", ".ckpt", ".safetensors"}
NON_MODEL_EXTENSIONS = {".txt", ".json", ".md", ".yaml", ".yml", ".ini", ".cfg", ".csv"}
VOICE_FILE_EXTENSIONS = {".pt"}
DEFAULT_KOKORO_MODEL_FILENAME = "kokoro-v1_0.pth"
DEFAULT_KOKORO_VOICES = ["af_bella", "af_nicole"]
KOKORO_SAMPLE_RATE_HZ = 24000
KOKORO_LEGACY_DEFAULT_MAX_CHARS = 2200
KOKORO_MODERN_DEFAULT_MAX_CHARS = 12000
KOKORO_MODEL_REPO_ID = "hexgrad/Kokoro-82M"
KOKORO_MODEL_CONFIG_FILENAME = "config.json"
GPU_PREFERENCE_VALUES = {"auto", "discrete", "integrated"}
DEVICE_VALUES = {"auto", "cpu", "cuda", "mps", "dml"}
RUNTIME_PREFERENCE_VALUES = {"modern", "legacy"}
DEFAULT_RUNTIME_PREFERENCE = "modern"
THREAD_ENV_VARS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
DISCRETE_GPU_MARKERS = (
    "nvidia",
    "geforce",
    "rtx",
    "gtx",
    "quadro",
    "tesla",
    "radeon rx",
    "radeon pro",
    "arc ",
    "arc)",
)
INTEGRATED_GPU_MARKERS = (
    "intel",
    "uhd",
    "iris",
    "integrated",
    "radeon(tm) graphics",
    "vega ",
)


def resolve_kokoro_model_dir(app_data: Path) -> Path:
    if sys.platform not in NATIVE_DROPIN_PLATFORMS:
        return app_data / "models" / "kokoro-82m"

    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        if sys.platform == "darwin":
            app_bundle = _find_macos_app_bundle(executable)
            if app_bundle is not None:
                return app_bundle.parent / "model"
        return executable.parent / "model"

    return Path(__file__).resolve().parents[2] / "model"


def _find_macos_app_bundle(executable: Path) -> Path | None:
    for parent in executable.parents:
        if parent.suffix.lower() == ".app":
            return parent
    return None


def normalize_voice_names(raw_voices: list[str] | None) -> list[str]:
    voices: list[str] = []
    seen: set[str] = set()
    for entry in raw_voices or []:
        for part in str(entry).replace("\n", ",").split(","):
            name = part.strip()
            if not name:
                continue
            lower = name.lower()
            if lower in seen:
                continue
            seen.add(lower)
            voices.append(name)
    return voices


def load_kokoro_voices_file(model_dir: Path) -> list[str]:
    path = model_dir / KOKORO_VOICES_FILENAME
    if not path.exists() or not path.is_file():
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return normalize_voice_names([content])


def save_kokoro_voices_file(model_dir: Path, voices: list[str]) -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    cleaned = normalize_voice_names(voices)
    payload = "\n".join(cleaned)
    if payload:
        payload += "\n"
    target = model_dir / KOKORO_VOICES_FILENAME
    target.write_text(payload, encoding="utf-8")
    return target


class KokoroBackend:
    _warning_filter_applied = False
    _compat_shim_applied = False
    _torch_thread_policy_applied: tuple[int, int] | None = None

    def __init__(
        self,
        model_dir: Path,
        config: dict,
        *,
        voices: list[str] | None = None,
        model_filename: str | None = None,
    ):
        self.model_dir = model_dir
        self.config = config
        model_cfg = config.get("kokoro", {})
        cfg_voices = normalize_voice_names(model_cfg.get("voices", DEFAULT_KOKORO_VOICES))
        explicit_voices = normalize_voice_names(voices)
        file_voices = [] if explicit_voices else load_kokoro_voices_file(self.model_dir)
        discovered_voices = [] if (explicit_voices or file_voices) else self._discover_local_voice_files()
        self._voices = explicit_voices or file_voices or discovered_voices or cfg_voices or list(DEFAULT_KOKORO_VOICES)

        configured_name = str(model_filename or model_cfg.get("model_filename", DEFAULT_KOKORO_MODEL_FILENAME)).strip()
        self._model_filename = configured_name or DEFAULT_KOKORO_MODEL_FILENAME
        self._legacy_engine: Any | None = None
        self._legacy_model_path: str | None = None
        self._modern_model: Any | None = None
        self._modern_pipeline: Any | None = None
        self._modern_model_path: str | None = None
        self._modern_voice_cache: dict[str, Any] = {}
        self._has_modern_runtime_cache: bool | None = None
        self._has_legacy_runtime_cache: bool | None = None
        self._modern_lang_code = "a"

    def list_voices(self) -> list[str]:
        return list(self._voices)

    def max_chars(self) -> int:
        configured = self._coerce_positive_int(
            self.config.get("kokoro", {}).get("max_chars", KOKORO_LEGACY_DEFAULT_MAX_CHARS),
            default=KOKORO_LEGACY_DEFAULT_MAX_CHARS,
        )
        if configured != KOKORO_LEGACY_DEFAULT_MAX_CHARS:
            return configured

        if self._has_modern_runtime():
            modern_default = self._coerce_positive_int(
                self.config.get("kokoro", {}).get("modern_max_chars", KOKORO_MODERN_DEFAULT_MAX_CHARS),
                default=KOKORO_MODERN_DEFAULT_MAX_CHARS,
            )
            return max(KOKORO_LEGACY_DEFAULT_MAX_CHARS, modern_default)

        return configured

    def ensure_model(self) -> Path:
        model_cfg = self.config.get("kokoro", {})
        url = model_cfg.get("model_url")
        checksum = model_cfg.get("model_sha256")
        filename = self._model_filename
        timeout_seconds = float(model_cfg.get("download_timeout_seconds", 60))
        target = self.model_dir / filename

        if self._requires_dropin_model():
            return self._ensure_dropin_model(target, checksum)

        self.model_dir.mkdir(parents=True, exist_ok=True)

        if target.exists():
            if not checksum:
                return target
            if self._sha256(target) == checksum:
                return target

        if not url or self._is_placeholder_url(url):
            raise RuntimeError(
                "Kokoro model URL is not configured. Set `kokoro.model_url` to a valid downloadable model URL."
            )

        tmp = target.with_suffix(".download")
        req = urllib.request.Request(url, headers={"User-Agent": "Book2Audiobook/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response, tmp.open("wb") as out:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
        except urllib.error.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(
                f"Kokoro model download failed with HTTP {exc.code} from {url}. "
                "Update `kokoro.model_url` in config."
            ) from exc
        except urllib.error.URLError as exc:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(
                f"Kokoro model download failed for {url}: {exc.reason}. "
                "Check network access or update `kokoro.model_url`."
            ) from exc
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        if checksum and self._sha256(tmp) != checksum:
            tmp.unlink(missing_ok=True)
            raise RuntimeError("Kokoro model checksum verification failed")
        os.replace(tmp, target)
        return target

    def synthesize_to_file(self, text: str, voice: str, speed: float, out_path: Path, **kwargs) -> None:
        model_file = self.ensure_model()

        self._suppress_nonfatal_urllib3_warnings()
        self._apply_python39_torch_compiler_shim()

        runtime_preference = self._runtime_preference()
        requested_device = self._requested_device_mode()
        runtime_order = self._runtime_order(runtime_preference)
        legacy_exc: Exception | None = None
        modern_exc: Exception | None = None

        for runtime_name in runtime_order:
            if runtime_name == "modern":
                try:
                    from kokoro import KModel, KPipeline  # type: ignore
                except Exception as exc:
                    modern_exc = exc
                    continue
                try:
                    device_label, device_target = self._resolve_modern_device()
                    self._apply_cpu_threading_policy(device_label=device_label)
                    self._synthesize_with_modern_runtime(
                        KModel=KModel,
                        KPipeline=KPipeline,
                        model_file=model_file,
                        text=text,
                        voice=voice,
                        speed=speed,
                        out_path=out_path,
                        resolved_device=(device_label, device_target),
                    )
                    return
                except Exception as exc:
                    modern_exc = exc
                    if requested_device not in {"auto", "cpu"}:
                        raise
                    continue

            try:
                from kokoro import KokoroTTS  # type: ignore
            except Exception as exc:
                legacy_exc = exc
                continue
            try:
                self._apply_cpu_threading_policy(device_label="cpu")
                self._synthesize_with_legacy_runtime(
                    KokoroTTS=KokoroTTS,
                    model_file=model_file,
                    text=text,
                    voice=voice,
                    speed=speed,
                    out_path=out_path,
                )
                return
            except Exception as exc:
                legacy_exc = exc
                continue

        raise RuntimeError(
            "Kokoro runtime is installed but not usable. "
            f"Tried runtimes in order {runtime_order!r}. "
            "Legacy API (`KokoroTTS`) and modern API (`KPipeline`/`KModel`) both failed. "
            f"Legacy error: {legacy_exc!r}. Modern error: {modern_exc!r}. "
            "Install a compatible Kokoro runtime in this venv and restart the app. "
            "If you are on Python 3.9 and still see `typing.Self` errors, upgrade to Python 3.10+ "
            "or use older torch/transformers versions compatible with Python 3.9."
        ) from (modern_exc or legacy_exc)

    def _synthesize_with_legacy_runtime(
        self,
        *,
        KokoroTTS: Any,
        model_file: Path,
        text: str,
        voice: str,
        speed: float,
        out_path: Path,
    ) -> None:
        model_path = str(model_file)
        if self._legacy_engine is None or self._legacy_model_path != model_path:
            self._legacy_engine = KokoroTTS(model_path=model_path)
            self._legacy_model_path = model_path
        audio = self._legacy_engine.synthesize(text=text, voice=voice, speed=speed)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("wb") as handle:
            handle.write(audio)

    def _synthesize_with_modern_runtime(
        self,
        *,
        KModel: Any,
        KPipeline: Any,
        model_file: Path,
        text: str,
        voice: str,
        speed: float,
        out_path: Path,
        resolved_device: tuple[str, Any] | None = None,
    ) -> None:
        model, pipeline = self._get_or_create_modern_pipeline(
            KModel=KModel,
            KPipeline=KPipeline,
            model_file=model_file,
            resolved_device=resolved_device,
        )
        resolved_voice = self._resolve_modern_voice(voice)
        del model
        self._prime_modern_voice_cache(
            pipeline=pipeline,
            resolved_voice=resolved_voice,
        )
        chunks = pipeline(text, voice=resolved_voice, speed=speed, split_pattern=r"\n+")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        wrote_audio = False
        with wave.open(str(out_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(KOKORO_SAMPLE_RATE_HZ)
            for result in chunks:
                audio = getattr(result, "audio", None)
                if audio is None:
                    continue
                pcm = self._tensor_audio_to_pcm16(audio)
                if not pcm:
                    continue
                wav_file.writeframes(pcm)
                wrote_audio = True

        if not wrote_audio:
            raise RuntimeError("Kokoro runtime returned no audio for the provided text/voice.")

    def _get_or_create_modern_pipeline(
        self,
        *,
        KModel: Any,
        KPipeline: Any,
        model_file: Path,
        resolved_device: tuple[str, Any] | None = None,
    ) -> tuple[Any, Any]:
        model_path = str(model_file)
        if self._modern_model is not None and self._modern_pipeline is not None and self._modern_model_path == model_path:
            return self._modern_model, self._modern_pipeline

        config_path = self._resolve_modern_config_path(model_file)
        try:
            if config_path is not None:
                model = KModel(config=str(config_path), model=str(model_file))
            else:
                model = KModel(model=str(model_file))
        except Exception as exc:
            if KOKORO_MODEL_CONFIG_FILENAME in str(exc).lower() or "huggingface.co" in str(exc).lower():
                raise RuntimeError(
                    "Kokoro modern runtime needs `config.json` alongside the model file for offline use. "
                    f"Expected at `{model_file.with_name(KOKORO_MODEL_CONFIG_FILENAME)}`. "
                    "Add that file or run once with network access so it can be cached."
                ) from exc
            raise

        if resolved_device is None:
            device_label, device_target = self._resolve_modern_device()
        else:
            device_label, device_target = resolved_device
        try:
            if device_label != "cpu" and hasattr(model, "to"):
                model = model.to(device_target)
            if hasattr(model, "eval"):
                model = model.eval()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialize Kokoro modern runtime on device `{device_label}`. "
                "Use `kokoro.device = \"cpu\"` in config to force CPU if needed."
            ) from exc

        pipeline = KPipeline(lang_code=self._modern_lang_code, model=model)
        self._modern_model = model
        self._modern_pipeline = pipeline
        self._modern_model_path = model_path
        self._modern_voice_cache.clear()
        return model, pipeline

    def _resolve_modern_config_path(self, model_file: Path) -> Path | None:
        local_config = model_file.with_name(KOKORO_MODEL_CONFIG_FILENAME)
        if local_config.exists():
            return local_config

        try:
            from huggingface_hub import hf_hub_download

            cached = hf_hub_download(
                repo_id=KOKORO_MODEL_REPO_ID,
                filename=KOKORO_MODEL_CONFIG_FILENAME,
                local_files_only=True,
            )
        except Exception:
            return None

        cached_path = Path(cached)
        return cached_path if cached_path.exists() else None

    def _prime_modern_voice_cache(self, *, pipeline: Any, resolved_voice: str) -> None:
        cache_key = f"{self._modern_model_path or ''}:{resolved_voice}"
        if cache_key in self._modern_voice_cache:
            return

        load_voice = getattr(pipeline, "load_voice", None)
        if not callable(load_voice):
            return

        try:
            load_voice(resolved_voice)
        except Exception:
            return

        self._modern_voice_cache[cache_key] = True

    def _resolve_modern_voice(self, voice: str) -> str:
        candidate = Path(voice).expanduser()
        if candidate.suffix.lower() != ".pt":
            local_id_voice = self.model_dir / f"{voice}.pt"
            if local_id_voice.exists():
                return str(local_id_voice)
            return voice
        if candidate.is_absolute():
            return str(candidate)
        local = self.model_dir / candidate
        if local.exists():
            return str(local)
        return voice

    def diagnose_runtime(self) -> dict[str, Any]:
        runtime_preference = self._runtime_preference()
        requested_device = self._requested_device_mode()
        has_modern = self._has_modern_runtime()
        has_legacy = self._has_legacy_runtime()
        if not has_modern and not has_legacy:
            raise RuntimeError(
                "Kokoro runtime is not installed or not importable. "
                "Install a runtime exposing `KPipeline`/`KModel` or `KokoroTTS`."
            )

        runtime_order = self._runtime_order(runtime_preference)
        selected_runtime = next(
            (
                runtime
                for runtime in runtime_order
                if (runtime == "modern" and has_modern) or (runtime == "legacy" and has_legacy)
            ),
            runtime_order[0],
        )

        if selected_runtime == "modern":
            device_label, _ = self._resolve_modern_device()
            fallback_to_cpu = device_label == "cpu" and requested_device != "cpu"
            if fallback_to_cpu:
                if requested_device == "auto":
                    reason = "No GPU/Metal/DirectML backend is available; falling back to CPU."
                else:
                    reason = f"Requested `{requested_device}` device is unavailable; falling back to CPU."
            else:
                reason = f"Using modern runtime on `{device_label}`."
            return {
                "runtime": "modern",
                "device": device_label,
                "is_gpu_fallback_to_cpu": fallback_to_cpu,
                "reason": reason,
                "runtime_preference": runtime_preference,
                "requested_device": requested_device,
                "modern_available": has_modern,
                "legacy_available": has_legacy,
            }

        fallback_to_cpu = runtime_preference == "modern" and requested_device != "cpu"
        if fallback_to_cpu:
            if has_modern:
                reason = "Modern runtime could not be selected; using legacy runtime on CPU."
            else:
                reason = "Modern runtime is unavailable; using legacy runtime on CPU."
        else:
            reason = "Using legacy runtime on CPU."
        return {
            "runtime": "legacy",
            "device": "cpu",
            "is_gpu_fallback_to_cpu": fallback_to_cpu,
            "reason": reason,
            "runtime_preference": runtime_preference,
            "requested_device": requested_device,
            "modern_available": has_modern,
            "legacy_available": has_legacy,
        }

    def _discover_local_voice_files(self) -> list[str]:
        if not self.model_dir.exists() or not self.model_dir.is_dir():
            return []
        discovered: list[str] = []
        for path in sorted(self.model_dir.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.suffix.lower() in VOICE_FILE_EXTENSIONS:
                discovered.append(path.name)
        return normalize_voice_names(discovered)

    @staticmethod
    def _tensor_audio_to_pcm16(audio: Any) -> bytes:
        values = audio
        try:
            if hasattr(values, "detach"):
                values = values.detach()
            if hasattr(values, "cpu"):
                values = values.cpu()
            if hasattr(values, "flatten"):
                values = values.flatten()
            if hasattr(values, "float") and hasattr(values, "clamp") and hasattr(values, "numpy"):
                values = values.float().clamp(-1.0, 1.0)
                values = (values * 32767.0).round()
                if hasattr(values, "short"):
                    values = values.short()
                return values.numpy().tobytes()
        except Exception:
            values = audio
            if hasattr(values, "detach"):
                values = values.detach()
            if hasattr(values, "cpu"):
                values = values.cpu()
            if hasattr(values, "flatten"):
                values = values.flatten()

        if hasattr(values, "tolist"):
            samples = values.tolist()
        else:
            samples = values
        if not isinstance(samples, list):
            samples = [samples]

        pcm = array("h")
        for sample in samples:
            value = float(sample)
            value = max(-1.0, min(1.0, value))
            pcm.append(int(round(value * 32767.0)))
        return pcm.tobytes()

    @staticmethod
    def _suppress_nonfatal_urllib3_warnings() -> None:
        if KokoroBackend._warning_filter_applied:
            return
        warnings.filterwarnings(
            "ignore",
            message=r"urllib3 v2 only supports OpenSSL 1\.1\.1\+",
        )
        warnings.filterwarnings(
            "ignore",
            message=r"dropout option adds dropout after all but last recurrent layer.*",
        )
        warnings.filterwarnings(
            "ignore",
            message=r"`torch\.nn\.utils\.weight_norm` is deprecated.*",
        )
        KokoroBackend._warning_filter_applied = True

    def _has_modern_runtime(self) -> bool:
        if self._has_modern_runtime_cache is not None:
            return self._has_modern_runtime_cache
        self._apply_python39_torch_compiler_shim()
        try:
            from kokoro import KModel, KPipeline  # type: ignore
        except Exception:
            self._has_modern_runtime_cache = False
        else:
            self._has_modern_runtime_cache = bool(KModel and KPipeline)
        return self._has_modern_runtime_cache

    def _has_legacy_runtime(self) -> bool:
        if self._has_legacy_runtime_cache is not None:
            return self._has_legacy_runtime_cache
        try:
            from kokoro import KokoroTTS  # type: ignore
        except Exception:
            self._has_legacy_runtime_cache = False
        else:
            self._has_legacy_runtime_cache = bool(KokoroTTS)
        return self._has_legacy_runtime_cache

    def _runtime_preference(self) -> str:
        raw = str(self.config.get("kokoro", {}).get("runtime_preference", DEFAULT_RUNTIME_PREFERENCE)).strip().lower()
        if raw in RUNTIME_PREFERENCE_VALUES:
            return raw
        return DEFAULT_RUNTIME_PREFERENCE

    @staticmethod
    def _runtime_order(runtime_preference: str) -> tuple[str, str]:
        if runtime_preference == "legacy":
            return ("legacy", "modern")
        return ("modern", "legacy")

    def _requested_device_mode(self) -> str:
        raw_device = str(self.config.get("kokoro", {}).get("device", "auto")).strip().lower()
        requested, _ = self._parse_device_request(raw_device)
        return requested

    @staticmethod
    def _coerce_positive_int(value: Any, *, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    def _resolve_cpu_thread_count(self) -> tuple[int, bool]:
        raw = self.config.get("kokoro", {}).get("cpu_threads", "auto")
        text = str(raw).strip().lower()
        if text in {"", "auto"}:
            return min(4, max(1, (os.cpu_count() or 2) // 2)), True
        try:
            parsed = int(text)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Invalid `kokoro.cpu_threads` value `{raw}`. Use `auto` or a positive integer."
            ) from exc
        if parsed <= 0:
            raise RuntimeError(f"Invalid `kokoro.cpu_threads` value `{raw}`. Use a positive integer.")
        return parsed, False

    def _apply_cpu_threading_policy(self, *, device_label: str) -> None:
        if device_label != "cpu":
            return

        thread_count, from_auto = self._resolve_cpu_thread_count()
        value = str(thread_count)
        resolved_thread_count = thread_count
        for env_name in THREAD_ENV_VARS:
            existing = os.environ.get(env_name)
            if from_auto and existing:
                try:
                    parsed = int(existing)
                except (TypeError, ValueError):
                    parsed = 0
                if parsed > 0 and resolved_thread_count == thread_count:
                    resolved_thread_count = parsed
                continue
            os.environ[env_name] = value

        try:
            import torch  # type: ignore
        except Exception:
            return

        try:
            torch.set_num_threads(resolved_thread_count)
        except Exception:
            pass

        interop_threads = max(1, resolved_thread_count // 2)
        if KokoroBackend._torch_thread_policy_applied == (resolved_thread_count, interop_threads):
            return
        try:
            torch.set_num_interop_threads(interop_threads)
        except Exception:
            return
        KokoroBackend._torch_thread_policy_applied = (resolved_thread_count, interop_threads)

    def _resolve_modern_device(self) -> tuple[str, Any]:
        kokoro_cfg = self.config.get("kokoro", {})
        raw_device = str(kokoro_cfg.get("device", "auto")).strip().lower()
        requested, inline_index = self._parse_device_request(raw_device)
        configured_index = self._parse_optional_non_negative_int(kokoro_cfg.get("device_index"))
        device_index = inline_index if inline_index is not None else configured_index
        gpu_preference = str(kokoro_cfg.get("gpu_preference", "discrete")).strip().lower()
        if gpu_preference not in GPU_PREFERENCE_VALUES:
            gpu_preference = "discrete"

        try:
            import torch  # type: ignore
        except Exception:
            if requested not in {"auto", "cpu"}:
                raise RuntimeError(
                    f"Kokoro device is set to `{requested}`, but PyTorch is unavailable in this environment."
                )
            return "cpu", "cpu"

        cuda_available = bool(hasattr(torch, "cuda") and torch.cuda.is_available())
        cuda_count = int(torch.cuda.device_count()) if hasattr(torch, "cuda") and hasattr(torch.cuda, "device_count") else 0
        mps_available = bool(hasattr(torch.backends, "mps") and torch.backends.mps.is_available())

        if requested == "cpu":
            return "cpu", "cpu"
        if requested == "cuda":
            return self._resolve_cuda_device(cuda_available=cuda_available, cuda_count=cuda_count, device_index=device_index)
        if requested == "mps":
            if not mps_available:
                raise RuntimeError("Kokoro device is set to `mps`, but Apple Metal (MPS) is not available.")
            return "mps", "mps"
        if requested == "dml":
            dml_device = self._resolve_dml_device(device_index=device_index, gpu_preference=gpu_preference)
            if dml_device is None:
                raise RuntimeError(
                    "Kokoro device is set to `dml`, but `torch-directml` is not installed or no DirectML adapters were found."
                )
            return dml_device

        if cuda_available:
            return self._resolve_cuda_device(cuda_available=True, cuda_count=cuda_count, device_index=device_index)
        if mps_available:
            return "mps", "mps"

        dml_device = self._resolve_dml_device(
            device_index=device_index,
            gpu_preference=gpu_preference,
            allow_missing=True,
        )
        if dml_device is not None:
            return dml_device
        return "cpu", "cpu"

    @staticmethod
    def _parse_device_request(raw: str) -> tuple[str, int | None]:
        text = raw.strip().lower()
        if text.startswith("cuda:"):
            return "cuda", KokoroBackend._parse_required_non_negative_int(text.split(":", 1)[1], "cuda")
        if text.startswith("dml:"):
            return "dml", KokoroBackend._parse_required_non_negative_int(text.split(":", 1)[1], "dml")
        if text.startswith("mps:"):
            return "mps", KokoroBackend._parse_required_non_negative_int(text.split(":", 1)[1], "mps")
        if text in DEVICE_VALUES:
            return text, None
        return "auto", None

    @staticmethod
    def _parse_required_non_negative_int(value: str, label: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Invalid `{label}` device index `{value}`. Use a non-negative integer.") from exc
        if parsed < 0:
            raise RuntimeError(f"Invalid `{label}` device index `{value}`. Use a non-negative integer.")
        return parsed

    @staticmethod
    def _parse_optional_non_negative_int(value: Any) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = int(text)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Invalid `kokoro.device_index` value `{value}`. Use a non-negative integer.") from exc
        if parsed < 0:
            raise RuntimeError(f"Invalid `kokoro.device_index` value `{value}`. Use a non-negative integer.")
        return parsed

    @staticmethod
    def _resolve_cuda_device(*, cuda_available: bool, cuda_count: int, device_index: int | None) -> tuple[str, str]:
        if not cuda_available:
            raise RuntimeError("Kokoro device is set to `cuda`, but CUDA is not available in this environment.")

        if device_index is None:
            return "cuda", "cuda"

        if cuda_count and device_index >= cuda_count:
            raise RuntimeError(
                f"Requested CUDA device index {device_index}, but only {cuda_count} CUDA device(s) are available."
            )
        label = f"cuda:{device_index}"
        return label, label

    def _resolve_dml_device(
        self,
        *,
        device_index: int | None,
        gpu_preference: str,
        allow_missing: bool = False,
    ) -> tuple[str, Any] | None:
        try:
            import torch_directml  # type: ignore
        except Exception:
            if allow_missing:
                return None
            raise RuntimeError("DirectML support requires `torch-directml` to be installed.")

        device_count = int(getattr(torch_directml, "device_count", lambda: 0)())
        if device_count <= 0:
            if allow_missing:
                return None
            raise RuntimeError("`torch-directml` is installed, but no DirectML adapters were found.")

        if device_index is None:
            selected_index = self._pick_dml_device_index(
                torch_directml=torch_directml,
                device_count=device_count,
                gpu_preference=gpu_preference,
            )
        else:
            selected_index = device_index

        if selected_index < 0 or selected_index >= device_count:
            raise RuntimeError(
                f"Requested DirectML device index {selected_index}, but only {device_count} adapter(s) are available."
            )

        device = torch_directml.device(selected_index)
        return f"dml:{selected_index}", device

    def _pick_dml_device_index(self, *, torch_directml: Any, device_count: int, gpu_preference: str) -> int:
        classified: list[tuple[int, str]] = []
        for idx in range(device_count):
            name = str(getattr(torch_directml, "device_name", lambda _idx: "")(idx)).strip().lower()
            classified.append((idx, self._classify_gpu_name(name)))

        if gpu_preference in {"auto", "discrete"}:
            discrete = [idx for idx, kind in classified if kind == "discrete"]
            if discrete:
                return discrete[0]

        if gpu_preference == "integrated":
            integrated = [idx for idx, kind in classified if kind == "integrated"]
            if integrated:
                return integrated[0]

        if gpu_preference == "discrete":
            non_integrated = [idx for idx, kind in classified if kind != "integrated"]
            if non_integrated:
                return non_integrated[0]

        return 0

    @staticmethod
    def _classify_gpu_name(name: str) -> str:
        if any(marker in name for marker in INTEGRATED_GPU_MARKERS):
            return "integrated"
        if any(marker in name for marker in DISCRETE_GPU_MARKERS):
            return "discrete"
        return "unknown"

    @staticmethod
    def _apply_python39_torch_compiler_shim() -> None:
        if KokoroBackend._compat_shim_applied:
            return
        # Newer torch/transformers paths may trigger torch._dynamo imports that can
        # fail on some Python 3.9 environments due to typing.Self handling.
        if sys.version_info >= (3, 10):
            KokoroBackend._compat_shim_applied = True
            return
        try:
            import torch  # type: ignore
        except Exception:
            return
        compiler = getattr(torch, "compiler", None)
        if compiler is None:
            return
        disable = getattr(compiler, "disable", None)
        if not callable(disable):
            return

        def _no_op_decorator(*args: Any, **kwargs: Any):
            if args and callable(args[0]) and len(args) == 1 and not kwargs:
                return args[0]

            def _decorator(fn: Any) -> Any:
                return fn

            return _decorator

        compiler.disable = _no_op_decorator

        # Avoid importing torch._dynamo in Python 3.9 paths where it can crash.
        if "_dynamo" not in getattr(torch, "__dict__", {}):
            torch._dynamo = SimpleNamespace(allow_in_graph=_no_op_decorator)  # type: ignore[attr-defined]

        # Transformers can trigger heavy auto-docstring machinery during import,
        # which is unnecessary for runtime inference and can trip py3.9 edge cases.
        try:
            import transformers.utils as transformer_utils  # type: ignore
        except Exception:
            return
        transformer_utils.auto_docstring = _no_op_decorator  # type: ignore[attr-defined]
        KokoroBackend._compat_shim_applied = True

    def _ensure_dropin_model(self, target: Path, checksum: str | None) -> Path:
        if self.model_dir.exists() and not self.model_dir.is_dir():
            raise RuntimeError(f"Kokoro model path exists but is not a folder: `{self.model_dir}`.")

        if not self.model_dir.exists():
            try:
                self.model_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                # Read-only install locations can still work if the user created the folder manually.
                pass

        resolved = target
        if not resolved.exists():
            if not self.model_dir.exists() or not self.model_dir.is_dir():
                raise RuntimeError(
                    f"Kokoro model missing. Create a folder named `model` at `{self.model_dir}` "
                    f"and drop the model file inside (recommended name: `{target.name}`)."
                )
            candidates = self._model_candidates()
            if len(candidates) == 1:
                resolved = candidates[0]
            elif len(candidates) > 1:
                names = ", ".join(path.name for path in candidates[:6])
                raise RuntimeError(
                    f"Multiple files found in `{self.model_dir}` ({names}). "
                    f"Keep only one model file or rename the desired file to `{target.name}`."
                )
            else:
                raise RuntimeError(
                    f"Kokoro model missing. Drop the model file into `{self.model_dir}` "
                    f"(recommended name: `{target.name}`)."
                )

        if checksum and self._sha256(resolved) != checksum:
            raise RuntimeError(f"Kokoro model checksum verification failed for `{resolved.name}`.")

        return resolved

    def _model_candidates(self) -> list[Path]:
        files: list[Path] = []
        for path in sorted(self.model_dir.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            name = path.name.lower()
            if name in MODEL_HELPER_FILENAMES:
                continue
            suffix = path.suffix.lower()
            if suffix in MODEL_FILE_EXTENSIONS or suffix not in NON_MODEL_EXTENSIONS:
                files.append(path)
        return files

    @staticmethod
    def _requires_dropin_model() -> bool:
        return sys.platform in NATIVE_DROPIN_PLATFORMS

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _is_placeholder_url(url: str) -> bool:
        return "example.com" in url.strip().lower()
