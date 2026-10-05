# -*- coding: utf-8 -*-
import torch
import sys
sys.path.insert(0, 'A:/studia/VoiceAssistant/voice_models/miyu')

import utils
from models import SynthesizerTrn
from text.symbols import symbols

def load_model(model_path, config_path):
    config = utils.get_hparams_from_file(config_path)
    model = SynthesizerTrn(
        len(symbols),
        config.data.n_mel_channels,
        config.train.segment_size // config.data.hop_length,
        n_speakers=config.data.n_speakers,
        **config.model
    )
    model.load_state_dict(torch.load(model_path, map_location='cpu'))
    model.eval()
    return model, config

def text_to_speech(text, output_path):
    model, config = load_model('voice_models/miyu/miyu.pth', 'voice_models/miyu/config.json')
    # Простая конвертация текста (без японского токенизатора)
    print(f"VITS: {text}")
    # Здесь нужен японский токенизатор, но для русского текста просто сохраним тишину
    # Полноценная интеграция требует обучения модели на русском
    return False