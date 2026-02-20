from __future__ import annotations

import os
from array import array
import sys
import types
from pathlib import Path

import pytest

from book2audiobook.backends import kokoro_backend
from book2audiobook.backends.kokoro_backend import (
    KokoroBackend,
    load_kokoro_voices_file,
    resolve_kokoro_model_dir,
    save_kokoro_voices_file,
)


def _config(model_filename: str = "kokoro-v1_0.pth", voices: list[str] | None = None) -> dict:
    return {
        "kokoro": {
            "model_filename": model_filename,
            "model_url": "",
            "model_sha256": "",
            "runtime_preference": "modern",
            "device": "auto",
            "device_index": "",
            "gpu_preference": "discrete",
            "cpu_threads": "auto",
            "require_gpu_confirm_on_cpu_fallback": True,
            "voices": voices if voices is not None else ["af_bella", "af_nicole"],
        }
    }


def _fake_torch_module(*, cuda_available: bool, cuda_count: int = 0, mps_available: bool = False):
    return types.SimpleNamespace(
        cuda=types.SimpleNamespace(
            is_available=lambda: cuda_available,
            device_count=lambda: cuda_count,
        ),
        backends=types.SimpleNamespace(
            mps=types.SimpleNamespace(
                is_available=lambda: mps_available,
            )
        ),
    )


def test_resolve_kokoro_model_dir_non_native_platform_uses_app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    monkeypatch.delattr(kokoro_backend.sys, "frozen", raising=False)

    resolved = resolve_kokoro_model_dir(tmp_path)
    assert resolved == tmp_path / "models" / "kokoro-82m"


def test_resolve_kokoro_model_dir_native_non_frozen_uses_repo_model_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "darwin")
    monkeypatch.delattr(kokoro_backend.sys, "frozen", raising=False)

    resolved = resolve_kokoro_model_dir(tmp_path)
    assert resolved == Path(kokoro_backend.__file__).resolve().parents[2] / "model"


def test_ensure_model_native_dropin_accepts_single_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "win32")

    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    actual_model = model_dir / "custom-model.onnx"
    actual_model.write_bytes(b"fake-model-bytes")

    backend = KokoroBackend(model_dir, _config())
    resolved = backend.ensure_model()
    assert resolved == actual_model


def test_ensure_model_native_dropin_requires_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "darwin")

    model_dir = tmp_path / "model"
    backend = KokoroBackend(model_dir, _config())

    with pytest.raises(RuntimeError, match="Kokoro model missing"):
        backend.ensure_model()


def test_ensure_model_native_dropin_rejects_multiple_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "win32")

    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "a.onnx").write_bytes(b"one")
    (model_dir / "b.onnx").write_bytes(b"two")

    backend = KokoroBackend(model_dir, _config())

    with pytest.raises(RuntimeError, match="Multiple files found"):
        backend.ensure_model()


def test_ensure_model_native_dropin_ignores_voices_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "darwin")

    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "voices.txt").write_text("alloy\nverse\n", encoding="utf-8")
    expected_model = model_dir / "kokoro.pth"
    expected_model.write_bytes(b"weights")

    backend = KokoroBackend(model_dir, _config())
    assert backend.ensure_model() == expected_model


def test_load_and_save_kokoro_voices_file_roundtrip(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    saved_path = save_kokoro_voices_file(model_dir, ["af_bella", "af_nicole", "af_bella"])
    assert saved_path.exists()
    assert load_kokoro_voices_file(model_dir) == ["af_bella", "af_nicole"]


def test_default_model_filename_is_kokoro_v1_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    backend = KokoroBackend(tmp_path / "model", _config(model_filename="", voices=["cfg_voice"]))
    assert backend._model_filename == "kokoro-v1_0.pth"


def test_max_chars_uses_modern_default_when_max_chars_is_legacy_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KModel=object, KPipeline=object))

    backend = KokoroBackend(tmp_path / "model", _config())
    assert backend.max_chars() == 12000


def test_max_chars_respects_explicit_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KModel=object, KPipeline=object))
    cfg = _config()
    cfg["kokoro"]["max_chars"] = 3000

    backend = KokoroBackend(tmp_path / "model", cfg)
    assert backend.max_chars() == 3000


def test_resolve_modern_device_auto_prefers_cuda_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch_module(cuda_available=True, cuda_count=2, mps_available=False))
    backend = KokoroBackend(tmp_path / "model", _config())
    label, target = backend._resolve_modern_device()
    assert label == "cuda"
    assert target == "cuda"


def test_resolve_modern_device_supports_cuda_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch_module(cuda_available=True, cuda_count=2, mps_available=False))
    cfg = _config()
    cfg["kokoro"]["device"] = "cuda:1"
    backend = KokoroBackend(tmp_path / "model", cfg)
    label, target = backend._resolve_modern_device()
    assert label == "cuda:1"
    assert target == "cuda:1"


def test_resolve_modern_device_raises_when_cuda_requested_but_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch_module(cuda_available=False, cuda_count=0, mps_available=False))
    cfg = _config()
    cfg["kokoro"]["device"] = "cuda"
    backend = KokoroBackend(tmp_path / "model", cfg)
    with pytest.raises(RuntimeError, match="CUDA is not available"):
        backend._resolve_modern_device()


def test_resolve_modern_device_auto_selects_discrete_dml_when_cuda_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch_module(cuda_available=False, cuda_count=0, mps_available=False))
    fake_dml = types.SimpleNamespace(
        device_count=lambda: 2,
        device_name=lambda idx: ["Intel(R) UHD Graphics", "NVIDIA GeForce RTX 4060"][idx],
        device=lambda idx: f"dml-device-{idx}",
    )
    monkeypatch.setitem(sys.modules, "torch_directml", fake_dml)

    cfg = _config()
    cfg["kokoro"]["gpu_preference"] = "discrete"
    backend = KokoroBackend(tmp_path / "model", cfg)
    label, target = backend._resolve_modern_device()
    assert label == "dml:1"
    assert target == "dml-device-1"


def test_resolve_modern_device_prefers_integrated_dml_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch_module(cuda_available=False, cuda_count=0, mps_available=False))
    fake_dml = types.SimpleNamespace(
        device_count=lambda: 2,
        device_name=lambda idx: ["Intel(R) Iris Xe Graphics", "AMD Radeon RX 6800"][idx],
        device=lambda idx: f"dml-device-{idx}",
    )
    monkeypatch.setitem(sys.modules, "torch_directml", fake_dml)

    cfg = _config()
    cfg["kokoro"]["device"] = "dml"
    cfg["kokoro"]["gpu_preference"] = "integrated"
    backend = KokoroBackend(tmp_path / "model", cfg)
    label, target = backend._resolve_modern_device()
    assert label == "dml:0"
    assert target == "dml-device-0"


def test_resolve_modern_device_allows_explicit_dml_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch_module(cuda_available=False, cuda_count=0, mps_available=False))
    fake_dml = types.SimpleNamespace(
        device_count=lambda: 2,
        device_name=lambda idx: ["Intel(R) UHD Graphics", "NVIDIA GeForce RTX 4060"][idx],
        device=lambda idx: f"dml-device-{idx}",
    )
    monkeypatch.setitem(sys.modules, "torch_directml", fake_dml)

    cfg = _config()
    cfg["kokoro"]["device"] = "dml:0"
    backend = KokoroBackend(tmp_path / "model", cfg)
    label, target = backend._resolve_modern_device()
    assert label == "dml:0"
    assert target == "dml-device-0"


def test_resolve_modern_device_errors_when_dml_requested_without_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch_module(cuda_available=False, cuda_count=0, mps_available=False))
    monkeypatch.setitem(
        sys.modules,
        "torch_directml",
        types.SimpleNamespace(device_count=lambda: 0),
    )
    cfg = _config()
    cfg["kokoro"]["device"] = "dml"
    backend = KokoroBackend(tmp_path / "model", cfg)
    with pytest.raises(RuntimeError, match="no DirectML adapters"):
        backend._resolve_modern_device()


def test_voice_priority_prefers_explicit_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "voices.txt").write_text("txt_voice\n", encoding="utf-8")
    (model_dir / "af_bella.pt").write_bytes(b"voice")

    backend = KokoroBackend(model_dir, _config(voices=["cfg_voice"]), voices=["explicit_voice"])
    assert backend.list_voices() == ["explicit_voice"]


def test_voice_priority_prefers_voices_txt_over_local_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "voices.txt").write_text("txt_voice_a\ntxt_voice_b\n", encoding="utf-8")
    (model_dir / "af_bella.pt").write_bytes(b"voice")

    backend = KokoroBackend(model_dir, _config(voices=["cfg_voice"]))
    assert backend.list_voices() == ["txt_voice_a", "txt_voice_b"]


def test_voice_priority_uses_local_pt_files_when_no_explicit_or_voices_txt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "af_nicole.pt").write_bytes(b"a")
    (model_dir / "af_bella.pt").write_bytes(b"b")

    backend = KokoroBackend(model_dir, _config(voices=["cfg_voice"]))
    assert backend.list_voices() == ["af_bella.pt", "af_nicole.pt"]


def test_voice_priority_falls_back_to_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "missing-model"
    backend = KokoroBackend(model_dir, _config(voices=["cfg_voice_a", "cfg_voice_b"]))
    assert backend.list_voices() == ["cfg_voice_a", "cfg_voice_b"]


def test_synthesize_prefers_modern_runtime_by_default_when_both_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "kokoro-v1_0.pth").write_bytes(b"model")
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    calls = {"modern": 0, "legacy": 0}

    class FakeTensor:
        def __init__(self, values: list[float]):
            self._values = values

        def detach(self) -> "FakeTensor":
            return self

        def cpu(self) -> "FakeTensor":
            return self

        def flatten(self) -> "FakeTensor":
            return self

        def tolist(self) -> list[float]:
            return self._values

    class FakeKokoroTTS:
        def __init__(self, model_path: str):
            calls["legacy"] += 1

        def synthesize(self, text: str, voice: str, speed: float) -> bytes:
            calls["legacy"] += 1
            return b"LEGACY-AUDIO"

    class FakeKModel:
        def __init__(self, config: str, model: str):
            self.device = "cpu"

    class FakeKPipeline:
        def __init__(self, lang_code: str, model: object):
            calls["modern"] += 1

        def __call__(self, text: str, voice: str, speed: float, split_pattern: str):
            yield types.SimpleNamespace(audio=FakeTensor([0.0, 0.2, -0.2]))

    monkeypatch.setitem(
        sys.modules,
        "kokoro",
        types.SimpleNamespace(KokoroTTS=FakeKokoroTTS, KModel=FakeKModel, KPipeline=FakeKPipeline),
    )
    monkeypatch.setattr(KokoroBackend, "_resolve_modern_device", lambda self: ("cpu", "cpu"))

    backend = KokoroBackend(model_dir, _config())
    out_path = tmp_path / "modern_default.wav"
    backend.synthesize_to_file("hello world", "af_bella", 1.0, out_path)

    assert calls["modern"] == 1
    assert calls["legacy"] == 0
    assert out_path.read_bytes()[:4] == b"RIFF"


def test_synthesize_uses_legacy_first_when_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "kokoro-v1_0.pth").write_bytes(b"model")
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    calls = {"modern": 0, "legacy": 0}

    class FakeKokoroTTS:
        def __init__(self, model_path: str):
            calls["legacy"] += 1

        def synthesize(self, text: str, voice: str, speed: float) -> bytes:
            calls["legacy"] += 1
            return b"LEGACY-AUDIO"

    class FakeKModel:
        def __init__(self, config: str, model: str):
            calls["modern"] += 1

    class FakeKPipeline:
        def __init__(self, lang_code: str, model: object):
            calls["modern"] += 1

    monkeypatch.setitem(
        sys.modules,
        "kokoro",
        types.SimpleNamespace(KokoroTTS=FakeKokoroTTS, KModel=FakeKModel, KPipeline=FakeKPipeline),
    )
    monkeypatch.setattr(KokoroBackend, "_resolve_modern_device", lambda self: ("cpu", "cpu"))
    cfg = _config()
    cfg["kokoro"]["runtime_preference"] = "legacy"
    backend = KokoroBackend(model_dir, cfg)
    out_path = tmp_path / "legacy_pref.wav"
    backend.synthesize_to_file("hello world", "af_bella", 1.0, out_path)

    assert out_path.read_bytes() == b"LEGACY-AUDIO"
    assert calls["legacy"] == 2
    assert calls["modern"] == 0


def test_diagnose_runtime_reports_gpu_fallback_to_cpu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "torch", _fake_torch_module(cuda_available=False, cuda_count=0, mps_available=False))
    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KModel=object, KPipeline=object, KokoroTTS=object))
    backend = KokoroBackend(tmp_path / "model", _config())

    diag = backend.diagnose_runtime()
    assert diag["runtime"] == "modern"
    assert diag["device"] == "cpu"
    assert diag["is_gpu_fallback_to_cpu"] is True
    assert "falling back" in str(diag["reason"]).lower()


def test_cpu_thread_policy_auto_uses_capped_cpu_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.os, "cpu_count", lambda: 16)
    monkeypatch.delenv("OPENBLAS_NUM_THREADS", raising=False)
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    monkeypatch.delenv("MKL_NUM_THREADS", raising=False)
    calls: dict[str, list[int]] = {"num": [], "interop": []}
    fake_torch = types.SimpleNamespace(
        set_num_threads=lambda value: calls["num"].append(int(value)),
        set_num_interop_threads=lambda value: calls["interop"].append(int(value)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(KokoroBackend, "_torch_thread_policy_applied", None)

    backend = KokoroBackend(tmp_path / "model", _config())
    backend._apply_cpu_threading_policy(device_label="cpu")

    assert os.environ["OPENBLAS_NUM_THREADS"] == "4"
    assert os.environ["OMP_NUM_THREADS"] == "4"
    assert os.environ["MKL_NUM_THREADS"] == "4"
    assert calls["num"] == [4]
    assert calls["interop"] == [2]


def test_cpu_thread_policy_explicit_value_overrides_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "9")
    monkeypatch.setenv("OMP_NUM_THREADS", "9")
    monkeypatch.setenv("MKL_NUM_THREADS", "9")
    calls: dict[str, list[int]] = {"num": [], "interop": []}
    fake_torch = types.SimpleNamespace(
        set_num_threads=lambda value: calls["num"].append(int(value)),
        set_num_interop_threads=lambda value: calls["interop"].append(int(value)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(KokoroBackend, "_torch_thread_policy_applied", None)
    cfg = _config()
    cfg["kokoro"]["cpu_threads"] = 3

    backend = KokoroBackend(tmp_path / "model", cfg)
    backend._apply_cpu_threading_policy(device_label="cpu")

    assert os.environ["OPENBLAS_NUM_THREADS"] == "3"
    assert os.environ["OMP_NUM_THREADS"] == "3"
    assert os.environ["MKL_NUM_THREADS"] == "3"
    assert calls["num"] == [3]
    assert calls["interop"] == [1]


def test_cpu_thread_policy_auto_respects_existing_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.os, "cpu_count", lambda: 12)
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "5")
    monkeypatch.setenv("OMP_NUM_THREADS", "6")
    monkeypatch.setenv("MKL_NUM_THREADS", "7")
    calls: dict[str, list[int]] = {"num": [], "interop": []}
    fake_torch = types.SimpleNamespace(
        set_num_threads=lambda value: calls["num"].append(int(value)),
        set_num_interop_threads=lambda value: calls["interop"].append(int(value)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(KokoroBackend, "_torch_thread_policy_applied", None)

    backend = KokoroBackend(tmp_path / "model", _config())
    backend._apply_cpu_threading_policy(device_label="cpu")

    assert os.environ["OPENBLAS_NUM_THREADS"] == "5"
    assert os.environ["OMP_NUM_THREADS"] == "6"
    assert os.environ["MKL_NUM_THREADS"] == "7"
    assert calls["num"] == [5]
    assert calls["interop"] == [2]


def test_tensor_audio_to_pcm16_vectorized_path_matches_expected() -> None:
    torch = pytest.importorskip("torch")
    values = [-1.5, -1.0, -0.25, 0.0, 0.25, 1.0, 1.5]
    tensor = torch.tensor(values, dtype=torch.float32)

    actual = KokoroBackend._tensor_audio_to_pcm16(tensor)
    expected = array(
        "h",
        [int(round(max(-1.0, min(1.0, float(sample))) * 32767.0)) for sample in values],
    ).tobytes()
    assert actual == expected


def test_synthesize_uses_legacy_runtime_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_file = model_dir / "kokoro-v1_0.pth"
    model_file.write_bytes(b"model")

    calls: dict[str, object] = {}

    class FakeKokoroTTS:
        def __init__(self, model_path: str):
            calls["model_path"] = model_path

        def synthesize(self, text: str, voice: str, speed: float) -> bytes:
            calls["text"] = text
            calls["voice"] = voice
            calls["speed"] = speed
            return b"LEGACY-AUDIO"

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KokoroTTS=FakeKokoroTTS))

    backend = KokoroBackend(model_dir, _config())
    out_path = tmp_path / "legacy.wav"
    backend.synthesize_to_file("hello world", "af_bella", 1.2, out_path)

    assert out_path.read_bytes() == b"LEGACY-AUDIO"
    assert calls["model_path"] == str(model_file)
    assert calls["voice"] == "af_bella"


def test_synthesize_reuses_legacy_runtime_between_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_file = model_dir / "kokoro-v1_0.pth"
    model_file.write_bytes(b"model")

    calls = {"init": 0, "synth": 0}

    class FakeKokoroTTS:
        def __init__(self, model_path: str):
            calls["init"] += 1
            calls["model_path"] = model_path

        def synthesize(self, text: str, voice: str, speed: float) -> bytes:
            calls["synth"] += 1
            return b"LEGACY-AUDIO"

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KokoroTTS=FakeKokoroTTS))

    backend = KokoroBackend(model_dir, _config())
    backend.synthesize_to_file("hello one", "af_bella", 1.0, tmp_path / "legacy1.wav")
    backend.synthesize_to_file("hello two", "af_bella", 1.0, tmp_path / "legacy2.wav")

    assert calls["init"] == 1
    assert calls["synth"] == 2
    assert calls["model_path"] == str(model_file)


def test_synthesize_rebuilds_legacy_runtime_when_model_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    first_model = model_dir / "first.pth"
    second_model = model_dir / "second.pth"
    first_model.write_bytes(b"m1")
    second_model.write_bytes(b"m2")

    calls = {"init": 0}

    class FakeKokoroTTS:
        def __init__(self, model_path: str):
            calls["init"] += 1
            calls[f"path_{calls['init']}"] = model_path

        def synthesize(self, text: str, voice: str, speed: float) -> bytes:
            return b"LEGACY-AUDIO"

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KokoroTTS=FakeKokoroTTS))

    backend = KokoroBackend(model_dir, _config(model_filename="first.pth"))
    backend.synthesize_to_file("hello one", "af_bella", 1.0, tmp_path / "legacy_a.wav")
    backend._model_filename = "second.pth"
    backend.synthesize_to_file("hello two", "af_bella", 1.0, tmp_path / "legacy_b.wav")

    assert calls["init"] == 2
    assert calls["path_1"] == str(first_model)
    assert calls["path_2"] == str(second_model)


def test_synthesize_falls_back_to_modern_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_file = model_dir / "kokoro-v1_0.pth"
    model_file.write_bytes(b"model")
    local_voice = model_dir / "af_bella.pt"
    local_voice.write_bytes(b"voice")

    calls: dict[str, object] = {}

    class FakeTensor:
        def __init__(self, values: list[float]):
            self._values = values

        def detach(self) -> "FakeTensor":
            return self

        def cpu(self) -> "FakeTensor":
            return self

        def flatten(self) -> "FakeTensor":
            return self

        def tolist(self) -> list[float]:
            return self._values

    class FakeKModel:
        def __init__(self, *args, **kwargs):
            calls["model_path"] = kwargs.get("model")
            calls["config_arg"] = kwargs.get("config")
            self.device = "cpu"

    class FakeKPipeline:
        def __init__(self, lang_code: str, model: object):
            calls["lang_code"] = lang_code
            calls["pipeline_model"] = model

        def load_voice(self, voice: str):
            calls["load_voice"] = voice
            return types.SimpleNamespace(to=lambda _device: voice)

        def __call__(self, text: str, voice: str, speed: float, split_pattern: str):
            calls["text"] = text
            calls["voice"] = voice
            calls["speed"] = speed
            calls["split_pattern"] = split_pattern
            yield types.SimpleNamespace(audio=FakeTensor([0.0, 0.25, -0.25]))

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KModel=FakeKModel, KPipeline=FakeKPipeline))

    backend = KokoroBackend(model_dir, _config())
    out_path = tmp_path / "modern.wav"
    backend.synthesize_to_file("hello world", "af_bella.pt", 1.0, out_path)

    header = out_path.read_bytes()[:4]
    assert header == b"RIFF"
    assert calls["lang_code"] == "a"
    assert calls["model_path"] == str(model_file)
    assert calls["load_voice"] == str(local_voice)
    assert calls["voice"] == str(local_voice)


def test_synthesize_reuses_modern_runtime_between_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_file = model_dir / "kokoro-v1_0.pth"
    model_file.write_bytes(b"model")
    config_file = model_dir / "config.json"
    config_file.write_text("{}", encoding="utf-8")

    calls = {"kmodel_init": 0, "kpipeline_init": 0}

    class FakeTensor:
        def __init__(self, values: list[float]):
            self._values = values

        def detach(self) -> "FakeTensor":
            return self

        def cpu(self) -> "FakeTensor":
            return self

        def flatten(self) -> "FakeTensor":
            return self

        def tolist(self) -> list[float]:
            return self._values

    class FakeKModel:
        def __init__(self, config: str, model: str):
            calls["kmodel_init"] += 1
            calls["config_path"] = config
            calls["model_path"] = model
            self.device = "cpu"

    class FakeKPipeline:
        def __init__(self, lang_code: str, model: object):
            calls["kpipeline_init"] += 1
            calls["lang_code"] = lang_code
            calls["pipeline_model"] = model

        def load_voice(self, voice: str):
            calls["last_loaded_voice"] = voice
            return types.SimpleNamespace(to=lambda _device: voice)

        def __call__(self, text: str, voice: str, speed: float, split_pattern: str):
            calls["last_voice"] = voice
            yield types.SimpleNamespace(audio=FakeTensor([0.0, 0.1, -0.1]))

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KModel=FakeKModel, KPipeline=FakeKPipeline))

    backend = KokoroBackend(model_dir, _config())
    backend.synthesize_to_file("hello one", "af_bella", 1.0, tmp_path / "modern1.wav")
    backend.synthesize_to_file("hello two", "af_bella", 1.0, tmp_path / "modern2.wav")

    assert calls["kmodel_init"] == 1
    assert calls["kpipeline_init"] == 1
    assert calls["config_path"] == str(config_file)
    assert calls["model_path"] == str(model_file)
    assert calls["last_loaded_voice"] == "af_bella"


def test_synthesize_reuses_cached_modern_voice_pack_between_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_file = model_dir / "kokoro-v1_0.pth"
    model_file.write_bytes(b"model")
    (model_dir / "config.json").write_text("{}", encoding="utf-8")

    calls = {"load_voice": 0}

    class FakeTensor:
        def __init__(self, values: list[float]):
            self._values = values

        def detach(self) -> "FakeTensor":
            return self

        def cpu(self) -> "FakeTensor":
            return self

        def flatten(self) -> "FakeTensor":
            return self

        def tolist(self) -> list[float]:
            return self._values

    class FakeKModel:
        def __init__(self, config: str, model: str):
            self.device = "cpu"

    class FakeKPipeline:
        def __init__(self, lang_code: str, model: object):
            pass

        def load_voice(self, voice: str):
            calls["load_voice"] += 1
            return types.SimpleNamespace(to=lambda _device: voice)

        def __call__(self, text: str, voice: str, speed: float, split_pattern: str):
            yield types.SimpleNamespace(audio=FakeTensor([0.0, 0.2, -0.2]))

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KModel=FakeKModel, KPipeline=FakeKPipeline))

    backend = KokoroBackend(model_dir, _config())
    backend.synthesize_to_file("hello one", "af_bella", 1.0, tmp_path / "voice_cache_1.wav")
    backend.synthesize_to_file("hello two", "af_bella", 1.0, tmp_path / "voice_cache_2.wav")

    assert calls["load_voice"] == 1


def test_synthesize_rebuilds_modern_runtime_when_model_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    first_model = model_dir / "first.pth"
    second_model = model_dir / "second.pth"
    first_model.write_bytes(b"m1")
    second_model.write_bytes(b"m2")
    (model_dir / "config.json").write_text("{}", encoding="utf-8")

    calls = {"kmodel_init": 0}

    class FakeTensor:
        def __init__(self, values: list[float]):
            self._values = values

        def detach(self) -> "FakeTensor":
            return self

        def cpu(self) -> "FakeTensor":
            return self

        def flatten(self) -> "FakeTensor":
            return self

        def tolist(self) -> list[float]:
            return self._values

    class FakeKModel:
        def __init__(self, config: str, model: str):
            calls["kmodel_init"] += 1
            calls[f"model_{calls['kmodel_init']}"] = model

    class FakeKPipeline:
        def __init__(self, lang_code: str, model: object):
            calls["lang_code"] = lang_code

        def __call__(self, text: str, voice: str, speed: float, split_pattern: str):
            yield types.SimpleNamespace(audio=FakeTensor([0.0, 0.2, -0.2]))

    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KModel=FakeKModel, KPipeline=FakeKPipeline))

    backend = KokoroBackend(model_dir, _config(model_filename="first.pth"))
    backend.synthesize_to_file("hello one", "af_bella", 1.0, tmp_path / "modern_a.wav")
    backend._model_filename = "second.pth"
    backend.synthesize_to_file("hello two", "af_bella", 1.0, tmp_path / "modern_b.wav")

    assert calls["kmodel_init"] == 2
    assert calls["model_1"] == str(first_model)
    assert calls["model_2"] == str(second_model)


def test_synthesize_raises_actionable_error_when_no_runtime_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kokoro_backend.sys, "platform", "linux")
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "kokoro-v1_0.pth").write_bytes(b"model")
    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace())

    backend = KokoroBackend(model_dir, _config())
    with pytest.raises(RuntimeError, match=r"KokoroTTS.*KPipeline"):
        backend.synthesize_to_file("hello", "af_bella", 1.0, tmp_path / "out.wav")
