from __future__ import annotations

from typing import Optional

from .provider import AIProvider, ModelResponse
from .ollama_provider import OllamaProvider, OllamaConfig


class ModelRouter:
    def __init__(self):
        self.default_chat_model = "qwen2.5:7b"
        self.coder_model = "qwen2.5-coder:7b"

        self.chat_provider = OllamaProvider(OllamaConfig(model=self.default_chat_model))
        self.coder_provider = OllamaProvider(OllamaConfig(model=self.coder_model))

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        preferred: str = "chat",
    ) -> ModelResponse:
        provider = self.chat_provider if preferred == "chat" else self.coder_provider
        return provider.generate(prompt=prompt, system_prompt=system_prompt, max_tokens=max_tokens)