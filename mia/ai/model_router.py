from __future__ import annotations

from typing import Dict, Optional

from .provider import AIProvider, ModelResponse

# Role → model mapping. These are the baseline model names already defined
# in this module (config.py has no Ollama model entries; config.py is the
# legacy Windows app and must not be touched by Task 4).
CHAT_ROLE = "chat"
CODER_ROLE = "coder"


class ModelRouter:
    """Pure role -> provider/model routing.

    Responsibilities (ONLY):
        - map a role ("chat"/"coder") to a provider instance bound to a model;
        - forward generate() to the selected provider.

    Everything server-side (transport, probes, residency policy, error-code
    mapping) belongs exclusively to the concrete provider implementation,
    never here.

    The router talks to providers through the AIProvider abstraction and
    has no compile-time dependency on any concrete transport. Reusable:
    one instance serves many calls; providers are created once.
    """

    def __init__(
        self,
        chat_provider: Optional[AIProvider] = None,
        coder_provider: Optional[AIProvider] = None,
        models: Optional[Dict[str, str]] = None,
    ):
        # Lazy import ONLY for default construction; injected providers
        # (any AIProvider) never require Ollama code paths.
        if chat_provider is None or coder_provider is None:
            from .ollama_provider import OllamaConfig, OllamaProvider

            defaults = {"chat": "qwen2.5:7b", "coder": "qwen2.5-coder:7b"}
            merged = {**defaults, **(models or {})}
            if chat_provider is None:
                chat_provider = OllamaProvider(OllamaConfig(model=merged["chat"]))
            if coder_provider is None:
                coder_provider = OllamaProvider(OllamaConfig(model=merged["coder"]))

        self.chat_provider: AIProvider = chat_provider
        self.coder_provider: AIProvider = coder_provider

        # Backward-compatible attribute names (baseline API).
        self.default_chat_model = getattr(
            getattr(chat_provider, "config", None), "model", "qwen2.5:7b"
        )
        self.coder_model = getattr(
            getattr(coder_provider, "config", None), "model", "qwen2.5-coder:7b"
        )

    # ------------------------------------------------------------------
    # Routing contract
    # ------------------------------------------------------------------

    def resolve(self, preferred: str = CHAT_ROLE) -> AIProvider:
        """role → provider. Unknown roles fall back to chat."""
        return self.coder_provider if preferred == CODER_ROLE else self.chat_provider

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        preferred: str = CHAT_ROLE,
    ) -> ModelResponse:
        provider = self.resolve(preferred)
        return provider.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )