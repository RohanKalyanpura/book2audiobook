<div align="center">

# 📖 Book2Audiobook

**Convert DRM-free ebooks into high-quality audiobooks — locally or via the cloud.**

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)](https://python.org)
[![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt)](https://pypi.org/project/PySide6/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## ✨ Features

- 🖥️ **Desktop UI** — clean native window for macOS and Windows
- 📚 **Multi-format input** — EPUB, PDF, and TXT
- 🔊 **Multiple backends** — local AI (Kokoro) or cloud TTS (OpenAI, OpenRouter)
- 🚀 **GPU accelerated** — Apple MPS, NVIDIA CUDA, AMD/Intel DirectML
- 📦 **Packageable** — ships as a standalone `.app` or `.exe` via PyInstaller
- 🔖 **Chapter-aware output** — M4B with chapter markers, MP3, or WAV

> **Note:** Only convert content you have the legal right to use.

---

## 🚀 Quick Start

### 1. Create a Python environment

```bash
python -m venv .venv
source .venv/bin/activate    # macOS / Linux
# .venv\Scripts\activate     # Windows PowerShell

pip install -r requirements.txt
```

### 2. Install ffmpeg

```bash
# macOS
brew install ffmpeg

# Windows
winget install "FFmpeg (Essentials Build)"
```

Restart your terminal after installation so the new `PATH` takes effect.

### 3. (Kokoro users) Install a Kokoro runtime

The app supports two Kokoro API styles:

| Runtime | Import |
|---|---|
| **Modern** (recommended) | `from kokoro import KPipeline, KModel` |
| **Legacy** | `from kokoro import KokoroTTS` |

```bash
pip install kokoro
```

Verify it is working:
```bash
python -c "import kokoro; print('modern:', hasattr(kokoro, 'KPipeline'), '| legacy:', hasattr(kokoro, 'KokoroTTS'))"
```

### 4. Add your Kokoro model files

Place your `.pth` / `.onnx` / `.bin` model files in a single folder.

| Mode | Default Model Path |
|---|---|
| Source run | `<repo>/model/` |
| macOS packaged | next to `Book2Audiobook.app` → `dist/model/` |
| Windows packaged | next to `Book2Audiobook.exe` → `dist\Book2Audiobook\model\` |

> **Tip:** Keep only one model file in the folder, or rename the target file to `kokoro-v1_0.pth`.

### 5. Run the app

```bash
python -m book2audiobook.app
```

---

## 🎮 GPU Acceleration

Book2Audiobook auto-detects the best available accelerator. Install the correct extra for your hardware:

| Platform | Hardware | Required Extra |
|---|---|---|
| **macOS** | Apple Silicon (M1-M4) | ✅ Built-in — nothing extra needed |
| **Windows / Linux** | NVIDIA GPU | `pip install torch --index-url https://download.pytorch.org/whl/cu124` |
| **Windows** | AMD / Intel GPU | `pip install torch-directml` |
| Any | CPU fallback | ✅ Always available |

> If the GPU cannot be initialized, the app will display a warning dialog and continue on CPU.

**NVIDIA — swap the PyTorch wheel:**
```bash
pip uninstall torch torchaudio torchvision -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

**Multi-GPU control** (set in `Backend Options → Kokoro`):
- `kokoro.gpu_preference`: `discrete` (default) or `integrated`
- `kokoro.device_index`: pin a specific adapter index
- `kokoro.device`: `auto` | `cpu` | `mps` | `cuda` | `cuda:0` | `dml` | `dml:1`

---

## 🔑 Cloud Backend Setup

**OpenAI TTS**
```bash
export OPENAI_API_KEY=sk-...
```

**OpenRouter**
```bash
export OPENROUTER_API_KEY=sk-or-...
```

Alternatively, enter keys directly under the app's key settings dialog.

---

## 📦 Packaging

**macOS:**
```bash
PYINSTALLER_CONFIG_DIR=/tmp/pyinstaller \
  pyinstaller --noconfirm --distpath dist --workpath build/pyinstaller build/pyinstaller.spec
```

**Windows:**
```powershell
pyinstaller --noconfirm --distpath dist --workpath build\pyinstaller build\pyinstaller.spec
```

After building, place your `model/` folder and `ffmpeg`/`ffprobe` binaries adjacent to the executable.

---

## 🛠️ Troubleshooting

<details>
<summary><strong>❌ "Kokoro runtime is not installed or not importable"</strong></summary>

```bash
python -c "import kokoro; print(hasattr(kokoro, 'KokoroTTS'), hasattr(kokoro, 'KPipeline'), hasattr(kokoro, 'KModel'))"
```

If both checks return `False`, your Kokoro package is not installed correctly in this environment. Re-run `pip install kokoro` with your venv active.

</details>

<details>
<summary><strong>❌ "Kokoro model missing"</strong></summary>

- Confirm model files exist in the folder shown in `Backend Options → Kokoro`.
- Keep only **one** model file, or rename the desired one to `kokoro-v1_0.pth`.
- For the modern Kokoro runtime in offline setups, also place `config.json` in the same folder.

</details>

<details>
<summary><strong>❌ "Multiple files found in model folder"</strong></summary>

Keep only one model file, or set `Model Filename` in `Backend Options → Kokoro` to the exact target filename.

</details>

<details>
<summary><strong>❌ "ffmpeg / ffprobe not found"</strong></summary>

- Verify both are on your `PATH` (`ffmpeg -version`).
- Restart your terminal after installation or `PATH` changes.

</details>

<details>
<summary><strong>❌ macOS crash: SIGBUS / STACK GUARD / OpenBLAS</strong></summary>

Stack overflow from NumPy/OpenBLAS in a worker thread. To work around:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m book2audiobook.app
```

The app already limits BLAS threads by default; this manually overrides it.

</details>

<details>
<summary><strong>❌ TypeError: Plain typing.Self is not valid</strong></summary>

Caused by newer PyTorch + Python 3.9 combinations. The app includes a compatibility shim for this — update to the latest version of this repo. If it still occurs, use Python 3.10+.

</details>

<details>
<summary><strong>❌ OpenAI / OpenRouter key errors</strong></summary>

- Confirm `OPENAI_API_KEY` / `OPENROUTER_API_KEY` env vars are set.
- Or clear and re-save keys from the app's key settings dialog.

</details>

---

## 📂 Data Locations

| Platform | Jobs Database |
|---|---|
| macOS | `~/Library/Application Support/Book2Audiobook/jobs.sqlite3` |
| Windows | `%APPDATA%\Book2Audiobook\jobs.sqlite3` |

---

## 🧪 Tests

```bash
pytest -q
```

---

## 📜 Legal

Only use Book2Audiobook to convert content you have the right to reproduce. The authors accept no liability for misuse.
