import os
import subprocess
from pathlib import Path

def extract_audio(video_path, output_path):
    """Извлечь аудио из видео"""
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "22050", "-ac", "1",
        output_path
    ])

def split_audio(input_path, output_dir, segment_length=10):
    """Нарезать на сегменты"""
    os.makedirs(output_dir, exist_ok=True)
    
    subprocess.run([
        "ffmpeg", "-i", input_path,
        "-f", "segment",
        "-segment_time", str(segment_length),
        "-c", "copy",
        os.path.join(output_dir, "segment_%03d.wav")
    ])

# Использование
extract_audio("senko_asmr.mp4", "senko_raw.wav")
split_audio("senko_raw.wav", "senko_dataset/", segment_length=10)