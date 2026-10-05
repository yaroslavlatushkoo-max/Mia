# -*- coding: utf-8 -*-
import webbrowser
import requests
import subprocess
import sys
import re
import pyautogui
import time

class WebSkills:
    def __init__(self, speech):
        self.speech = speech

    def open_site(self, url):
        print(f"Otkryvayu sajt: {url}")
        webbrowser.open(url)
        self.speech.speak("Открываю сайт")

    def search(self, query):
        url = f"https://www.google.com/search?q={query}"
        self.open_site(url)

    def _num_to_words(self, n):
        words = {
            0: "ноль", 1: "один", 2: "два", 3: "три", 4: "четыре",
            5: "пять", 6: "шесть", 7: "семь", 8: "восемь", 9: "девять",
            10: "десять", 11: "одиннадцать", 12: "двенадцать",
            13: "тринадцать", 14: "четырнадцать", 15: "пятнадцать",
            16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
            19: "девятнадцать", 20: "двадцать", 30: "тридцать",
            40: "сорок", 50: "пятьдесят", 60: "шестьдесят",
        }
        if n in words:
            return words[n]
        if n < 100:
            tens = (n // 10) * 10
            ones = n % 10
            return words[tens] + " " + words[ones]
        return str(n)

    def get_weather(self, city="Moscow"):
        try:
            city_map = {
                "минск": "Minsk", "минске": "Minsk", "ми": "Minsk",
                "брест": "Brest", "бресте": "Brest",
                "гомель": "Gomel", "гомеле": "Gomel",
                "гродно": "Grodno",
                "витебск": "Vitebsk", "витебске": "Vitebsk",
                "могилев": "Mogilev", "могилеве": "Mogilev",
                "москва": "Moscow", "москве": "Moscow",
                "питер": "Saint Petersburg",
            }
            city_lower = city.lower()
            display_city = city
            if city_lower in city_map:
                display_city = city_map[city_lower]
            
            # Use English name for API
            api_city = city_map.get(city_lower, city)
            
            url = f"https://wttr.in/{api_city}?format=%C+%t&lang=ru"
            headers = {"User-Agent": "curl/7.68.0"}
            response = requests.get(url, timeout=5, headers=headers)
            if response.status_code == 200:
                weather = response.text.strip()
                weather = weather.encode('ascii', 'ignore').decode('ascii')
                temp_match = re.search(r'([+-]?\d+)', weather)
                temp_num = int(temp_match.group(1)) if temp_match else 0
                temp_word = self._num_to_words(abs(temp_num))
                sign = "минус" if temp_num < 0 else "плюс"
                weather = weather.replace("+", "").replace(str(temp_num), "").strip()
                weather = weather.replace("Partly cloudy", "облачно")
                weather = weather.replace("Light rain", "дождь")
                weather = weather.replace("Light rain shower", "дождь")
                weather = weather.replace("Patchy rain nearby", "дождь")
                weather = weather.replace("Overcast", "пасмурно")
                weather = weather.replace("Clear", "ясно")
                weather = weather.replace("Sunny", "солнечно")
                weather = weather.replace("Mist", "туман")
                weather = weather.replace("Fog", "туман")
                weather = weather.replace("Rain", "дождь")
                weather = weather.replace("Snow", "снег")
                weather = weather.replace("Cloudy", "облачно")
                weather = weather.strip()
                self.speech.speak(f"Погода в {display_city}: {weather} {sign} {temp_word} градусов")
            else:
                self.speech.speak("Не удалось получить погоду")
        except Exception as e:
            print(f"Weather error: {e}")
            self.speech.speak("Проблемы с интернетом")

    def youtube_search(self, query):
        """Search on YouTube"""
        url = f"https://www.youtube.com/results?search_query={query}"
        self.open_site(url)
        time.sleep(2)
        self.speech.speak(f"Ищу {query} на YouTube")

    def youtube_select_video(self, number=1):
        """Select video by number on YouTube search results page"""
        self.speech.speak(f"Выбираю видео номер {self._num_to_words(number)}")
        time.sleep(0.5)
        # Press Tab to navigate to video thumbnails, then Enter
        for _ in range(number):
            pyautogui.press('tab')
            time.sleep(0.1)
        pyautogui.press('enter')

    def youtube_play(self):
        """Play/pause YouTube video"""
        pyautogui.press('space')
        self.speech.speak("Воспроизведение")

    def youtube_pause(self):
        pyautogui.press('space')
        self.speech.speak("Пауза")

    def youtube_fullscreen(self):
        pyautogui.press('f')
        self.speech.speak("Полный экран")

    def youtube_next(self):
        pyautogui.hotkey('shift', 'n')
        self.speech.speak("Следующее видео")

    def youtube_prev(self):
        self.speech.speak("Возвращаюсь к предыдущему видео")
        pyautogui.hotkey('alt', 'left')

    def youtube_mute(self):
        pyautogui.press('m')
        self.speech.speak("Звук YouTube отключен")

    def youtube_subtitles(self):
        pyautogui.press('c')
        self.speech.speak("Субтитры переключены")

    def can_handle(self, command):
        keywords = [
            "pogoda", "погода", "погоду", "погоде",
            "naidi", "найди", "найти", "поищи", "загугли", "погугли",
            "search", "поиск", "ищи",
            # YouTube
            "ютуб", "youtube", "видео",
            "выбери", "полный экран", "субтитры",
        ]
        return any(kw in command for kw in keywords)

    def execute(self, command):
        cmd = command.lower()
        
        # === YOUTUBE (если "ютуб" или "youtube" в команде) ===
        if any(w in cmd for w in ["ютуб", "youtube", "ютюб", "ютуби", "ютубе"]):
            # Extract everything after "ютуб" or "ютубе"
            match = re.search(r'(?:ютуб[еи]?|youtube)\s+(.+)', cmd)
            if match:
                query = match.group(1).strip().strip('«»"\'()[]{}')
                if query:
                    self.youtube_search(query)
                    return True
            
            # Select video by number
            number_map = {"первое": 1, "второе": 2, "третье": 3, "четвертое": 4, "пятое": 5}
            for word, num in number_map.items():
                if word in cmd:
                    self.youtube_select_video(num)
                    return True
            
            # YouTube controls
            if "полный экран" in cmd or "фулскрин" in cmd:
                self.youtube_fullscreen()
                return True
            if "субтитры" in cmd:
                self.youtube_subtitles()
                return True
            if any(w in cmd for w in ["без звука", "мут", "выключи звук"]):
                self.youtube_mute()
                return True
            
            # Just "ютуб"
            self.open_site("https://youtube.com")
            return True
        
        # === WEATHER ===
        if "погода" in cmd:
            match = re.search(r"погода(?: в городе | в | )(.+)", cmd)
            city = match.group(1).strip() if match else "Moscow"
            self.get_weather(city)
            return True
        
        # === GOOGLE SEARCH ===
        search_match = re.search(r"(?:найди|поищи|найти|погугли|загугли|поиск|ищи|покажи в гугле|найди в гугле|найди в браузере) (.+)", cmd)
        if search_match:
            self.search(search_match.group(1))
            return True
        
        return False        
