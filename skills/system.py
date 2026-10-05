# -*- coding: utf-8 -*-
import os
import subprocess
import psutil
import pyautogui
import ctypes
import time
import shutil
from config import APPS, PROCESS_MAP
import winreg

class SystemSkills:
    def __init__(self, speech):
        self.speech = speech
        self.found_apps_cache = {}
        self.screenshot_counter = 0
        self.recording = False
    
    def _find_exe_in_path(self, exe_name):
        for path in os.environ.get("PATH", "").split(os.pathsep):
            full_path = os.path.join(path, exe_name)
            if os.path.isfile(full_path):
                return full_path
        return None
    
    def _find_exe_in_registry(self, exe_name):
        paths_to_check = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
        ]
        name_no_ext = exe_name.replace(".exe", "")
        for hkey, subkey in paths_to_check:
            try:
                key = winreg.OpenKey(hkey, subkey)
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        if name_no_ext.lower() in subkey_name.lower():
                            with winreg.OpenKey(key, subkey_name) as app_key:
                                path = winreg.QueryValue(app_key, None)
                                if path and os.path.isfile(path):
                                    return path
                    except:
                        continue
            except:
                continue
        return None
    
    def _search_in_common_dirs(self, exe_name):
        common_dirs = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.path.expandvars("%LOCALAPPDATA%"),
            os.path.expandvars("%APPDATA%"),
            "C:\\Games", "D:\\Games", "E:\\Games",
            "C:\\Program Files (x86)\\Steam\\steamapps\\common",
            "D:\\SteamLibrary\\steamapps\\common",
            "E:\\SteamLibrary\\steamapps\\common",
            "C:\\Program Files\\Epic Games",
        ]
        for base_dir in common_dirs:
            if not os.path.exists(base_dir):
                continue
            for root, dirs, files in os.walk(base_dir):
                depth = root.replace(base_dir, "").count(os.sep)
                if depth > 4:  # Увеличил глубину для игр
                    dirs.clear()
                    continue
                if exe_name.lower() in [f.lower() for f in files]:
                    return os.path.join(root, exe_name)
        return None
    
    def find_app(self, exe_name):
        if exe_name in self.found_apps_cache:
            cached_path = self.found_apps_cache[exe_name]
            if os.path.isfile(cached_path):
                return cached_path
        result = self._find_exe_in_path(exe_name)
        if result:
            self.found_apps_cache[exe_name] = result
            return result
        result = self._find_exe_in_registry(exe_name)
        if result:
            self.found_apps_cache[exe_name] = result
            return result
        result = self._search_in_common_dirs(exe_name)
        if result:
            self.found_apps_cache[exe_name] = result
            return result
        return None
    
    def can_handle(self, command):
        keywords = [
            "открой", "запусти", "включи", "закрой", "выключи",
            "сверни", "разверни", "окно", "переключи",
            "создай файл", "создай папку", "удали файл", "найди файл",
            "обои", "тема", "запись экрана",
            "загрузка", "система", "процессор", "память", "состояние",
            "состояния", "состоянию", "состоянием", "состоянии",
            "загрузки", "загрузку", "загрузке",
            "заблокируй", "выключи компьютер", "перезагрузи",
            "спящий режим", "режим сна", "скриншот",
            "процессы", "пинг", "проверь интернет",
            "альт ф4", "альт эф четыре",
            "калькулятор", "блокнот", "проводник", "браузер",
            "паинт", "ворд", "эксель",
            "телеграм", "стим", "дискорд", "телеграм", "вотсап",
            "покажи рабочий", "рабочий стол",
        ]
        return any(kw in command for kw in keywords)    
    def execute(self, command):
        cmd = command.lower()

        # Direct app opens - try fuzzy search for ANY app
        for prefix in ["открой ", "запусти ", "включи ", "запускай ", "включай ", "пожалуйста ", "запустить "]:
            if prefix in cmd:
                app = cmd.replace(prefix, "").strip()
                if app:
                    self.open_app(app)
                    return True
        
        # Direct app closes
        for prefix in ["закрой ", "выключи ", "останови "]:
            if prefix in cmd:
                app = cmd.replace(prefix, "").strip()
                if app:
                    self.close_app(app)
                    return True
        # Windows
        if any(w in cmd for w in ["сверни все окна", "сверни окна", "сверни все вкладки", "сверни вкладки", "покажи рабочий стол", "рабочий стол", "покажи рабочий", "сверни всё", "сверни"]):
            self.minimize_all()
            return True
        if any(w in cmd for w in ["разверни окна", "восстанови окна"]):
            self.restore_all()
            return True
        if any(w in cmd for w in ["сверни окно", "спрячь окно"]):
            self.minimize_current()
            return True
        if any(w in cmd for w in ["разверни окно", "на весь экран"]):
            self.maximize_current()
            return True
        if any(w in cmd for w in ["переключи окно", "смени окно"]):
            self.switch_window()
            return True
        if any(w in cmd for w in ["окно влево", "прикрепи влево"]):
            self.snap_left()
            return True
        if any(w in cmd for w in ["окно вправо", "прикрепи вправо"]):
            self.snap_right()
            return True
        if any(w in cmd for w in ["закрой текущее окно", "альт ф4", "альт эф четыре"]):
            self.close_current_window()
            return True

        # System info
        if any(w in cmd for w in ["состояние", "состояния", "состоянию", "состоянием", "состоянии", "загрузка", "загрузки", "загрузку", "процессор", "память", "система"]):
            self.system_info()
            return True
        if any(w in cmd for w in ["процессы", "запущенные программы"]):
            self.processes_info()
            return True
        if any(w in cmd for w in ["пинг", "проверь интернет", "скорость интернета"]):
            self.internet_speed_test()
            return True
        
        # Power
        if any(w in cmd for w in ["заблокируй компьютер", "заблокируй пк", "блокировка"]):
            self.lock_pc()
            return True
        if any(w in cmd for w in ["выключи компьютер", "выключи пк", "выруби компьютер"]):
            self.shutdown()
            return True
        if any(w in cmd for w in ["отмена", "отменить выключение", "не выключай"]):
            self.cancel_shutdown()
            return True
        if any(w in cmd for w in ["перезагрузи компьютер", "перезагрузка", "ребут"]):
            self.restart()
            return True
        if any(w in cmd for w in ["спящий режим", "режим сна", "усыпи компьютер", "спать"]):
            self.sleep()
            return True
        
        # Screenshot
        if any(w in cmd for w in ["скриншот", "сделай скрин", "снимок экрана", "заскринь"]):
            self.take_screenshot()
            return True
        
        # Files
        if "создай папку" in cmd:
            name = cmd.replace("создай папку", "").strip()
            if name:
                self.create_folder(os.path.join(os.path.expanduser("~\\Desktop"), name))
                return True
        if "создай файл" in cmd:
            name = cmd.replace("создай файл", "").strip()
            if name:
                self.create_file(os.path.join(os.path.expanduser("~\\Desktop"), name))
                return True
        if "найди файл" in cmd:
            name = cmd.replace("найди файл", "").strip()
            if name:
                self.find_files(name)
                return True
        
        # Themes
        if any(w in cmd for w in ["тёмная тема", "ночная тема"]):
            self.set_dark_theme()
            return True
        if any(w in cmd for w in ["светлая тема", "дневная тема"]):
            self.set_light_theme()
            return True
        
        # Recording
        if any(w in cmd for w in ["начни запись", "записывай экран"]):
            self.start_recording()
            return True
        if any(w in cmd for w in ["останови запись", "стоп запись"]):
            self.stop_recording()
            return True
        
        return False
    
    def _scan_start_menu(self):
        """Найти все программы в меню Пуск"""
        apps = {}
        paths = [
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        ]
        for base in paths:
            if os.path.exists(base):
                for root, dirs, files in os.walk(base):
                    for f in files:
                        if f.endswith(".lnk") or f.endswith(".url"):
                            name = os.path.splitext(f)[0].lower()
                            full_path = os.path.join(root, f)
                            if name not in apps:
                                apps[name] = full_path
        return apps

    def _scan_registry_apps(self):
        """Найти программы через реестр"""
        apps = {}
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        ]
        for hkey, subkey in reg_paths:
            try:
                key = winreg.OpenKey(hkey, subkey)
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        name = winreg.EnumKey(key, i).lower().replace(".exe", "")
                        with winreg.OpenKey(key, name + ".exe") as app_key:
                            path = winreg.QueryValue(app_key, None)
                            if path and os.path.isfile(path):
                                apps[name] = path
                    except:
                        continue
            except:
                continue
        return apps

    def find_app_fuzzy(self, name):
        """Поиск программы по неточному имени"""
        name = name.lower().strip()
        
        if name in self.found_apps_cache:
            return self.found_apps_cache[name]
        
        for key, val in APPS.items():
            if name in key or key in name:
                return val
        
        start_menu = self._scan_start_menu()
        for app_name, app_path in start_menu.items():
            if name in app_name or app_name in name:
                self.found_apps_cache[name] = app_path
                return app_path
        
        registry = self._scan_registry_apps()
        for app_name, app_path in registry.items():
            if name in app_name or app_name in name:
                self.found_apps_cache[name] = app_path
                return app_path
        
        return None

    def open_app(self, app_name):
        app_name = app_name.lower().strip()
        for prefix in ["открой ", "запусти ", "включи ", "запускай ", "включай ", "пожалуйста ", "запустить "]:
            app_name = app_name.replace(prefix, "")
        
        found_path = self.find_app_fuzzy(app_name)
        
        if found_path:
            # Если это игра Steam — запустить Steam
            if "SteamLibrary" in found_path or "steamapps" in found_path:
                self._ensure_steam_running()
            
            print(f"Нашла: {found_path}")
            print(f"Нашла: {found_path}")
            try:
                if found_path.endswith(".lnk") or found_path.endswith(".url"):
                    os.startfile(found_path)
                elif found_path.startswith("ms-"):
                    os.system(f"start {found_path}")
                else:
                    # Для .exe файлов используем startfile (надёжнее)
                    os.startfile(found_path)
                self.speech.speak(f"Открываю {app_name}")
                return True
            except Exception as e:
                print(f"Ошибка запуска: {e}")
        try:
            os.system(f"start {app_name}")
            self.speech.speak(f"Пытаюсь открыть {app_name}")
            return True
        except:
            pass
        
        self.speech.speak(f"Не могу найти программу {app_name}. Попробуйте уточнить название.")
        return False        
    def close_app(self, app_name):
        app_name = app_name.lower().strip()
        for prefix in ["закрой ", "выключи ", "останови "]:
            app_name = app_name.replace(prefix, "")
        
        search_words = app_name.split()
        found = False
        
        # First try exact match from PROCESS_MAP
        mapped = PROCESS_MAP.get(app_name)
        if mapped:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if mapped.lower().replace('.exe', '') in proc.info['name'].lower().replace('.exe', ''):
                        proc.terminate()
                        found = True
                except:
                    pass
        
        # Then try word-by-word match
        if not found:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    proc_name = proc.info['name'].lower().replace('.exe', '')
                    for word in search_words:
                        if len(word) >= 3 and word in proc_name:
                            proc.terminate()
                            found = True
                            break
                except:
                    pass
        
        # Try to find by window title (for apps that spawn child processes)
        if not found:
            import ctypes
            EnumWindows = ctypes.windll.user32.EnumWindows
            GetWindowText = ctypes.windll.user32.GetWindowTextW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible
            GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
            
            def callback(hwnd, _):
                if IsWindowVisible(hwnd):
                    title = ctypes.create_unicode_buffer(512)
                    GetWindowText(hwnd, title, 512)
                    for word in search_words:
                        if len(word) >= 3 and word in title.value.lower():
                            pid = ctypes.c_ulong()
                            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                            try:
                                psutil.Process(pid.value).terminate()
                                nonlocal found
                                found = True
                            except:
                                pass
                            return False
                return True
            
            EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(callback), 0)
        
        if found:
            self.speech.speak(f"Закрыла {app_name}")
        else:
            self.speech.speak(f"{app_name} не запущена")
        return found
    
    def minimize_all(self):
        """Свернуть все окна через Win+D (работает быстрее Win+M)"""
        import ctypes
        # Используем системный вызов для сворачивания
        ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)  # Нажать Win
        ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)  # Нажать D
        ctypes.windll.user32.keybd_event(0x44, 0, 2, 0)  # Отпустить D
        ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)  # Отпустить Win
        self.speech.speak("Все окна свёрнуты")
    
    def restore_all(self):
        pyautogui.keyDown('win')
        pyautogui.press('d')
        pyautogui.keyUp('win')
        self.speech.speak("Окна восстановлены")
    
    def minimize_current(self):
        pyautogui.hotkey('win', 'down')
        self.speech.speak("Окно свёрнуто")
    
    def maximize_current(self):
        pyautogui.hotkey('win', 'up')
        self.speech.speak("Окно развёрнуто")
    
    def switch_window(self):
        pyautogui.keyDown('alt')
        pyautogui.press('tab')
        pyautogui.keyUp('alt')
        self.speech.speak("Переключила окно")
    
    def snap_left(self):
        pyautogui.hotkey('win', 'left')
        self.speech.speak("Окно слева")
    
    def snap_right(self):
        pyautogui.hotkey('win', 'right')
        self.speech.speak("Окно справа")
    
    def close_current_window(self):
        pyautogui.hotkey('alt', 'f4')
        self.speech.speak("Окно закрыто")
    
    def create_folder(self, path):
        try:
            os.makedirs(path, exist_ok=True)
            self.speech.speak(f"Папка создана")
        except Exception as e:
            self.speech.speak(f"Не удалось создать папку")
    
    def create_file(self, path, content=""):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.speech.speak(f"Файл создан")
        except Exception as e:
            self.speech.speak(f"Не удалось создать файл")
    
    def find_files(self, name, search_path=None):
        if search_path is None:
            search_path = os.path.expanduser("~")
        found = []
        for root, dirs, files in os.walk(search_path):
            if len(found) > 10:
                break
            for f in files:
                if name.lower() in f.lower():
                    found.append(os.path.join(root, f))
        if found:
            count = len(found)
            self.speech.speak(f"Найдено {count} файлов")
            for i, f in enumerate(found[:3], 1):
                self.speech.speak(f"Файл {i}: {os.path.basename(f)}")
        else:
            self.speech.speak("Ничего не найдено")
        return found
    
    def set_wallpaper(self, image_path):
        try:
            if not os.path.isfile(image_path):
                self.speech.speak("Файл обоев не найден")
                return
            ctypes.windll.user32.SystemParametersInfoW(20, 0, image_path, 3)
            self.speech.speak("Обои изменены")
        except:
            self.speech.speak("Не удалось сменить обои")
    
    def set_dark_theme(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize", 
                0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            self.speech.speak("Тёмная тема включена")
        except:
            self.speech.speak("Не удалось сменить тему")
    
    def set_light_theme(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize", 
                0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            self.speech.speak("Светлая тема включена")
        except:
            self.speech.speak("Не удалось сменить тему")
    
    def start_recording(self):
        if self.recording:
            self.speech.speak("Запись уже идёт")
            return
        self.recording = True
        pyautogui.hotkey('win', 'alt', 'r')
        self.speech.speak("Запись экрана началась")
    
    def stop_recording(self):
        if not self.recording:
            self.speech.speak("Запись не ведётся")
            return
        self.recording = False
        pyautogui.hotkey('win', 'alt', 'r')
        self.speech.speak("Запись экрана остановлена")
    
    def _num_to_words(self, n):
        words = {
            0: "ноль", 1: "один", 2: "два", 3: "три", 4: "четыре",
            5: "пять", 6: "шесть", 7: "семь", 8: "восемь", 9: "девять",
            10: "десять", 11: "одиннадцать", 12: "двенадцать",
            13: "тринадцать", 14: "четырнадцать", 15: "пятнадцать",
            16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
            19: "девятнадцать", 20: "двадцать", 30: "тридцать",
            40: "сорок", 50: "пятьдесят", 60: "шестьдесят",
            70: "семьдесят", 80: "восемьдесят", 90: "девяносто",
            100: "сто",
        }
        if n in words:
            return words[n]
        if n < 100:
            tens = (n // 10) * 10
            ones = n % 10
            return words[tens] + " " + words[ones]
        return str(n)
    def system_info(self):
        cpu = int(psutil.cpu_percent(interval=1))
        mem = psutil.virtual_memory()
        mem_used = round(mem.used/1024**3)
        mem_total = round(mem.total/1024**3)
        battery = psutil.sensors_battery()
        
        cpu_word = self._num_to_words(cpu)
        mem_used_word = self._num_to_words(mem_used)
        mem_total_word = self._num_to_words(mem_total)
        
        info = f"Процессор загружен на {cpu_word} процентов. "
        info += f"Память занято {mem_used_word} из {mem_total_word} гигабайт. "
        
        if battery:
            bat_word = self._num_to_words(int(battery.percent))
            info += f"Заряд батареи {bat_word} процентов."
        
        self.speech.speak(info)
    def processes_info(self):
        procs = []
        for proc in psutil.process_iter(['name', 'memory_percent']):
            try:
                procs.append((proc.info['name'], proc.info['memory_percent']))
            except:
                pass
        procs.sort(key=lambda x: x[1] if x[1] else 0, reverse=True)
        top5 = procs[:5]
        self.speech.speak("Топ пять процессов по памяти")
        for name, mem in top5:
            if name:
                self.speech.speak(f"{name} {round(mem, 1)} процентов")
    
    def internet_speed_test(self):
        import requests
        try:
            start = time.time()
            requests.get("https://google.com", timeout=5)
            latency = round((time.time() - start) * 1000)
            self.speech.speak(f"Пинг до Google {latency} миллисекунд")
        except:
            self.speech.speak("Не удалось проверить интернет")
    
    def lock_pc(self):
        os.system("rundll32.exe user32.dll,LockWorkStation")
        self.speech.speak("Компьютер заблокирован")
    
    def shutdown(self):
        self.speech.speak("Выключаю компьютер через шестьдесят секунд")
        os.system("shutdown /s /t 60")
    
    def cancel_shutdown(self):
        os.system("shutdown /a")
        self.speech.speak("Выключение отменено")
    
    def sleep(self):
        self.speech.speak("Перевожу в спящий режим")
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    
    def restart(self):
        self.speech.speak("Перезагружаю компьютер через шестьдесят секунд")
        os.system("shutdown /r /t 60")
    
    def take_screenshot(self):
        self.screenshot_counter += 1
        desktop = os.path.expanduser("~\\Desktop")
        path = os.path.join(desktop, f"screenshot_{self.screenshot_counter}.png")
        screenshot = pyautogui.screenshot()
        screenshot.save(path)
        self.speech.speak(f"Скриншот {self.screenshot_counter} сохранён на рабочий стол")
    
    def volume_up(self):
        for _ in range(10):
            pyautogui.press("volumeup")
        self.speech.speak("Громкость увеличена")
    
    def volume_down(self):
        for _ in range(10):
            pyautogui.press("volumedown")
        self.speech.speak("Громкость уменьшена")
    
    def volume_mute(self):
        pyautogui.press("volumemute")
        self.speech.speak("Звук отключен")
    
    def brightness_up(self):
        try:
            import subprocess
            # PowerShell команда для увеличения яркости
            cmd = 'powershell -c "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(0, 100)"'
            subprocess.run(cmd, shell=True, capture_output=True)
            self.speech.speak("Яркость увеличена")
        except:
            try:
                # Альтернативный метод через Win + A (Центр уведомлений) и скрипт
                pyautogui.hotkey('win', 'a')
                import time
                time.sleep(0.5)
                pyautogui.press('tab')
                pyautogui.press('right', presses=5)
                pyautogui.hotkey('win', 'a')
                self.speech.speak("Яркость увеличена")
            except:
                self.speech.speak("Не удалось изменить яркость. Попробуйте нажать Fn + F6")
    
    def brightness_down(self):
        try:
            import subprocess
            cmd = 'powershell -c "$m = Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness; $m.WmiSetBrightness(0, ($m.CurrentBrightness - 20))"'
            subprocess.run(cmd, shell=True, capture_output=True)
            self.speech.speak("Яркость уменьшена")
        except:
            try:
                pyautogui.hotkey('win', 'a')
                import time
                time.sleep(0.5)
                pyautogui.press('tab')
                pyautogui.press('left', presses=5)
                pyautogui.hotkey('win', 'a')
                self.speech.speak("Яркость уменьшена")
            except:
                self.speech.speak("Не удалось изменить яркость. Попробуйте нажать Fn + F5")
    def _ensure_steam_running(self):
        """Проверить, что Steam запущен, и если нет — запустить и войти"""
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and 'steam' in proc.info['name'].lower():
                    return True
            
            steam_paths = [
                "C:\\Program Files (x86)\\Steam\\Steam.exe",
                "A:\\Steam\\Steam.exe",
                "D:\\Steam\\Steam.exe",
            ]
            for path in steam_paths:
                if os.path.isfile(path):
                    print("Запускаю Steam...")
                    self.speech.speak("Запускаю Steam")
                    subprocess.Popen(path, shell=True)
                    
                    # Ждать появления окна Steam
                    for i in range(10):
                        time.sleep(2)
                        # Проверить, есть ли окно Steam
                        try:
                            import ctypes
                            hwnd = ctypes.windll.user32.FindWindowW(None, "Steam")
                            if hwnd:
                                print("Окно Steam найдено!")
                                # Развернуть окно
                                ctypes.windll.user32.ShowWindow(hwnd, 9)
                                ctypes.windll.user32.SetForegroundWindow(hwnd)
                                time.sleep(1)
                                break
                        except:
                            pass
                    
                    # Кликнуть по центру экрана для выбора аккаунта
                    pyautogui.click(x=960, y=400)
                    time.sleep(2)
                    self.speech.speak("Steam готов. Выберите аккаунт")
                    return True
            
            print("Steam не найден")
            return False
        except Exception as e:
            print(f"Ошибка Steam: {e}")
            return False
