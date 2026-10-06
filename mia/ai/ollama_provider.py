from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from http.client import HTTPException
from socket import timeout as SocketTimeout
from typing import Any, Dict, List, Optional, Tuple

from .lifecycle import (
    DEFAULT_KEEP_ALIVE,
    HEALTH_TIMEOUT_SECONDS,
    UNLOAD_KEEP_ALIVE,
    AvailabilityResult,
    HealthResult,
)
from .provider import (
    AIProvider,
    MALFORMED_RESPONSE,
    MODEL_UNAVAILABLE,
    OLLAMA_UNAVAILABLE,
    PROVIDER_ERROR,
    PROVIDER_TIMEOUT,
    ModelResponse,
)


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder:7b"
    timeout: int = 120
    #: Health/availability probe timeout (seconds). Contract default: 1s.
    health_timeout: float = HEALTH_TIMEOUT_SECONDS
    #: Centralized keep-alive default ("5m") — defined once in lifecycle.py.
    keep_alive: str = DEFAULT_KEEP_ALIVE


class OllamaProvider(AIProvider):
    """Ollama transport + single-resident-model lifecycle.

    The ONLY place in the architecture that knows about Ollama HTTP API,
    health probes, model availability and keep_alive residency switching.
    Designed for reuse: one instance handles many generate() calls and
    tracks the currently resident model across them.
    """

    def __init__(self, config: Optional[OllamaConfig] = None):
        self.config = config or OllamaConfig()
        #: Currently resident model on the server (None = unknown/none).
        self.current_model: Optional[str] = None

    # ------------------------------------------------------------------
    # Transport (single choke point; maps all failures to error codes)
    # ------------------------------------------------------------------

    def _request(self, path: str, payload: Optional[Dict[str, Any]] = None,
                 timeout: Optional[float] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """Perform one HTTP request against Ollama.

        Returns (parsed_json, error_message, error_code). Never raises.
        """
        url = f"{self.config.base_url}{path}"
        try:
            if payload is None:
                req = urllib.request.Request(url, method="GET")
                data = None
            else:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            with urllib.request.urlopen(req, timeout=timeout, data=data) as response:
                raw = response.read().decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return None, f"invalid JSON body from {path}", MALFORMED_RESPONSE
            if not isinstance(parsed, dict):
                return None, f"non-object JSON body from {path}", MALFORMED_RESPONSE
            return parsed, None, None
        except SocketTimeout as e:
            return None, f"timeout contacting {url}: {e}", PROVIDER_TIMEOUT
        except urllib.error.HTTPError as e:
            # Server reachable but rejected the request → provider-side error.
            return None, f"HTTP {e.code} from {url}: {e.reason}", PROVIDER_ERROR
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, SocketTimeout) or "timed out" in str(reason).lower():
                return None, f"timeout contacting {url}: {reason}", PROVIDER_TIMEOUT
            return None, f"cannot reach {url}: {reason}", OLLAMA_UNAVAILABLE
        except (OSError, HTTPException) as e:
            # ConnectionResetError etc. — transport-level failure.
            return None, f"transport error for {url}: {e}", PROVIDER_ERROR
        except Exception as e:  # defensive: providers must never raise outward
            return None, f"unexpected provider error: {e}", PROVIDER_ERROR

    def _safe_request(self, path, payload=None, timeout=None):
        """Absolute no-raise guarantee: even a broken/mocked _request that
        raises an unexpected exception is converted to a structured failure."""
        try:
            return self._request(path=path, payload=payload, timeout=timeout)
        except Exception as e:
            return None, f"unexpected provider error: {e}", PROVIDER_ERROR

    # ------------------------------------------------------------------
    # Health & availability
    # ------------------------------------------------------------------

    def health(self) -> HealthResult:
        """GET /api/tags with short (default 1s) timeout. Never raises."""
        parsed, err, code = self._safe_request("/api/tags", timeout=self.config.health_timeout)
        if err is not None:
            return HealthResult(healthy=False, error=f"{code}: {err}")
        return HealthResult(healthy=True)

    def list_models(self) -> Tuple[List[str], Optional[str]]:
        """Return (model_names, error). Names include tags, e.g. 'qwen3:4b'."""
        parsed, err, code = self._safe_request("/api/tags", timeout=self.config.health_timeout)
        if err is not None:
            return [], f"{code}: {err}"
        models_raw = parsed.get("models")
        if models_raw is None:
            # Real Ollama always returns {"models": [...]} (possibly empty).
            # An absent key on a healthy server is treated as an empty list;
            # truly malformed bodies are already caught by _request.
            return [], None
        if not isinstance(models_raw, list):
            return [], f"{MALFORMED_RESPONSE}: 'models' is not a list"
        names: List[str] = []
        for entry in models_raw:
            if isinstance(entry, dict):
                name = entry.get("name")
                if isinstance(name, str) and name:
                    names.append(name)
            elif isinstance(entry, str) and entry:
                names.append(entry)
        return names, None

    def is_model_available(self, model: str) -> AvailabilityResult:
        """Check presence of a concrete model via /api/tags. No auto-download."""
        names, err = self.list_models()
        if err is not None:
            return AvailabilityResult(available=False, model=model, error=err)
        if model in names:
            return AvailabilityResult(available=True, model=model)
        return AvailabilityResult(
            available=False, model=model,
            error=f"{MODEL_UNAVAILABLE}: '{model}' not present in Ollama tags {names}",
        )

    # ------------------------------------------------------------------
    # Lifecycle: single resident model with keep_alive switching
    # ------------------------------------------------------------------

    def unload_model(self, model: str) -> bool:
        """Explicitly unload a resident model (keep_alive='0'). Best effort."""
        parsed, err, code = self._safe_request(
            "/api/generate",
            payload={"model": model, "keep_alive": UNLOAD_KEEP_ALIVE},
            timeout=self.config.health_timeout,
        )
        return err is None

    def ensure_resident(self, target: str) -> Optional[ModelResponse]:
        """Make `target` the resident model following the A→B protocol:

            A resident → A keep_alive=0 → B keep_alive=5m → B resident

        Same-model requests are a no-op (no pointless switching). Resident
        state is updated only after a successful load; a failed switch
        leaves state honest (unknown current model), never stale-wrong.
        Returns None on success or a structured failure ModelResponse.
        """
        if self.current_model == target:
            return None  # already resident — reuse, no switching

        previous = self.current_model

        # Probe availability BEFORE touching residency (never attempt to
        # load a model the server does not have; no auto-download).
        availability = self.is_model_available(target)
        if not availability.available:
            err = availability.error or ""
            if err.startswith(OLLAMA_UNAVAILABLE):
                self.current_model = None  # server unreachable: residency unknown
                return ModelResponse.failure(OLLAMA_UNAVAILABLE, err, model=target)
            if err.startswith(MALFORMED_RESPONSE):
                return ModelResponse.failure(MALFORMED_RESPONSE, err, model=target)
            # MODEL_UNAVAILABLE (or conservative verdict on empty list):
            # unload the old resident to free VRAM, then fail. Residency
            # becomes unknown until the next successful load.
            if previous:
                self.unload_model(previous)
                self.current_model = None
            return ModelResponse.failure(MODEL_UNAVAILABLE, err, model=target)

        # Unload previous resident (best effort; failure here does not
        # corrupt state — we proceed and validate via the load itself).
        if previous:
            self.unload_model(previous)

        # Load target into residency with default keep_alive.
        parsed, err, code = self._safe_request(
            "/api/generate",
            payload={
                "model": target,
                "prompt": "",
                "stream": False,
                "keep_alive": self.config.keep_alive,
            },
            timeout=self.config.timeout,
        )
        if err is not None:
            # Switch failed: do NOT claim target is resident.
            self.current_model = None
            return ModelResponse.failure(code or PROVIDER_ERROR, err, model=target)

        self.current_model = target
        return None

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        model: Optional[str] = None,
        keep_alive: Optional[str] = None,
    ) -> ModelResponse:
        target = model or self.config.model
        eff_keep_alive = keep_alive or self.config.keep_alive

        # 1. Lifecycle: ensure the requested model is resident.
        cfg_keep_alive = self.config.keep_alive
        self.config.keep_alive = eff_keep_alive
        try:
            switch_failure = self.ensure_resident(target)
        finally:
            self.config.keep_alive = cfg_keep_alive
        if switch_failure is not None:
            return switch_failure

        # 2. Build generation request.
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "model": target,
            "prompt": full_prompt,
            "stream": False,
            "keep_alive": eff_keep_alive,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7,
            },
        }

        # 3..6. Send, handle timeouts/unavailability, validate structure.
        parsed, err, code = self._safe_request("/api/generate", payload=payload,
                                          timeout=self.config.timeout)
        if err is not None:
            if code in (OLLAMA_UNAVAILABLE, PROVIDER_TIMEOUT, PROVIDER_ERROR):
                # Transport died or timed out: residency is no longer known.
                self.current_model = None
            return ModelResponse.failure(code or PROVIDER_ERROR, err, model=target)

        # Structure validation: must carry a string "response" field.
        if "response" not in parsed or not isinstance(parsed["response"], str):
            return ModelResponse.failure(
                MALFORMED_RESPONSE,
                "/api/generate response missing string 'response' field",
                model=target,
            )

        tokens = parsed.get("eval_count", 0)
        try:
            tokens_used = int(tokens or 0)
        except (TypeError, ValueError):
            tokens_used = 0

        # 7. Structured success result.
        return ModelResponse(
            text=parsed["response"].strip(),
            model=target,
            tokens_used=tokens_used,
        )