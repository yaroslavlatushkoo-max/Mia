# -*- coding: utf-8 -*-
from .base import BaseSkill
import json
import os
import threading
import time
from datetime import datetime

class OrganizerSkills(BaseSkill):
    
    def __init__(self, speech, config=None):
        super().__init__(speech, config)
        self.notes_file = os.path.join(os.path.dirname(__file__), "..", "data", "notes.json")
        self._ensure_files()
    
    def _ensure_files(self):
        os.makedirs(os.path.dirname(self.notes_file), exist_ok=True)
        if not os.path.exists(self.notes_file):
            with open(self.notes_file, "w", encoding="utf-8") as f:
                json.dump([], f)
    
    def _num_to_words(self, n):
        """Convert number to Russian words (for Silero TTS)"""
        words = {
            0: "ноль", 1: "один", 2: "два", 3: "три", 4: "четыре",
            5: "пять", 6: "шесть", 7: "семь", 8: "восемь", 9: "девять",
            10: "десять", 11: "одиннадцать", 12: "двенадцать",
            13: "тринадцать", 14: "четырнадцать", 15: "пятнадцать",
            16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
            19: "девятнадцать", 20: "двадцать", 30: "тридцать",
            40: "сорок", 50: "пятьдесят", 60: "шестьдесят",
            100: "сто", 200: "двести", 300: "триста",
            400: "четыреста", 500: "пятьсот", 1000: "тысяча"
        }
        if n in words:
            return words[n]
        if n < 100:
            tens = (n // 10) * 10
            ones = n % 10
            return f"{words[tens]} {words[ones]}"
        return str(n)
    
    def can_handle(self, command):
        keywords = ["заметк", "запиши", "сохрани", "таймер", "напомни", "будильник", "очисти"]
        return any(kw in command for kw in keywords)
    
    def execute(self, command):
        cmd = command.lower()
        
        if any(w in cmd for w in ["запиши", "сохрани заметку", "добавь заметку", "новая заметка"]):
            for prefix in ["запиши", "сохрани заметку", "добавь заметку", "новая заметка"]:
                cmd = cmd.replace(prefix, "", 1)
            note_text = cmd.strip()
            if note_text:
                self.add_note(note_text)
                return True
        
        if any(w in cmd for w in ["прочитай заметки", "список заметок", "мои заметки", "покажи заметки", "зачитай заметки"]):
            self.read_notes()
            return True
        
        if "удали заметку" in cmd:
            import re
            match = re.search(r"(\d+)", cmd)
            if match:
                self.delete_note(int(match.group(1)))
                return True
        
        if "таймер" in cmd:
            import re
            match = re.search(r"(\d+)\s*(секунд|минут|час)", cmd)
            if match:
                value = int(match.group(1))
                unit = match.group(2)
                if unit == "секунд": seconds = value
                elif unit == "минут": seconds = value * 60
                elif unit == "час": seconds = value * 3600
                else: seconds = value
                self.set_timer(seconds, unit, value)
                return True
                # Clear all notes
        if any(w in cmd for w in ["очисти заметки", "удали все заметки", "сотри заметки", "удали заметки"]):
            self.clear_notes()
            return True
        return False
    
    def add_note(self, text):
        with open(self.notes_file, "r", encoding="utf-8") as f:
            notes = json.load(f)
        notes.append({"text": text, "date": datetime.now().strftime("%d.%m.%Y %H:%M")})
        with open(self.notes_file, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        self.speech.speak(f"Заметка сохранена: {text}")
    
    def read_notes(self):
        with open(self.notes_file, "r", encoding="utf-8") as f:
            notes = json.load(f)
        if not notes:
            self.speech.speak("Заметок пока нет")
        else:
            count_word = self._num_to_words(len(notes))
            self.speech.speak(f"Всего заметок: {count_word}")
            for i, note in enumerate(notes, 1):
                num_word = self._num_to_words(i)
                self.speech.speak(f"Заметка {num_word}: {note['text']}")
    
    def delete_note(self, index):
        with open(self.notes_file, "r", encoding="utf-8") as f:
            notes = json.load(f)
        if 1 <= index <= len(notes):
            notes.pop(index - 1)
            with open(self.notes_file, "w", encoding="utf-8") as f:
                json.dump(notes, f, ensure_ascii=False, indent=2)
            num_word = self._num_to_words(index)
            self.speech.speak(f"Заметка {num_word} удалена")
        else:
            self.speech.speak("Нет заметки с таким номером")
    
    def set_timer(self, seconds, unit, value):
        num_word = self._num_to_words(value)
        self.speech.speak(f"Таймер на {num_word} {unit} запущен")
        def timer_thread():
            time.sleep(seconds)
            self.speech.speak("Время вышло! Таймер сработал.")
        threading.Thread(target=timer_thread, daemon=True).start()
    def clear_notes(self):
        with open(self.notes_file, "w", encoding="utf-8") as f:
            json.dump([], f)
        self.speech.speak("Все заметки удалены")