"""Task 4 — Model Lifecycle: shared lifecycle constants and result structures.

Single source of truth for keep_alive defaults and health/availability
result types used by providers. No transport logic lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Centralized lifecycle defaults (do NOT scatter these values across files)
# ---------------------------------------------------------------------------

#: Default residency window for a loaded model on the server.
DEFAULT_KEEP_ALIVE = "5m"

#: Value that instructs Ollama to immediately unload a resident model.
UNLOAD_KEEP_ALIVE = "0"

#: Base timeout (seconds) for health / model-availability probes.
HEALTH_TIMEOUT_SECONDS = 1


@dataclass
class HealthResult:
    """Structured result of a provider health probe. Never raises outward."""

    healthy: bool
    error: Optional[str] = None


@dataclass
class AvailabilityResult:
    """Structured result of a concrete-model availability check."""

    available: bool
    model: str = ""
    error: Optional[str] = None
