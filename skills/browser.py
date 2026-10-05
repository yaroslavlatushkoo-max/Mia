# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.action_chains import ActionChains
import time
import re
import os
import threading

class BrowserSkills:
    def __init__(self, speech):
        self.speech = speech
        self.driver = None
        self.known_videos = []
        self.scanning = False
    
    def _start_browser(self):
        if self.driver is None:
            print("Запускаю браузер с твоим профилем...")
            
            # Kill any existing Edge processes first
            import subprocess
            subprocess.run("taskkill /F /IM msedge.exe", shell=True, capture_output=True)
            time.sleep(1)
            
            edge_options = Options()
            edge_options.add_argument("--start-maximized")
            edge_options.add_argument("--no-sandbox")
            edge_options.add_argument("--disable-dev-shm-usage")
            # Use YOUR real profile
            edge_options.add_argument("--user-data-dir=C:\\Users\\vo_va\\AppData\\Local\\Microsoft\\Edge\\User Data")
            edge_options.add_argument("--profile-directory=Default")
            # Allow remote debugging
            edge_options.add_argument("--remote-debugging-port=9222")
            
            driver_path = os.path.join(os.path.dirname(__file__), "..", "msedgedriver.exe")
            service = Service(driver_path)
            self.driver = webdriver.Edge(service=service, options=edge_options)
            print("Браузер готов!")
    
    def open_youtube(self):
        self._start_browser()
        self.driver.get("https://www.youtube.com")
        time.sleep(3)
        self.known_videos = []
        self.scanning = False  # Reset scanner
        self._scan_current_page()
        self.speech.speak("Ютуб открыт")
        self._start_background_scanner()
    
    def _scan_current_page(self):
        """Scan current page for ALL video titles"""
        try:
            # Universal scan - get ALL video title elements
            videos = self.driver.execute_script("""
                var results = [];
                // Try every possible video title element
                var allElems = document.querySelectorAll(
                    '#video-title, ' +
                    'a[title], ' +
                    'h3 a, ' +
                    'ytd-compact-video-renderer a[title], ' +
                    'ytd-video-renderer a[title], ' +
                    'ytd-rich-item-renderer a[title], ' +
                    'ytd-grid-video-renderer a[title]'
                );
                for (var i = 0; i < allElems.length; i++) {
                    var t = allElems[i].textContent || allElems[i].getAttribute('title') || '';
                    t = t.trim();
                    // Filter out non-video links (menu items, channels, etc.)
                    if (t && t.length > 10 && results.indexOf(t) === -1 && 
                        t.indexOf('%') === -1 &&  // filter percentages
                        t.indexOf('Подписаться') === -1 &&  // filter buttons
                        t.indexOf('Главная') === -1) {  // filter navigation
                        results.push(t);
                    }
                }
                return results;
            """)
            
            found_any = False
            for title in videos:
                if title and title not in self.known_videos:
                    self.known_videos.append(title)
                    found_any = True
            
            if found_any:
                print(f"Found {len(self.known_videos)} videos total")
            else:
                print(f"No new videos. Total: {len(self.known_videos)}")
        except Exception as e:
            print(f"Scan error: {e}")
    
    def _start_background_scanner(self):
        """Periodically scan as user scrolls"""
        if self.scanning:
            return
        self.scanning = True
        def scan_loop():
            while self.scanning and self.driver:
                try:
                    time.sleep(2)
                    if self.driver:
                        self._scan_current_page()
                except:
                    break
        threading.Thread(target=scan_loop, daemon=True).start()
    
    def find_and_click_video(self, query):
        self._start_browser()
        
        # ALWAYS reset and rescan current page
        self.known_videos = []
        time.sleep(1)
        self._scan_current_page()
        # Scroll sidebar
        self.driver.execute_script("""
            var sidebar = document.querySelector('#related') || document.querySelector('ytd-watch-next-secondary-results-renderer');
            if (sidebar) { sidebar.scrollTop += 2000; sidebar.scrollTop -= 500; }
        """)
        time.sleep(1.5)
        self._scan_current_page()

        query_words = query.lower().split()
        print(f"Searching for '{query}' ({len(query_words)} words) among {len(self.known_videos)} videos")
        
        best_match = None
        best_score = 0
        
        for title in self.known_videos:
            title_lower = title.lower()
            # Count how many query words are in this title
            score = sum(1 for word in query_words if word in title_lower)
            if score > best_score:
                best_score = score
                best_match = title
        
        # Need at least 2 matching words, or ceil(half) for longer queries
        min_score = max(2, len(query_words) // 2)
        
        if best_match and best_score >= min_score:
            try:
                clicked = self.driver.execute_script("""
                    var searchText = arguments[0];
                    var allElems = document.querySelectorAll(
                        '#video-title, a[title], h3 a, ' +
                        'ytd-compact-video-renderer a[title], ' +
                        'ytd-video-renderer a[title], ' +
                        'ytd-rich-item-renderer a[title]'
                    );
                    for (var i = 0; i < allElems.length; i++) {
                        var t = allElems[i].textContent || allElems[i].getAttribute('title') || '';
                        if (t.trim().toLowerCase().replace(/\\s/g, '') === searchText.toLowerCase().replace(/\\s/g, '')) {
                            allElems[i].scrollIntoView({block: 'center'});
                            allElems[i].click();
                            return true;
                        }
                    }
                    return false;
                """, best_match)
                
                if clicked:
                    self.speech.speak("Открываю")
                    self.known_videos = []
                    return True
            except Exception as e:
                print(f"Click error: {e}")
            self.speech.speak("Не удалось открыть видео")
            return False
        else:
            if best_match:
                print(f"Best: '{best_match[:60]}' (score: {best_score}, need: {min_score})")
                for t in self.known_videos[:3]:
                    print(f"  Available: '{t[:60]}'")
            self.speech.speak("Видео не найдено")
            return False
    
    def click_video_by_number(self, number):
        """Click video by number in list"""
        if 0 < number <= len(self.known_videos):
            title = self.known_videos[number - 1]
            self.find_and_click_video(title)
            return True
        else:
            self.speech.speak(f"Нет видео с номером {number}")
            return False
    
    def close_browser(self):
        self.scanning = False
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.known_videos = []
            self.speech.speak("Браузер закрыт")
    
    def can_handle(self, command):
        keywords = [
            # YouTube open
            "открой ютуб", "запусти ютуб", "ютуб", "youtube", "с полноэкранного", "из полноэкранного", "с полного экрана",
            # Video selection
            "видео номер", "открой видео", "включи видео", "выбери видео", "выбери",
            "первое видео", "второе видео", "третье видео",
            "четвертое видео", "пятое видео",
            # Playback controls
            "пауза", "стоп", "приостанови", "поставь на паузу", "сделай паузу",
            "продолжи", "плей", "воспроизведи", "сделай плей", "поставь на паузу", "сделай паузу", "пауза",
            "на весь экран", "на полный экран", "разверни",
            "полный экран", "фулскрин", "во весь экран",
            "полный экран", "фулскрин", "во весь экран", "на полный", "на весь экран", "разверни", "сделай на полный",
            "выйти из полного", "убрать полный", "оконный режим", "сделай окно",
	    "выйди из полного", "выйди из полноэкранного", "убери полный",
	    "сделай окно", "окно", "не полный", "уменьши экран",
            "следующее видео", "след видео", "предыдущее видео", "пред видео",
            "громче ютуб", "прибавь звук ютуб", "громче видео", "сделай громче ютуб",
            "тише ютуб", "убавь звук ютуб", "тише видео", "сделай тише ютуб",
            "без звука", "мут", "выключи звук", "включи звук",
            # Close
            "закрой браузер",
        ]
        return any(kw in command for kw in keywords)
    
    def execute(self, command):
        cmd = command.lower()
        
        # Open YouTube
        if any(w in cmd for w in ["ютуб", "youtube"]):
            self.open_youtube()
            return True
        
        # Next/prev video shortcuts
        if any(w in cmd for w in ["следующее видео", "след видео", "предыдущее видео", "пред видео"]):
            if self.driver:
                if "пред" in cmd:
                    self.driver.execute_script("history.back();")
                    self.speech.speak("Предыдущее видео")
                else:
                    actions = ActionChains(self.driver)
                    actions.key_down(Keys.SHIFT).send_keys('n').key_up(Keys.SHIFT).perform()
                    self.speech.speak("Следующее видео")
                return True
        
        # === YOUTUBE PLAYBACK CONTROLS ===
        if any(w in cmd for w in ["полный экран", "фулскрин", "во весь экран", "на полный", "на весь экран", "разверни", "сделай на полный"]):
            self._start_browser()
            ActionChains(self.driver).send_keys('f').perform()
            self.speech.speak("Полный экран")
            return True
        if any(w in cmd for w in ["выйти из полного", "выйди из полного", "с полноэкранного", "из полноэкранного", "с полного экрана", "выйти из полноэкранного", "выйди из полноэкранного", "убрать полный", "убери полный", "оконный режим", "сделай окно", "окно", "уменьши экран"]):
            self._start_browser()
            self.driver.execute_script("document.exitFullscreen();")
            self.speech.speak("Оконный режим")
            return True
        if any(w in cmd for w in ["пауза", "стоп", "приостанови", "поставь на паузу", "сделай паузу"]):
            self._start_browser()
            ActionChains(self.driver).send_keys(Keys.SPACE).perform()
            self.speech.speak("Пауза")
            return True
        if any(w in cmd for w in ["продолжи", "плей", "воспроизведи", "сделай плей"]):
            self._start_browser()
            ActionChains(self.driver).send_keys(Keys.SPACE).perform()
            self.speech.speak("Продолжаю")
            return True
        
        # Video by number words
        number_map = {
            "первое": 1, "второе": 2, "третье": 3,
            "четвертое": 4, "пятое": 5,
        }
        for word, num in number_map.items():
            if word in cmd and "видео" in cmd:
                self.click_video_by_number(num)
                return True
        
        # Video by number digit
        match = re.search(r"видео номер (\d+)", cmd)
        if match:
            self.click_video_by_number(int(match.group(1)))
            return True
        
        # Video by name
        for prefix in ["открой видео", "включи видео", "выбери видео", "выбери"]:
            if prefix in cmd:
                name = cmd.replace(prefix, "").strip()
                if name:
                    self.find_and_click_video(name)
                    return True
        
        # Close browser
        if "закрой браузер" in cmd:
            self.close_browser()
            return True
        
        return False