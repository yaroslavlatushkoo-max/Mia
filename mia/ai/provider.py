from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Task 4 error codes (provider-level contract). Every one of these implies
# success == False. A successful response MUST carry error == None.
OLLAMA_UNAVAILABLE = "OLLAMA_UNAVAILABLE"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
PROVIDER_ERROR = "PROVIDER_ERROR"


@dataclass
class ModelResponse:
    text: str = ""
    model: str = ""
    tokens_used: int = 0
    error: Optional[str] = None
    #: Machine-readable provider error code (one of the constants above)
    #: when error is set; None on success.
    error_code: Optional[str] = None

    def __post_init__(self) -> None:
        # Normalization: an empty-string error must never masquerade as a
        # failure marker.
        if self.error is not None and not str(self.error).strip():
            self.error = None
        # Contract enforcement: it is impossible to hold success=True +
        # error="..." simultaneously.
        self._success = self.error is None

    @property
    def success(self) -> bool:
        """Derived, never stored — guarantees invariant with `error`."""
        return self._success

    @classmethod
    def failure(cls, error_code: str, message: str = "", model: str = "") -> "ModelResponse":
        return cls(
            text="",
            model=model,
            tokens_used=0,
            error=f"{error_code}: {message}" if message else error_code,
            error_code=error_code,
        )


class AIProvider:
    """Abstract provider contract.

    Concrete providers (e.g. OllamaProvider) additionally implement the
    lifecycle surface introduced by Task 4:

        health() -> HealthResult
        is_model_available(model: str) -> AvailabilityResult
        generate(..., model=None, keep_alive=None) -> ModelResponse

    Transport/lifecycle errors are converted into structured failures;
    exceptions escaping a concrete provider are treated as bugs.
    """

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
    ) -> ModelResponse:
        raise NotImplementedError