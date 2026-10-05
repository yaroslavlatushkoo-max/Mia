# -*- coding: utf-8 -*-
from speech import Speech
from skills.system import SystemSkills
from skills.web import WebSkills
from skills.utils import UtilsSkills
from skills.media import MediaSkills
from skills.organizer import OrganizerSkills
from skills.ai_brain import AIBrainSkill
from skills.browser import BrowserSkills
from skills.eyes import EyesSkill
from skills.skill_loader import SkillLoader
from skills.memory import MemorySkill
from skills.system_tools import SystemTools
from skills.live_observer import LiveObserver
from skills.response_templates import ResponseTemplates
import config
import re
import threading
import time
import subprocess
import os
import shutil
import requests
import signal
import pygetwindow as gw
import pyautogui

class VoiceAssistant:
    def __init__(self):
        self.speech = Speech()
        self.running = True
        self.skills = {
            'browser': BrowserSkills(self.speech),
            'templates': ResponseTemplates(self.speech),
            'web': WebSkills(self.speech),
            'tools': SystemTools(self.speech),
            'media': MediaSkills(self.speech),
            'system': SystemSkills(self.speech),
            'observer': LiveObserver(self.speech),
            'organizer': OrganizerSkills(self.speech),
            'utils': UtilsSkills(self.speech),
            'memory': MemorySkill(self.speech),
            'eyes': EyesSkill(self.speech),
            'ai': AIBrainSkill(self.speech, {
                "AI_ENABLED": config.AI_ENABLED,
                "AI_PROVIDER": config.AI_PROVIDER,
                "AI_API_KEY": config.AI_API_KEY,
                "AI_MODEL": config.AI_MODEL,
            }),
        }
        self.skill_loader = SkillLoader()
        self.rvc_process = None
    
    def find_name(self, text):
        text_lower = text.lower()
        for alias in config.ASSISTANT_ALIASES:
            if alias in text_lower:
                return alias
        return None
    
    def process_command(self, command):
        cmd = command.lower().strip()

        if self.skills['eyes'].can_handle(cmd):
            return self.skills['eyes'].execute(cmd)
        if self.skills['browser'].can_handle(cmd):
            return self.skills['browser'].execute(cmd)
        if self.skills['web'].can_handle(cmd):
            result = self.skills['web'].execute(cmd)
            if result:
                return True
        
        sites_sorted = sorted(config.SITES.items(), key=lambda x: len(x[0]), reverse=True)
        for site_name, site_url in sites_sorted:
            pattern = r'(?<!\w)' + re.escape(site_name) + r'(?!\w)'
            if re.search(pattern, cmd):
                self.skills['web'].open_site(site_url)
                return True
        
        if self.skills['system'].can_handle(cmd):
            return self.skills['system'].execute(cmd)
        if self.skills['media'].can_handle(cmd):
            return self.skills['media'].execute(cmd)
        if self.skills['organizer'].can_handle(cmd):
            return self.skills['organizer'].execute(cmd)
        
        open_match = re.search(r"(?:открой|запусти|включи|запускай|включай) (.+)", cmd)
        if open_match:
            target = open_match.group(1).strip()
            for site_name, site_url in sites_sorted:
                if site_name in target:
                    self.skills['web'].open_site(site_url)
                    return True
            self.skills['system'].open_app(target)
            return True
        
        close_match = re.search(r"(?:закрой|выключи|останови) (.+)", cmd)
        if close_match:
            self.skills['system'].close_app(close_match.group(1))
            return True

        skill = self.skill_loader.find_skill(cmd)
        if skill:
            prompt = f"Выполни навык '{skill['name']}':\n{skill['body']}\n\nКоманда пользователя: {command}"
            try:
                import ollama
                response = ollama.chat(
                    model="qwen2.5:7b",
                    messages=[{"role": "user", "content": prompt}],
                    options={"max_tokens": 80}
                )
                answer = response["message"]["content"]
                answer = answer.replace("\n", " ").replace("*", "")[:200]
                self.speech.speak(answer)
                return True
            except:
                pass

        if self.skills['memory'].can_handle(cmd):
            return self.skills['memory'].execute(cmd)
        if self.skills['utils'].can_handle(cmd):
            return self.skills['utils'].execute(cmd)
        if self.skills['tools'].can_handle(cmd):
            return self.skills['tools'].execute(cmd)
        if self.skills['observer'].can_handle(cmd):
            return self.skills['observer'].execute(cmd)
        if self.skills['templates'].can_handle(cmd):
            return self.skills['templates'].execute(cmd)
        if self.skills['ai'].can_handle(cmd):
            return self.skills['ai'].execute(cmd)
        
        return False
    
    def _close_rvc_gracefully(self):
        """Закрывает RVC-сервер и вкладку браузера"""
        print("🎤 Закрываю RVC сервер...")
        
        # 1. Закрываем через API
        try:
            requests.get("http://127.0.0.1:7865/shutdown", timeout=2)
            print("🎤 RVC остановлен через API")
            time.sleep(1)
        except:
            pass
        
        # 2. Закрываем вкладку через Selenium
        try:
            from selenium import webdriver
            from selenium.webdriver.edge.options import Options
            
            print("🔍 Подключаюсь к браузеру через Selenium...")
            options = Options()
            options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            
            driver = webdriver.Edge(options=options)
            
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                if "7865" in driver.current_url or "RVC" in driver.title:
                    driver.close()
                    print("🧹 Вкладка RVC закрыта через Selenium")
                    break
            
            driver.quit()
        except Exception as e:
            print(f"⚠ Selenium не сработал: {e}")
            # Запасной способ через pygetwindow
            try:
                windows = gw.getWindowsWithTitle("RVC")
                for w in windows:
                    if "python" not in w.title.lower():
                        w.close()
                        print("🧹 Окно RVC закрыто через pygetwindow")
            except:
                pass
        
        # 3. Закрываем процесс по порту
        try:
            result = subprocess.run(
                ['netstat', '-ano', '|', 'findstr', ':7865'],
                capture_output=True,
                text=True,
                shell=True
            )
            lines = result.stdout.strip().split('\n')
            pids = set()
            for line in lines:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    if pid.isdigit():
                        pids.add(int(pid))
            
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                    print(f"🎤 Убит процесс RVC (PID: {pid})")
                except:
                    try:
                        os.system(f'taskkill /F /PID {pid} 2>nul')
                        print(f"🎤 Принудительно убит RVC (PID: {pid})")
                    except:
                        pass
            time.sleep(1)
        except Exception as e:
            print(f"⚠ Не удалось найти процесс по порту: {e}")
        
        # 4. Убиваем консоль RVC
        try:
            os.system('taskkill /F /FI "WINDOWTITLE eq RVC*" /IM python.exe 2>nul')
        except:
            pass
        
        print("🎤 RVC сервер полностью остановлен")
        return True
    
    def run(self):
        print("🎤 Запускаю RVC сервер...")
        rvc_path = r"A:\rvc_env\Retrieval-based-Voice-Conversion-WebUI"
        rvc_python = r"A:\rvc_env\Retrieval-based-Voice-Conversion-WebUI\venv\Scripts\python.exe"
        
        # Убиваем старые процессы RVC
        try:
            result = subprocess.run(
                ['netstat', '-ano', '|', 'findstr', ':7865'],
                capture_output=True,
                text=True,
                shell=True
            )
            lines = result.stdout.strip().split('\n')
            for line in lines:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    if pid.isdigit():
                        os.system(f'taskkill /F /PID {pid} 2>nul')
        except:
            pass
        
        # Запускаем RVC сервер
        self.rvc_process = subprocess.Popen(
            [rvc_python, "infer-web.py"],
            cwd=rvc_path,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        
        rvc_ready = False
        for i in range(45):
            time.sleep(1)
            try:
                r = requests.post(
                    "http://127.0.0.1:7865/run/infer_change_voice",
                    json={"data": ["shikimori.pth", 0.33, 0.33]},
                    timeout=3
                )
                if r.status_code == 200:
                    rvc_ready = True
                    break
            except:
                pass
        
        if rvc_ready:
            print(f"🎤 RVC сервер готов! (за {i+1} сек)")
        else:
            print("⚠ RVC сервер не запустился")
        
        self.speech.speak("Привет! Я Мия, твой персональный ассистент.")
        
        import web_ui
        web_ui.mia_instance = self
        threading.Thread(target=web_ui.start_server, daemon=True).start()
        time.sleep(1)
        
        while self.running:
            command = self.speech.listen(timeout=10)
            if not command:
                continue
            
            cmd_lower = command.lower()
            
            exit_words = ["выход", "пока", "завершить работу", "выключись", "хватит"]
            should_exit = any(w in cmd_lower for w in exit_words)
            if should_exit and "покажи" not in cmd_lower and "показал" not in cmd_lower and "показ" not in cmd_lower:
                self.speech.speak("До свидания! Я буду скучать!")
                self._close_rvc_gracefully()
                self.running = False
                break
            
            name = self.find_name(command)
            if name:
                if self.speech.is_speaking:
                    self.speech.is_speaking = False
                    print("👤 Barge-in: Мия замолкает...")
                
                clean_cmd = cmd_lower.replace(name, "").strip()
                if clean_cmd:
                    if not self.process_command(clean_cmd):
                        self.speech.speak("Извини, я не поняла команду")

if __name__ == "__main__":
    assistant = VoiceAssistant()
    assistant.run()