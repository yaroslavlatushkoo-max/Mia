# -*- coding: utf-8 -*-
import os
import subprocess
import psutil
import pyautogui
import webbrowser
import socket
import platform
import requests
import shutil
import tempfile
import zipfile
import ctypes
from datetime import datetime

class SystemTools:
    def __init__(self, speech):
        self.speech = speech
    
    # ========== ИНТЕРНЕТ И СЕТЬ ==========
    
    def check_internet(self):
        """Проверка интернета"""
        try:
            requests.get("https://google.com", timeout=3)
            return True
        except:
            return False
    
    def get_ip(self):
        """Получить IP-адрес"""
        try:
            ip = requests.get("https://api.ipify.org", timeout=3).text
            return ip
        except:
            return "неизвестно"
    
    def get_network_info(self):
        """Информация о сети"""
        hostname = socket.gethostname()
        ip_local = socket.gethostbyname(hostname)
        ip_public = self.get_ip()
        online = "онлайн" if self.check_internet() else "офлайн"
        
        return f"Компьютер: {hostname}. Локальный IP: {ip_local}. Внешний IP: {ip_public}. Статус: {online}"
    
    def open_network_settings(self):
        """Открыть сетевые настройки"""
        os.system("start ms-settings:network")
        self.speech.speak("Открываю сетевые настройки")
    
    def open_wifi_settings(self):
        """Открыть настройки Wi-Fi"""
        os.system("start ms-settings:network-wifi")
        self.speech.speak("Открываю настройки Wi-Fi")
    
    # ========== ПИТАНИЕ ==========
    
    def get_battery_info(self):
        """Детальная информация о батарее"""
        battery = psutil.sensors_battery()
        if battery:
            status = "заряжается" if battery.power_plugged else "разряжается"
            time_left = f"{battery.secsleft // 3600} ч {(battery.secsleft % 3600) // 60} мин" if battery.secsleft > 0 else "неизвестно"
            return f"Заряд: {battery.percent}%. Статус: {status}. Осталось: {time_left}"
        return "Батарея не обнаружена"
    
    def set_power_mode(self, mode="balanced"):
        """Установить режим питания"""
        modes = {
            "high": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",  # Высокая производительность
            "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",  # Сбалансированный
            "saving": "a1841308-3541-4fab-bc81-f71556f20b4a",  # Экономия
        }
        if mode in modes:
            os.system(f'powercfg /setactive {modes[mode]}')
            self.speech.speak(f"Режим питания изменён")
        else:
            self.speech.speak("Режим не найден")
    
    # ========== ЗВУК И МЕДИА ==========
    
    def set_volume(self, level):
        """Установить громкость (0-100)"""
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(level / 100, None)
            self.speech.speak(f"Громкость: {level}%")
        except:
            # Простой способ — нажатия клавиш
            for _ in range(50):
                pyautogui.press("volumedown")
            for _ in range(level // 2):
                pyautogui.press("volumeup")
            self.speech.speak(f"Громкость установлена")
    
    def get_volume(self):
        """Получить текущую громкость"""
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            return round(volume.GetMasterVolumeLevelScalar() * 100)
        except:
            return 50
    
    # ========== ДИСКИ И ПАМЯТЬ ==========
    
    def get_disk_info(self):
        """Информация о дисках"""
        info = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                info.append(
                    f"Диск {part.device} ({part.mountpoint}): "
                    f"свободно {usage.free // (1024**3)} ГБ из {usage.total // (1024**3)} ГБ"
                )
            except:
                pass
        return "\n".join(info) if info else "Диски не найдены"
    
    def get_ram_info(self):
        """Информация о RAM"""
        mem = psutil.virtual_memory()
        return (
            f"Всего: {mem.total // (1024**3)} ГБ. "
            f"Доступно: {mem.available // (1024**3)} ГБ. "
            f"Используется: {mem.percent}%"
        )
    
    def get_cpu_info(self):
        """Информация о процессоре"""
        cpu = psutil.cpu_percent(interval=1)
        freq = psutil.cpu_freq()
        cores = psutil.cpu_count()
        
        info = f"Загрузка: {cpu}%. Ядер: {cores}. "
        if freq:
            info += f"Частота: {freq.current:.0f} МГц."
        return info
    
    # ========== ПРИЛОЖЕНИЯ И ПРОЦЕССЫ ==========
    
    def kill_process(self, name):
        """Убить процесс по имени"""
        killed = 0
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if name.lower() in proc.info['name'].lower():
                    proc.kill()
                    killed += 1
            except:
                pass
        return killed
    
    def get_running_apps(self):
        """Список запущенных приложений"""
        apps = []
        for proc in psutil.process_iter(['name', 'memory_percent']):
            try:
                name = proc.info['name']
                if name and proc.info['memory_percent'] > 0.1:
                    apps.append(name.replace('.exe', ''))
            except:
                pass
        return list(set(apps))[:20]  # Уникальные, топ-20
    
    def start_program(self, program):
        """Запустить программу по имени исполняемого файла"""
        try:
            subprocess.Popen(program, shell=True)
            return True
        except:
            return False
    
    # ========== СКРИНШОТЫ И ЗАПИСЬ ==========
    
    def screenshot_to_clipboard(self):
        """Скриншот в буфер обмена"""
        pyautogui.hotkey('win', 'shift', 's')
        self.speech.speak("Выберите область для скриншота")
    
    def start_screen_recording(self):
        """Начать запись экрана"""
        pyautogui.hotkey('win', 'alt', 'r')
        self.speech.speak("Запись экрана")
    
    # ========== РАБОТА С ФАЙЛАМИ ==========
    
    def open_folder(self, path):
        """Открыть папку в проводнике"""
        if os.path.exists(path):
            os.startfile(path)
            self.speech.speak("Открываю папку")
        else:
            self.speech.speak("Папка не найдена")
    
    def clean_temp_files(self):
        """Очистить временные файлы"""
        try:
            temp_dir = tempfile.gettempdir()
            count = 0
            for item in os.listdir(temp_dir):
                try:
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                    count += 1
                except:
                    pass
            self.speech.speak(f"Очищено {count} временных файлов")
        except:
            self.speech.speak("Не удалось очистить временные файлы")
    
    def empty_recycle_bin(self):
        """Очистить корзину"""
        try:
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0)
            self.speech.speak("Корзина очищена")
        except:
            self.speech.speak("Не удалось очистить корзину")
    
    # ========== СИСТЕМНАЯ ИНФОРМАЦИЯ ==========
    
    def get_system_info(self):
        """Полная информация о системе"""
        info = [
            f"Система: {platform.system()} {platform.release()}",
            f"Компьютер: {platform.node()}",
            f"Процессор: {platform.processor()}",
            f"ОЗУ: {psutil.virtual_memory().total // (1024**3)} ГБ",
            f"Python: {platform.python_version()}",
        ]
        return "\n".join(info)
    
    def get_uptime(self):
        """Время работы системы"""
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        
        return f"Компьютер работает {days} дн {hours} ч {minutes} мин"
    
    def can_handle(self, command):
        keywords = [
            "интернет", "сеть", "ip", "вайфай", "wifi",
            "батарея", "заряд", "питание", "режим питания",
            "громкость", "звук", "диск", "память", "процессор",
            "процессы", "программы", "програмы", "приложения", "запущены",
            "очисти временные", "очисти корзину",
            "скриншот", "запись экрана", "информация о системе",
	    "информация системе", "информация о системе", "характеристики",
            "сколько работает", "время работы",
        ]
        return any(kw in command for kw in keywords)
    
    def execute(self, command):
        cmd = command.lower()
        
        if "информация о системе" in cmd or "информация системе" in cmd or "характеристики" in cmd:
            info = self.get_system_info()
            self.speech.speak(info[:200])
            return True

        # Интернет и сеть
        if any(w in cmd for w in ["интернет", "сеть", "онлайн"]):
            info = self.get_network_info()
            self.speech.speak(info)
            return True
        if "вайфай" in cmd or "wifi" in cmd:
            self.open_wifi_settings()
            return True
        
        # Батарея
        if any(w in cmd for w in ["батарея", "заряд", "зарядка"]):
            info = self.get_battery_info()
            self.speech.speak(info)
            return True
        
        # Память и процессор
        if "процессор" in cmd or "цп" in cmd:
            info = self.get_cpu_info()
            self.speech.speak(info)
            return True
        if "память" in cmd or "озу" in cmd or "ram" in cmd:
            info = self.get_ram_info()
            self.speech.speak(info)
            return True
        if "диск" in cmd:
            info = self.get_disk_info()
            self.speech.speak(info[:200])
            return True
        
        # Процессы
        if "процессы" in cmd or "запущено" in cmd:
            apps = self.get_running_apps()
            if apps:
                self.speech.speak(f"Запущено {len(apps)} приложений: {', '.join(apps[:10])}")
            return True
        
        # Очистка
        if "очисти временные" in cmd:
            self.clean_temp_files()
            return True
        if "очисти корзину" in cmd:
            self.empty_recycle_bin()
            return True
        
        # Системная информация
        if "информация о системе" in cmd or "характеристики" in cmd:
            info = self.get_system_info()
            self.speech.speak(info[:200])
            return True
        if "сколько работает" in cmd or "время работы" in cmd:
            info = self.get_uptime()
            self.speech.speak(info)
            return True
        
        return False