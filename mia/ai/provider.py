from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelResponse:
    text: str
    model: str
    tokens_used: int = 0
    error: Optional[str] = None


class AIProvider:
    def generate(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 512) -> ModelResponse:
        raise NotImplementedError