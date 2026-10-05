# -*- coding: utf-8 -*-
"""
Mia Environment Audit
Безопасная диагностика окружения. Ничего не устанавливает и не изменяет.
Запуск из корня VoiceAssistant:
    python audit_environment.py
"""

import importlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PACKAGES = [
    "torch", "torchaudio", "torchvision",
    "vosk", "sounddevice", "soundfile", "numpy",
    "chromadb", "ollama", "requests",
    "selenium", "flask", "flask_cors",
    "fastapi", "uvicorn", "edge_tts",
    "pyttsx3", "pyautogui", "psutil",
    "pygetwindow", "pycaw", "comtypes",
    "librosa", "numba",
    "transformers", "datasets", "peft", "trl", "unsloth",
    "gradio", "speech_recognition",
    "yaml",
]

def version_of(name):
    try:
        m = importlib.import_module(name)
        return getattr(m, "__version__", "(version attribute unavailable)")
    except Exception as e:
        return f"NOT IMPORTABLE: {type(e).__name__}: {e}"

def pip_show(name):
    try:
        p = subprocess.run(
            [sys.executable, "-m", "pip", "show", name],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if p.returncode != 0:
            return "not installed"
        for line in p.stdout.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
        return "installed (version unknown)"
    except Exception as e:
        return f"pip error: {e}"

print("=" * 72)
print("MIA ENVIRONMENT AUDIT")
print("=" * 72)

print("\n[PYTHON]")
print("Executable :", sys.executable)
print("Version    :", platform.python_version())
print("Platform   :", platform.platform())
print("Prefix     :", sys.prefix)
print("Base prefix:", getattr(sys, "base_prefix", "?"))
print("Virtualenv :", sys.prefix != getattr(sys, "base_prefix", sys.prefix))

print("\n[PROJECT]")
print("Root       :", ROOT)
print("requirements.txt:", (ROOT / "requirements.txt").exists())
print("venv       :", (ROOT / "venv").exists())
print(".venv      :", (ROOT / ".venv").exists())
print("env        :", (ROOT / "env").exists())
print("root/python:", (ROOT / "python").exists())

print("\n[PYTHON COMMANDS]")
for cmd in ["python", "py", "pip", "ollama"]:
    print(f"{cmd:8}:", shutil.which(cmd))

print("\n[PACKAGES]")
for name in PACKAGES:
    print(f"{name:18} import={version_of(name)} | pip={pip_show(name)}")

print("\n[TORCH / CUDA]")
try:
    import torch
    print("torch version       :", torch.__version__)
    print("CUDA available      :", torch.cuda.is_available())
    print("torch CUDA version  :", torch.version.cuda)
    print("cuDNN version       :", torch.backends.cudnn.version())
    print("GPU count           :", torch.cuda.device_count())
    for i in range(torch.cuda.device_count()):
        print(f"GPU {i}              :", torch.cuda.get_device_name(i))
        print(f"GPU {i} capability   :", torch.cuda.get_device_capability(i))
except Exception as e:
    print("Torch diagnostic error:", repr(e))

print("\n[OLLAMA]")
try:
    p = subprocess.run(
        ["ollama", "list"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=15
    )
    print("return code:", p.returncode)
    print(p.stdout[:12000] if p.stdout else "(no stdout)")
    if p.stderr:
        print("stderr:", p.stderr[:4000])
except Exception as e:
    print("Ollama diagnostic error:", repr(e))

print("\n[IMPORTANT FILES]")
for rel in [
    "model.pt",
    "speech.py",
    "main.py",
    "config.py",
    "tts_engine.py",
    "tts_server.py",
    "vits_speak.py",
    "voice_settings.py",
    "cache_voices.py",
    "voice_cache",
    "temp_voice",
    "tts_output",
]:
    p = ROOT / rel
    if p.exists():
        if p.is_file():
            print(f"{rel:22} EXISTS file={p.stat().st_size} bytes")
        else:
            print(f"{rel:22} EXISTS directory")
    else:
        print(f"{rel:22} MISSING")

print("\n" + "=" * 72)
print("AUDIT FINISHED — nothing was installed or modified.")
print("=" * 72)
