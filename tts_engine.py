# -*- coding: utf-8 -*-
import os
import torch
import soundfile as sf
import time
import pyttsx3

class SileroTTS:
    def __init__(self):
        self.device = torch.device('cpu')
        self.model = None
        self.sample_rate = 48000
        self.speaker = "baya"
        self.temp_file = "temp_speech.wav"
        self.load_model()
        self.fallback = pyttsx3.init()
    
    def load_model(self):
        print("Zagruzhayu model Silero...")
        try:
            model_path = "model.pt"
            if not os.path.exists(model_path):
                print("Skachivayu...")
                torch.hub.download_url_to_file(
                    "https://models.silero.ai/models/tts/ru/v4_ru.pt", model_path)
            
            self.model = torch.package.PackageImporter(model_path).load_pickle("tts_models", "model")
            self.model.to(self.device)
            print("Gotovo!")
        except Exception as e:
            print(f"Oshibka: {e}")
            self.model = None
    
    def speak(self, text):
        if self.model is None:
            self.fallback.say(text)
            self.fallback.runAndWait()
            return False
        
        try:
            audio = self.model.apply_tts(
                text=text,
                speaker=self.speaker,
                sample_rate=self.sample_rate
            )
            
            # Save to WAV file
            audio_np = audio.numpy()
            sf.write(self.temp_file, audio_np, self.sample_rate)
            
            # Play with system default player
            os.system(f'start /min powershell -c "(New-Object Media.SoundPlayer \'{self.temp_file}\').PlaySync();"')
            
            return True
        except Exception as e:
            print(f"Silero error: {e}, using fallback")
            self.fallback.say(text)
            self.fallback.runAndWait()
            return False
    
    def set_voice(self, speaker):
        valid = ["baya", "xenia", "aidar", "eugene", "kseniya", "random"]
        if speaker in valid:
            self.speaker = speaker
            print(f"Golos: {speaker}")

if __name__ == "__main__":
    tts = SileroTTS()
    
    print("\nTestiruyu golosa:\n")
    
    for voice in ["baya", "xenia", "random"]:
        tts.set_voice(voice)
        print(f"  [{voice}] Govoryu...")
        tts.speak("Privet! Menya zovut Miya. Eto test golosa.")
        time.sleep(1)
    
    print("\nKakoy golos luchshe? (baya/xenia)")
    choice = input("> ").strip().lower()
    if choice:
        tts.set_voice(choice if choice in ["baya", "xenia"] else "baya")
        tts.speak(f"Golos {tts.speaker} vybran. Otlichno!")