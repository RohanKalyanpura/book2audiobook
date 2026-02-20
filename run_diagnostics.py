from book2audiobook.backends.kokoro_backend import KokoroBackend
import sys, traceback
try:
    from kokoro import KModel, KPipeline
    print("Modern runtime is available.")
except Exception as e:
    print(f"Failed to import modern runtime:")
    traceback.print_exc()

try:
    from kokoro import KokoroTTS
    print("Legacy runtime is available.")
except Exception as e:
    print(f"Failed to import legacy runtime:")
    traceback.print_exc()
