from __future__ import annotations

from typing import Optional

from .stt_engine import STTEngine, STTResult
from .tts_engine import TTSEngine
from ..core.orchestrator import Orchestrator


class VoicePipeline:
    def __init__(
        self,
        orchestrator: Optional[Orchestrator] = None,
        stt: Optional[STTEngine] = None,
        tts: Optional[TTSEngine] = None
    ):
        self.orchestrator = orchestrator or Orchestrator()
        self.stt = stt or STTEngine()
        self.tts = tts or TTSEngine()

    def listen_and_respond(self, duration: int = 5) -> Optional[dict]:
        """Записать голос, обработать, озвучить ответ."""

        # 1. Слушаем
        stt_result = self.stt.transcribe_from_microphone(duration)

        if not stt_result or not stt_result.text:
            self.tts.speak("Я не расслышала. Повтори, пожалуйста.")
            return None

        print(f"[User] {stt_result.text}")

        # 2. Обрабатываем через ядро
        result = self.orchestrator.handle(stt_result.text, source="voice")

        answer = result.get("answer", "Я не знаю что ответить.")

        print(f"[Mia] {answer}")

        # 3. Озвучиваем
        self.tts.speak(answer)

        return result

    def process_text(self, text: str) -> dict:
        """Обработать текст и озвучить ответ."""
        result = self.orchestrator.handle(text, source="text")

        answer = result.get("answer", "")
        if answer:
            self.tts.speak(answer)

        return result