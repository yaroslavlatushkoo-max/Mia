# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.responses import FileResponse
import edge_tts
import asyncio
import os
import uuid

app = FastAPI()
OUTPUT_DIR = "tts_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.get("/tts")
async def tts(text: str):
    """Лисий голос: медленнее и выше"""
    filename = f"{OUTPUT_DIR}/{uuid.uuid4()}.mp3"
    communicate = edge_tts.Communicate(
        text, 
        "ru-RU-SvetlanaNeural", 
        rate="-12%"
    )
    await communicate.save(filename)
    return FileResponse(filename, media_type="audio/mp3")

if __name__ == "__main__":
    import uvicorn
    print("🦊 Лисий TTS сервер: http://127.0.0.1:5000/tts?text=Привет")
    uvicorn.run(app, host="127.0.0.1", port=5000)