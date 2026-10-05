from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

from .provider import AIProvider, ModelResponse


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder:7b"
    timeout: int = 120


class OllamaProvider(AIProvider):
    def __init__(self, config: Optional[OllamaConfig] = None):
        self.config = config or OllamaConfig()

    def generate(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 512) -> ModelResponse:
        try:
            url = f"{self.config.base_url}/api/generate"

            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            payload = {
                "model": self.config.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.7,
                },
            }

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                raw = response.read().decode("utf-8", errors="ignore")
                parsed = json.loads(raw)

            return ModelResponse(
                text=parsed.get("response", "").strip(),
                model=self.config.model,
                tokens_used=int(parsed.get("eval_count", 0) or 0),
            )

        except urllib.error.URLError as e:
            return ModelResponse(
                text="",
                model=self.config.model,
                error=f"Ollama connection error: {e}"
            )
        except Exception as e:
            return ModelResponse(
                text="",
                model=self.config.model,
                error=str(e)
            )