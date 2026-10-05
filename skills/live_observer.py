# -*- coding: utf-8 -*-
import threading
import time
import os
import base64
import json
import hashlib
import pyautogui
from datetime import datetime
import requests

class LiveObserver:
    def __init__(self, speech):
        self.speech = speech
        self.observing = False
        self.api_key = "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"
        
        # Папки
        self.data_dir = os.path.join(os.path.dirname(__file__), "..", "data", "visual_memory")
        self.screenshots_dir = os.path.join(self.data_dir, "screenshots")
        self.memory_file = os.path.join(self.data_dir, "memory.json")
        os.makedirs(self.screenshots_dir, exist_ok=True)
        
        # База уникальных скриншотов
        self.memory = {}
        self._load_memory()
        
        self.last_report = ""
        self.last_report_time = 0
        
        print(f"[EYE] Visual memory loaded: {len(self.memory)} unique screenshots")
        
        # Автозапуск наблюдения через 5 секунд
        threading.Thread(target=self._auto_start, daemon=True).start()
    
    def _auto_start(self):
        """Автозапуск наблюдения"""
        time.sleep(5)
        self.start_observing(interval=15)
    
    def _load_memory(self):
        """Загрузить память из файла"""
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    self.memory = json.load(f)
        except:
            self.memory = {}
    
    def _save_memory(self):
        """Сохранить память в файл"""
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def _get_image_hash(self, image):
        """MD5 хэш изображения"""
        return hashlib.md5(image.tobytes()).hexdigest()
    
    def _analyze_with_claude(self, image_b64):
        """Отправить скриншот Claude и получить описание"""
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "anthropic/claude-3-haiku",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Опиши ОДНИМ предложением что на этом скриншоте (программы, окна, действия). На русском."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                        ]
                    }],
                    "max_tokens": 50
                },
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            return None
        except Exception as e:
            print(f"Claude error: {e}")
            return None
    
    def _process_screenshot(self):
        """Обработать скриншот: проверить уникальность, сохранить, проанализировать"""
        try:
            # Делаем скриншот
            screenshot = pyautogui.screenshot()
            
            # Хэш для проверки уникальности
            img_hash = self._get_image_hash(screenshot)
            
            # Проверяем, есть ли такой в памяти
            if img_hash in self.memory:
                return self.memory[img_hash]["description"]
            
            # Новый скриншот! Уменьшаем и сохраняем
            w, h = screenshot.size
            screenshot_small = screenshot.resize((1024, int(h*1024/w)))
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"scr_{timestamp}_{img_hash[:8]}.png"
            filepath = os.path.join(self.screenshots_dir, filename)
            screenshot_small.save(filepath)
            
            # Конвертируем в base64 и анализируем
            import io
            buffer = io.BytesIO()
            screenshot_small.save(buffer, format="PNG")
            image_b64 = base64.b64encode(buffer.getvalue()).decode()
            
            description = self._analyze_with_claude(image_b64)
            if not description:
                description = "Неизвестный экран"
            
            # Сохраняем в память
            self.memory[img_hash] = {
                "file": filename,
                "description": description,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "hash": img_hash
            }
            self._save_memory()
            
            print(f"[EYE] Новый скриншот: {description[:80]}")
            return description
            
        except Exception as e:
            print(f"Process error: {e}")
            return None
    
    def start_observing(self, interval=15):
        """Начать наблюдение (молча)"""
        if self.observing:
            return
        
        self.observing = True
        print(f"[EYE] Авто-наблюдение запущено. В памяти {len(self.memory)} сцен.")
        
        def observe_loop():
            while self.observing:
                time.sleep(interval)
                description = self._process_screenshot()
                if description:
                    self.last_report = description
                    self.last_report_time = time.time()
        
        threading.Thread(target=observe_loop, daemon=True).start()
    
    def stop_observing(self):
        """Остановить наблюдение"""
        self.observing = False
        # Удаляем повторы при выходе
        self._cleanup_duplicates()
        self.speech.speak(f"Наблюдение остановлено. Сохранено {len(self.memory)} уникальных сцен.")
    
    def _cleanup_duplicates(self):
        """Удалить повторяющиеся скриншоты"""
        files_on_disk = set(os.listdir(self.screenshots_dir))
        files_in_memory = set()
        
        for img_hash, data in self.memory.items():
            files_in_memory.add(data["file"])
        
        # Удаляем файлы, которых нет в памяти
        for file in files_on_disk:
            if file not in files_in_memory:
                try:
                    os.remove(os.path.join(self.screenshots_dir, file))
                except:
                    pass
    
    def report(self):
        """Рассказать что видит"""
        if self.last_report and time.time() - self.last_report_time < 60:
            self.speech.speak(self.last_report[:200])
        else:
            description = self._process_screenshot()
            if description:
                self.last_report = description
                self.last_report_time = time.time()
                self.speech.speak(description[:200])
            else:
                self.speech.speak("Не могу проанализировать экран")
    
    def show_memory_stats(self):
        """Показать статистику памяти"""
        total = len(self.memory)
        today = 0
        today_str = datetime.now().strftime("%Y-%m-%d")
        for data in self.memory.values():
            if today_str in data.get("date", ""):
                today += 1
        
        self.speech.speak(f"В памяти {total} уникальных сцен. За сегодня: {today} новых.")
    
    def can_handle(self, command):
        keywords = [
            "начни следить", "следи за мной", "наблюдай в реальном",
            "останови слежку", "хватит следить",
            "что видишь", "что сейчас", "что происходит",
            "статистика памяти", "сколько сцен", "память глаз",
            "что ты видишь", "ты видишь", "опиши экран", "что видишь",
        ]
        return any(kw in command for kw in keywords)
    
    def execute(self, command):
        cmd = command.lower()

        if any(w in cmd for w in ["что ты видишь", "ты видишь", "опиши экран", "что видишь", "что сейчас", "что происходит"]):
            self.report()
            return True
        
        if any(w in cmd for w in ["начни следить", "следи за мной", "наблюдай в реальном"]):
            self.start_observing()
            return True
        
        if any(w in cmd for w in ["останови слежку", "хватит следить"]):
            self.stop_observing()
            return True
        
        if any(w in cmd for w in ["что видишь", "что сейчас", "что происходит"]):
            self.report()
            return True
        
        if any(w in cmd for w in ["статистика памяти", "сколько сцен", "память глаз"]):
            self.show_memory_stats()
            return True
        
        return False