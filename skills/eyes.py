# -*- coding: utf-8 -*-
import pyautogui
import time
import os
import base64
import requests
import json

class EyesSkill:
    def __init__(self, speech):
        self.speech = speech
        self.screen_path = os.path.join(os.path.dirname(__file__), "..", "data", "screen.png")
        self.api_key = "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"
        self.model = "anthropic/claude-3-haiku"  # Быстрый и понимает изображения
    
    def see_screen(self):
        """Сделать скриншот и вернуть base64"""
        screenshot = pyautogui.screenshot()
        # Уменьшаем для скорости (ширина 1024px)
        w, h = screenshot.size
        new_h = int(h * 1024 / w)
        screenshot = screenshot.resize((1024, new_h))
        screenshot.save(self.screen_path)
        with open(self.screen_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    
    def analyze_with_ai(self, question="Опиши кратко что на экране, на русском"):
        """Анализ экрана через Claude (OpenRouter)"""
        self.speech.speak("Смотрю...")
        
        try:
            image_b64 = self.see_screen()
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                        ]
                    }],
                    "max_tokens": 100
                },
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                answer = answer.replace("\n", " ").replace("*", "")[:200]
                self.speech.speak(answer)
                return answer
            else:
                print(f"OpenRouter error: {response.status_code}")
                self.speech.speak("Ошибка анализа экрана")
                return ""
        except Exception as e:
            print(f"Vision error: {e}")
            self.speech.speak("Не получилось проанализировать экран")
            return ""
    
    def find_element(self, description):
        """Найти элемент на экране по описанию и кликнуть"""
        self.speech.speak(f"Ищу {description}...")
        
        try:
            image_b64 = self.see_screen()
            
            prompt = f"Найди на скриншоте {description}. Ответь ТОЛЬКО в формате: x,y (координаты центра). Если элемента нет, ответь 'нет'."
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                        ]
                    }],
                    "max_tokens": 20
                },
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                answer = data["choices"][0]["message"]["content"].strip()
                
                if answer.lower() != "нет" and "," in answer:
                    try:
                        x, y = map(int, answer.replace(" ", "").split(","))
                        screen_w, screen_h = pyautogui.size()
                        scale_x = screen_w / 1024
                        scale_y = screen_h / (screen_h * 1024 / screen_w)
                        
                        real_x = int(x * scale_x)
                        real_y = int(y * scale_y)
                        
                        pyautogui.click(real_x, real_y)
                        self.speech.speak(f"Нажала на {description}")
                        return True
                    except:
                        pass
            
            self.speech.speak(f"Не нашла {description} на экране")
            return False
        except Exception as e:
            print(f"Find error: {e}")
            return False
    
    def can_handle(self, command):
        keywords = [
            "посмотри", "что на экране", "что видишь", "опиши экран",
            "найди на экране", "кликни на", "нажми на",
            "аккаунт", "первый", "второй", "третий", "четвёртый", "пятый",
            "что это", "что там", "что открыто",
        ]
        return any(kw in command for kw in keywords)
    
    def execute(self, command):
        cmd = command.lower()
        
        if any(w in cmd for w in ["что на экране", "что видишь", "опиши экран", "что открыто"]):
            self.analyze_with_ai()
            return True
        
        if any(w in cmd for w in ["найди на экране", "кликни на", "нажми на"]):
            for prefix in ["найди на экране", "кликни на", "нажми на"]:
                if prefix in cmd:
                    target = cmd.replace(prefix, "").strip()
                    if target:
                        self.find_element(target)
                        return True
        
        if any(w in cmd for w in ["первый", "второй", "третий", "четвёртый", "пятый"]):
            positions = {
                "первый": (826, 775),
                "второй": (1024, 775),
                "третий": (1235, 775),
                "четвёртый": (1447, 775),
                "пятый": (1635, 775),
            }
            for word, pos in positions.items():
                if word in cmd:
                    pyautogui.click(x=pos[0], y=pos[1])
                    self.speech.speak(f"Выбираю {word} аккаунт")
                    time.sleep(1)
                    return True
        
        return False