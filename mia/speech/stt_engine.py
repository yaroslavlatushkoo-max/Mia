from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class STTResult:
    text: str
    language: str
    confidence: float


class STTEngine:
    def __init__(self, model_size: str = "small", device: str = "cpu"):
        self.model_size = model_size
        self.device = device
        self._model = None
        self._load_model()

    def _load_model(self):
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type="int8"
            )
            print(f"[STT] Модель {self.model_size} загружена")
        except ImportError:
            print("[STT] faster-whisper не установлен. Установи: pip install faster-whisper")
            self._model = None

    def transcribe(self, audio_path: str) -> Optional[STTResult]:
        if not self._model:
            return None

        try:
            segments, info = self._model.transcribe(
                audio_path,
                language="ru",
                beam_size=5
            )

            text = " ".join([seg.text for seg in segments]).strip()

            return STTResult(
                text=text,
                language=info.language,
                confidence=info.language_probability
            )
        except Exception as e:
            print(f"[STT] Ошибка: {e}")
            return None

    def transcribe_from_microphone(self, duration: int = 5) -> Optional[STTResult]:
        """Записать с микрофона и распознать."""
        try:
            import sounddevice as sd
            import numpy as np
            import tempfile
            import soundfile as sf

            print(f"[STT] Говори... ({duration} сек)")

            # Записываем аудио
            sample_rate = 16000
            audio = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype=np.float32
            )
            sd.wait()

            # Сохраняем во временный файл
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                sf.write(f.name, audio, sample_rate)
                temp_path = f.name

            # Распознаём
            result = self.transcribe(temp_path)

            # Удаляем временный файл
            import os
            os.unlink(temp_path)

            return result

        except ImportError:
            print("[STT] Нужны sounddevice, soundfile, numpy")
            print("Установи: pip install sounddevice soundfile numpy")
            return None
        except Exception as e:
            print(f"[STT] Ошибка записи: {e}")
            return None