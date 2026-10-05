# -*- coding: utf-8 -*-
from .base import BaseSkill
import pyautogui

# Disable failsafe for media keys (they are safe)
pyautogui.FAILSAFE = False

class MediaSkills(BaseSkill):
    
    def can_handle(self, command):
        keywords = [
            # Volume
            "громче", "громкость", "звук", "мут", "заглуши",
            "прибавь", "убавь", "увеличь", "уменьш",
            "сделай громче", "сделай тише", "погромче", "потише",
            "без звука", "выключи звук", "отключи звук", "включи звук",
            # Media
            "пауз", "стоп", "приостанови", "поставь на паузу",
            "продолжи", "плей", "воспроизведи", "запусти",
            "дальше", "след", "вперед", "вперёд", "переключи",
            "назад", "предыд", "пред трек", "прошлый",
            # Brightness
            "ярче", "темнее", "яркость",
        ]
        return any(kw in command for kw in keywords)
    
    def execute(self, command):
        cmd = command.lower()
        
        # === VOLUME UP ===
        if any(w in cmd for w in ["громче", "погромче", "прибавь звук", "увеличь громкость", "сделай громче", "сделай погромче", "прибавь громкость"]):
            for _ in range(10): 
                pyautogui.press("volumeup")
            self.speech.speak("Громкость увеличена")
            return True
        
        # === VOLUME DOWN ===
        if any(w in cmd for w in ["тише", "потише", "убавь звук", "уменьш громкость", "сделай тише", "сделай потише", "убавь громкость"]):
            for _ in range(10): 
                pyautogui.press("volumedown")
            self.speech.speak("Громкость уменьшена")
            return True
        
        # === MUTE ===
        if any(w in cmd for w in ["без звука", "выключи звук", "мут", "заглуши", "отключи звук", "выруби звук"]):
            pyautogui.press("volumemute")
            self.speech.speak("Звук отключен")
            return True
        
        # === PAUSE ===
        if any(w in cmd for w in ["пауз", "стоп", "приостанови", "поставь на паузу", "останови"]):
            pyautogui.press("playpause")
            self.speech.speak("Пауза")
            return True
        
        # === PLAY / CONTINUE ===
        if any(w in cmd for w in ["продолжи", "плей", "воспроизведи", "запусти", "дальше играй", "продолжай"]):
            pyautogui.press("playpause")
            self.speech.speak("Продолжаю")
            return True
        
        # === NEXT ===
        if any(w in cmd for w in ["дальше", "след", "вперед", "вперёд", "след трек", "следующий трек", "переключи вперед", "переключи вперёд"]):
            pyautogui.press("nexttrack")
            self.speech.speak("Следующий трек")
            return True
        
        # === PREVIOUS ===
        if any(w in cmd for w in ["назад", "предыд", "пред трек", "предыдущий трек", "прошлый трек", "переключи назад", "верни"]):
            pyautogui.press("prevtrack")
            self.speech.speak("Предыдущий трек")
            return True
        
        # === BRIGHTNESS ===
        if any(w in cmd for w in ["ярче", "прибавь яркость", "увеличь яркость", "сделай ярче"]):
            self.speech.speak("Для яркости нажмите Fn + F6")
            return True
        if any(w in cmd for w in ["темнее", "убавь яркость", "уменьш яркость", "сделай темнее"]):
            self.speech.speak("Для яркости нажмите Fn + F5")
            return True
        
        return False