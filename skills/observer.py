# -*- coding: utf-8 -*-
import threading
import time
import os
import json
from datetime import datetime

class ObserverSkill:
    def __init__(self, speech):
        self.speech = speech
        self.observations = []
        self.observing = False
        self.log_file = os.path.join(os.path.dirname(__file__), "..", "data", "observations.json")
        self._load_log()
    
    def _load_log(self):
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, "r", encoding="utf-8") as f:
                    self.observations = json.load(f)
        except:
            self.observations = []
    
    def _save_log(self):
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(self.observations[-100:], f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def start_observing(self, interval=300):
        """Начать наблюдение каждые N секунд (по умолчанию 5 минут)"""
        if self.observing:
            self.speech.speak("Я уже наблюдаю")
            return
        
        self.observing = True
        self.speech.speak(f"Начинаю наблюдение каждые {interval//60} минут")
        
        def observe_loop():
            while self.observing:
                time.sleep(interval)
                try:
                    # Делаем скриншот
                    import pyautogui
                    screenshot = pyautogui.screenshot()
                    # Уменьшаем
                    w, h = screenshot.size
                    screenshot = screenshot.resize((512, int(h*512/w)))
                    
                    # Сохраняем
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = os.path.join(os.path.dirname(__file__), "..", "data", f"obs_{timestamp}.png")
                    screenshot.save(path)
                    
                    # Записываем наблюдение
                    obs = {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "screenshot": path,
                        "note": "Автоматическое наблюдение"
                    }
                    self.observations.append(obs)
                    self._save_log()
                    
                    print(f"Наблюдение сохранено: {timestamp}")
                    
                    # Удаляем старые скриншоты (оставляем последние 20)
                    screenshots = sorted([f for f in os.listdir(os.path.dirname(path)) if f.startswith("obs_")])
                    for old in screenshots[:-20]:
                        os.remove(os.path.join(os.path.dirname(path), old))
                        
                except Exception as e:
                    print(f"Observer error: {e}")
        
        threading.Thread(target=observe_loop, daemon=True).start()
    
    def stop_observing(self):
        """Остановить наблюдение"""
        self.observing = False
        self.speech.speak("Наблюдение остановлено")
    
    def analyze_observations(self):
        """Проанализировать наблюдения за сегодня"""
        today = datetime.now().strftime("%Y-%m-%d")
        today_obs = [o for o in self.observations if today in o.get("time", "")]
        
        if today_obs:
            self.speech.speak(f"За сегодня я сделала {len(today_obs)} наблюдений")
        else:
            self.speech.speak("Сегодня наблюдений не было")
        
        return today_obs
    
    def can_handle(self, command):
        keywords = [
            "начни наблюдать", "наблюдай", "следи за экраном",
            "останови наблюдение", "хватит наблюдать",
            "что ты видела", "покажи наблюдения", "анализ дня",
        ]
        return any(kw in command for kw in keywords)
    
    def execute(self, command):
        cmd = command.lower()
        
        if any(w in cmd for w in ["начни наблюдать", "наблюдай", "следи"]):
            self.start_observing()
            return True
        
        if any(w in cmd for w in ["останови наблюдение", "хватит наблюдать"]):
            self.stop_observing()
            return True
        
        if any(w in cmd for w in ["что ты видела", "покажи наблюдения", "анализ дня"]):
            self.analyze_observations()
            return True
        
        return False