import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from book2audiobook.backends.kokoro_backend import KokoroBackend
import traceback

print("Starting test_ui_import.py")
try:
    app = QApplication(sys.argv)
    print("PySide6 QApplication created successfully.")
except Exception as e:
    print(f"Failed to create QApplication: {e}")
    traceback.print_exc()

try:
    print("Attempting to import KModel, KPipeline from kokoro...")
    from kokoro import KModel, KPipeline
    print("Direct import SUCCESS")
except Exception as e:
    print("Direct import FAILED:")
    traceback.print_exc()

print("Testing KokoroBackend.diagnose_runtime()...")
try:
    backend = KokoroBackend(Path("."), {})
    diag = backend.diagnose_runtime()
    print("diagnose_runtime SUCCESS:")
    print(diag)
except Exception as e:
    print("diagnose_runtime FAILED:")
    traceback.print_exc()
