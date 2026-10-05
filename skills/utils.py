# -*- coding: utf-8 -*-
from .base import BaseSkill
from datetime import datetime
import random

class UtilsSkills(BaseSkill):
    
    def can_handle(self, command):
        keywords = [
            "время", "час", "дата", "число", "день недели",
            "шутк", "анекдот", "рассмеши", "пошути",
            "монетк", "орёл", "кубик", "кость",
            "привет", "здравствуй", "пока", "выход",
        ]
        return any(kw in command for kw in keywords)
    
    def execute(self, command):
        cmd = command.lower()
        
        if any(w in cmd for w in ["который час", "время", "сколько времени", "подскажи время", "который час сейчас", "время сейчас"]):
            self.tell_time()
            return True
        
        if any(w in cmd for w in ["дата", "число", "день недели", "сегодня", "какое сегодня", "сегодняшняя дата"]):
            self.tell_date()
            return True
        
        if any(w in cmd for w in ["шутк", "анекдот", "рассмеши", "пошути"]):
            self.tell_joke()
            return True
        
        if any(w in cmd for w in ["монетк", "орёл", "орел или решка"]):
            self.flip_coin()
            return True
        
        if any(w in cmd for w in ["кубик", "кость", "брось кубик"]):
            self.roll_dice()
            return True
        
        # Привет и пока — короткие шаблоны
        if any(w in cmd for w in ["привет", "здравствуй", "добрый день", "доброе утро", "добрый вечер"]):
            g = ["Приветствую!", "Здравствуйте!", "Добрый день!", "Рада вас слышать!"]
            self.speech.speak(random.choice(g))
            return True
        
        return False
    
    def tell_time(self):
        now = datetime.now()
        h, m = now.hour, now.minute
        if h in [1, 21]: hw = "час"
        elif h in [2, 3, 4, 22, 23]: hw = "часа"
        else: hw = "часов"
        if m == 0:
            self.speech.speak(f"Сейчас ровно {h} {hw}.")
        elif m < 10:
            self.speech.speak(f"На часах {h} {hw} ноль {m} минут.")
        else:
            self.speech.speak(f"Текущее время — {h} {hw} {m} минут.")
    
    def tell_date(self):
        now = datetime.now()
        months = ["января", "февраля", "марта", "апреля", "мая", "июня",
                  "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        days = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
        self.speech.speak(f"Сегодня {now.day} {months[now.month-1]}, {days[now.weekday()]}.")
    
    def tell_joke(self):
        jokes = [
            "Программист ставит будильник. Утром будильник орёт. Программист: «Отмена, контрл зет, контрл зет!»",
            "Почему Python такой спокойный? У него нет острых скобок!",
            "Объявление: «Требуется программист. Зарплата триста тысяч. Обязанности: знать всё, уметь чинить принтеры и настраивать чайники.»",
        ]
        self.speech.speak(random.choice(jokes))
    
    def flip_coin(self):
        result = random.choice(["Орёл!", "Решка!"])
        self.speech.speak(f"Подбрасываю монетку... {result}")
    
    def roll_dice(self):
        result = random.randint(1, 6)
        self.speech.speak(f"Кидаю кубик... Выпало {result}!")