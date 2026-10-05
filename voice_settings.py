"""
Настройка голоса для Мии.
Запусти этот файл отдельно: python voice_settings.py
"""

import pyttsx3

class VoiceTuner:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.voices = self.engine.getProperty('voices')
    
    def show_all_voices(self):
        """Показать все доступные голоса"""
        print("\n" + "="*60)
        print("🎤 ДОСТУПНЫЕ ГОЛОСА")
        print("="*60)
        
        for i, voice in enumerate(self.voices):
            gender = "👩 Женский" if any(w in voice.name.lower() for w in ['female', 'zira', 'elena', 'katya', 'woman', 'anna', 'maria']) else "👨 Мужской"
            print(f"\nИндекс: {i}")
            print(f"  Имя: {voice.name}")
            print(f"  Пол: {gender}")
            print(f"  ID: {voice.id[:50]}...")
    
    def test_voice(self, index):
        """Протестировать голос по индексу"""
        if index >= len(self.voices):
            print(f"❌ Индекс {index} не существует. Всего голосов: {len(self.voices)}")
            return
        
        voice = self.voices[index]
        self.engine.setProperty('voice', voice.id)
        
        print(f"\n🔊 Тестирую голос: {voice.name}")
        print("Настройки: скорость=180, громкость=0.9")
        
        self.engine.setProperty('rate', 180)
        self.engine.setProperty('volume', 0.9)
        
        test_phrases = [
            "Привет! Я Мия, твой голосовой ассистент.",
            "Сегодня отличный день для новых свершений.",
            "Чем я могу тебе помочь?",
        ]
        
        for phrase in test_phrases:
            print(f"  Говорю: {phrase}")
            self.engine.say(phrase)
            self.engine.runAndWait()
    
    def tune_voice(self, index, rate=180, volume=0.9):
        """Настройка голоса с параметрами"""
        if index >= len(self.voices):
            print(f"❌ Индекс {index} не существует.")
            return
        
        voice = self.voices[index]
        self.engine.setProperty('voice', voice.id)
        self.engine.setProperty('rate', rate)
        self.engine.setProperty('volume', volume)
        
        print(f"\n🎵 Текущие настройки:")
        print(f"  Голос: {voice.name}")
        print(f"  Скорость: {rate}")
        print(f"  Громкость: {volume}")
        print(f"\n  Для изменения скорости: введи число (150-220)")
        print(f"  Для изменения громкости: введи 'громкость число' (0.1-1.0)")
        print(f"  Для теста: просто нажми Enter")
        print(f"  Для выхода: 'выход' или 'готово'")
        
        while True:
            user_input = input("\n> ").strip().lower()
            
            if user_input in ['выход', 'готово', 'exit', 'done']:
                print(f"\n✅ Итоговые настройки: голос={voice.name}, скорость={rate}, громкость={volume}")
                print(f"   Пропиши в config.py: VOICE_INDEX = {index}")
                print(f"   Пропиши в config.py: VOICE_RATE = {rate}")
                print(f"   Пропиши в config.py: VOICE_VOLUME = {volume}")
                break
            
            elif user_input.startswith('громкость'):
                try:
                    volume = float(user_input.split()[1])
                    volume = max(0.1, min(1.0, volume))
                    self.engine.setProperty('volume', volume)
                    print(f"  Громкость: {volume}")
                except:
                    print("  Формат: громкость 0.8")
            
            elif user_input.isdigit():
                rate = int(user_input)
                rate = max(100, min(300, rate))
                self.engine.setProperty('rate', rate)
                print(f"  Скорость: {rate}")
            
            else:
                # Тест
                self.engine.say("Привет! Я Мия. Как тебе такой голос?")
                self.engine.runAndWait()
    
    def interactive(self):
        """Интерактивный режим настройки"""
        self.show_all_voices()
        
        print("\n" + "="*60)
        print("✨ НАСТРОЙКА ГОЛОСА МИИ")
        print("="*60)
        
        try:
            index = int(input("\nВведи индекс женского голоса (обычно 1 или 2): "))
            self.test_voice(index)
            
            print("\nНравится голос?")
            ans = input("1 - да, настраивать дальше | 2 - другой индекс | 3 - выход: ")
            
            if ans == '1':
                self.tune_voice(index)
            elif ans == '2':
                self.interactive()
            else:
                print("Выход")
        except ValueError:
            print("Введи число!")
            self.interactive()


if __name__ == "__main__":
    tuner = VoiceTuner()
    tuner.interactive()