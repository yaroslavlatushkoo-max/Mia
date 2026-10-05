import torch
import soundfile as sf
from silero import silero_tts


LANGUAGE = "ru"
SPEAKER = "v5_5_ru"
SAMPLE_RATE = 48000

TEXT = "Привет. Это тест нового голосового движка Мии."


print("=" * 60)
print("SILERO V5 TEST")
print("=" * 60)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print(f"Device: {device}")
print(f"CUDA:   {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU:    {torch.cuda.get_device_name(0)}")

print("\nLoading Silero V5...")

model, example_text = silero_tts(
    language=LANGUAGE,
    speaker=SPEAKER,
    device=device
)

print("Model loaded.")

print("\nGenerating speech...")
audio = model.apply_tts(
    text=TEXT,
    speaker="xenia",
    sample_rate=SAMPLE_RATE
)

output = "test_silero.wav"
sf.write(output, audio.cpu().numpy(), SAMPLE_RATE)

print(f"\nSaved: {output}")
print("SILERO TEST COMPLETE")