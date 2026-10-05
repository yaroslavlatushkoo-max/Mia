# -*- coding: utf-8 -*-
import os
import json
import time
import threading
import numpy as np
from config import LANGUAGE, ASSISTANT_ALIASES

# Silero TTS
import torch
import soundfile as sf

class Speech:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        # Используем voice_cache напрямую (там лежат все 130 файлов)
        self.cache_dir = os.path.join(self.base_dir, "voice_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Индекс кэша для быстрого поиска
        self.cache_index = {}
        self._build_cache_index()
        
        # Vosk STT setup
        try:
            from vosk import Model, KaldiRecognizer
            import sounddevice as sd
            
            model_path = os.path.join(self.base_dir, "vosk-model", "vosk-model-small-ru-0.22")
            if not os.path.exists(model_path):
                model_path = os.path.join(self.base_dir, "vosk-model")
            
            if os.path.exists(model_path):
                print("Загружаю Vosk модель...")
                self.vosk_model = Model(model_path)
                self.vosk_recognizer = KaldiRecognizer(self.vosk_model, 16000)
                self.use_vosk = True
                print("Vosk готов!")
            else:
                print("Vosk модель не найдена, использую Google")
                self.use_vosk = False
        except Exception as e:
            print(f"Vosk error: {e}, использую Google")
            self.use_vosk = False
        
        # Silero TTS setup
        self.device = torch.device('cpu')
        self.model = None
        self.sample_rate = 48000
        self.speaker = "xenia"
        self.temp_file = os.path.join(self.base_dir, "temp_speech.wav")
        self.is_speaking = False
        self._load_silero()
        
        # RVC Voice Changer (Shikimori)
        self.use_rvc = True
        
        # Google Speech fallback
        if not self.use_vosk:
            import speech_recognition as sr
            self.recognizer = sr.Recognizer()
            self.microphone = sr.Microphone()
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
    
    def _load_silero(self):
        model_path = os.path.join(self.base_dir, "model.pt")
        if os.path.exists(model_path):
            try:
                self.model = torch.package.PackageImporter(model_path).load_pickle("tts_models", "model")
                self.model.to(self.device)
                print("Silero TTS loaded!")
            except:
                self.model = None
    
    def _build_cache_index(self):
        """Построить индекс кэша для мгновенного поиска"""
        if not os.path.exists(self.cache_dir):
            return
        
        for filename in os.listdir(self.cache_dir):
            if not filename.endswith(".wav"):
                continue
            name_without_ext = filename[:-4]
            # Разбиваем на слова
            words = name_without_ext.lower().replace('_', ' ').split()
            for word in words:
                if len(word) > 2:
                    if word not in self.cache_index:
                        self.cache_index[word] = []
                    self.cache_index[word].append(filename)
    
    def _to_cyrillic(self, text):
        trans = {
            'a': 'а', 'b': 'б', 'c': 'ц', 'd': 'д', 'e': 'е', 'f': 'ф',
            'g': 'г', 'h': 'х', 'i': 'и', 'j': 'й', 'k': 'к', 'l': 'л',
            'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п', 'q': 'к', 'r': 'р',
            's': 'с', 't': 'т', 'u': 'у', 'v': 'в', 'w': 'в', 'x': 'кс',
            'y': 'и', 'z': 'з',
        }
        
        result = []
        for ch in text:
            lower = ch.lower()
            if lower in trans:
                result.append(trans[lower])
            elif ch.isdigit():
                digits = {
                    '0': 'ноль', '1': 'один', '2': 'два', '3': 'три', '4': 'четыре',
                    '5': 'пять', '6': 'шесть', '7': 'семь', '8': 'восемь', '9': 'девять'
                }
                result.append(digits.get(ch, ch) + ' ')
            elif 'A' <= ch <= 'Z' or 'a' <= ch <= 'z':
                continue
            else:
                result.append(ch)
        
        return ''.join(result)
    
    def _speak_fallback(self, text):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', 170)
            engine.setProperty('volume', 0.9)
            engine.say(text)
            engine.runAndWait()
        except:
            pass
    
    def _speak_silero(self, text):
        """Синтез через Silero (основа для RVC) — генерирует ВСЁ предложение целиком"""
        # Очищаем текст
        clean_text = self._to_cyrillic(text)
        clean_text = clean_text.replace("  ", " ")
        
        if self.model and len(clean_text) < 500:
            try:
                audio = self.model.apply_tts(
                    text=clean_text,
                    speaker=self.speaker,
                    sample_rate=self.sample_rate,
                    put_accent=True,
                    put_yo=True
                )
                sf.write(self.temp_file, audio.numpy(), self.sample_rate)
                return
            except Exception as e:
                print(f"Silero error: {e}")
                self._speak_fallback(text)
                return
        else:
            self._speak_fallback(text)
    
    def _rvc_convert(self, audio_path):
        """Конвертировать голос через RVC в Shikimori"""
        try:
            import requests
            import soundfile as sf
            
            if not os.path.exists(audio_path):
                print(f"RVC: файл {audio_path} не найден")
                return False
            
            data, sr = sf.read(audio_path)
            if len(data) == 0:
                print("RVC: аудио пустое")
                return False
            
            response = requests.post(
                "http://127.0.0.1:7865/run/infer_convert",
                json={
                    "data": [
                        0,
                        audio_path,
                        10,
                        None,
                        "rmvpe",
                        "added_IVF243_Flat_nprobe_1_shikimori_v2.index",
                        "",
                        0.8,
                        3,
                        0,
                        1,
                        0.33,
                    ]
                },
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("data") and len(result["data"]) > 1:
                    audio_info = result["data"][1]
                    if isinstance(audio_info, dict) and audio_info.get("name"):
                        file_url = "http://127.0.0.1:7865/file=" + audio_info["name"]
                        audio_resp = requests.get(file_url)
                        if audio_resp.status_code == 200:
                            with open(self.temp_file, "wb") as f:
                                f.write(audio_resp.content)
                            return True
            else:
                print(f"RVC error: {response.status_code}")
            return False
        except Exception as e:
            print(f"RVC error: {e}")
            return False
    
    def _find_in_cache(self, text):
        """Поиск по индексу кэша"""
        if not self.cache_index:
            return None
        
        # Нормализуем текст
        search_text = text.lower().strip()
        for char in '.,!?;:()[]{}"\'':
            search_text = search_text.replace(char, '')
        search_words = search_text.split()
        
        # Ищем в индексе
        candidates = {}
        for word in search_words:
            if len(word) > 2 and word in self.cache_index:
                for filename in self.cache_index[word]:
                    candidates[filename] = candidates.get(filename, 0) + 1
        
        if not candidates:
            return None
        
        # Берём файл с наибольшим количеством совпадений
        best_file = max(candidates, key=candidates.get)
        return os.path.join(self.cache_dir, best_file)
    
    def speak(self, text):
        """Главный метод синтеза речи с кэшированием"""
        self.is_speaking = True
        print(f"Miia: {text}")
        
        # 1. Проверяем кэш
        cached_file = self._find_in_cache(text)
        if cached_file and os.path.exists(cached_file):
            os.system(f'powershell -c "(New-Object Media.SoundPlayer \'{cached_file}\').PlaySync();"')
            self.is_speaking = False
            print(f"🎤 Из кэша!")
            return
        
        # 2. Если в кэше нет — генерируем через Silero + RVC
        print("🎤 Генерация через RVC...")
        self._speak_silero(text)
        
        # 3. Конвертируем через RVC
        if self.use_rvc and os.path.exists(self.temp_file):
            success = self._rvc_convert(self.temp_file)
            if success:
                os.system(f'powershell -c "(New-Object Media.SoundPlayer \'{self.temp_file}\').PlaySync();"')
                self.is_speaking = False
                return
        
        # 4. Если RVC не сработал — Silero напрямую
        if os.path.exists(self.temp_file):
            os.system(f'powershell -c "(New-Object Media.SoundPlayer \'{self.temp_file}\').PlaySync();"')
        
        self.is_speaking = False
    
    def listen(self, timeout=10):
        while self.is_speaking:
            time.sleep(0.1)
        time.sleep(0.3)
        
        if self.use_vosk:
            return self._listen_vosk(timeout)
        else:
            return self._listen_google(timeout)
    
    def _listen_vosk(self, timeout=10):
        import sounddevice as sd
        
        print("🎤 Слушаю (Vosk)...")
        
        try:
            silence_frames = 0
            silence_threshold = 10
            spoken = False
            full_text = ""
            
            def callback(indata, frames, time_info, status):
                nonlocal silence_frames, spoken, full_text
                
                if status:
                    print(f"Audio error: {status}")
                
                audio_bytes = indata.tobytes()
                
                if self.vosk_recognizer.AcceptWaveform(audio_bytes):
                    result = json.loads(self.vosk_recognizer.Result())
                    text = result.get("text", "").strip()
                    if text:
                        full_text += " " + text
                        spoken = True
                        silence_frames = 0
                else:
                    partial = json.loads(self.vosk_recognizer.PartialResult())
                    text = partial.get("partial", "").strip()
                    if text:
                        spoken = True
                        silence_frames = 0
                    else:
                        silence_frames += 1
            
            with sd.InputStream(samplerate=16000, channels=1, dtype='int16', blocksize=480, callback=callback):
                start_time = time.time()
                
                while True:
                    time.sleep(0.05)
                    
                    if spoken and silence_frames >= silence_threshold:
                        break
                    
                    if not spoken and (time.time() - start_time) > timeout:
                        break
                    
                    if spoken and silence_frames > 30:
                        break
            
            full_text = full_text.strip().lower()
            if full_text:
                print(f"👤 {full_text}")
                return full_text
            
        except Exception as e:
            print(f"Vosk listen error: {e}")
        
        return None
    
    def _listen_google(self, timeout=5):
        import speech_recognition as sr
        
        try:
            with self.microphone as source:
                print("🎤 Слушаю (Google)...")
                audio = self.recognizer.listen(source, timeout=timeout)
            text = self.recognizer.recognize_google(audio, language="ru-RU")
            print(f"👤 {text}")
            return text.lower()
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            print("❌ Не распознано")
            return None
        except sr.RequestError:
            print("❌ Ошибка сервиса")
            return None