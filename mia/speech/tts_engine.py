class TTSEngine:
    def __init__(self, engine: str = "silero", speaker: str = "xenia"):
        self.engine = engine
        self.speaker = speaker
        self._model = None
        self._device = "cpu"
        self._sample_rate = 48000
        self._load_model()

    def _load_model(self):
        if self.engine == "f5tts":
            self._load_f5tts()
        else:
            self._load_silero()

    def _load_f5tts(self):
        try:
            from f5_tts.api import F5TTS
            self._model = F5TTS(model_path="models/senko_tts/")
            print("[TTS] F5-TTS (Сэнко-сан) загружена")
        except Exception as e:
            print(f"[TTS] F5-TTS ошибка: {e}, fallback на Silero")
            self.engine = "silero"
            self._load_silero()

    def synthesize(self, text: str, output_path: Optional[str] = None) -> Optional[TTSResult]:
        if self.engine == "f5tts":
            return self._synthesize_f5tts(text, output_path)
        else:
            return self._synthesize_silero(text, output_path)

    def _synthesize_f5tts(self, text: str, output_path: Optional[str] = None) -> Optional[TTSResult]:
        try:
            import soundfile as sf

            if output_path is None:
                output_path = f"voice_cache/response_{hash(text) % 100000}.wav"

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            # F5-TTS синтез
            audio = self._model.infer(text)

            sf.write(output_path, audio, self._sample_rate)

            duration = len(audio) / self._sample_rate

            return TTSResult(audio_path=output_path, duration=duration)

        except Exception as e:
            print(f"[TTS] F5-TTS ошибка: {e}")
            return None