from __future__ import annotations

"""Structured Observation (Task 5, CORE_MIGRATION.md §5/§7).

Observation = the honest, structured result of ONE concrete tool execution.
ExecutionTrace = the history of observations over a task. The two layers
must not be conflated:

    REGISTERED   -> the tool exists in ToolRegistry
    IMPLEMENTED  -> the tool has a real executor
    EXECUTED     -> the executor actually ran and returned
    VERIFIED     -> Verification accepted the outcome (separate stage!)

An Observation NEVER fabricates success:
  * no executor            -> NOT_IMPLEMENTED
  * policy block           -> BLOCKED
  * wall-clock timeout     -> TIMEOUT
  * raised / returned err  -> FAILURE
  * cancelled              -> CANCELLED
  * only an actual positive executor result -> SUCCESS
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ObservationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    TIMEOUT = "TIMEOUT"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    #: вход не прошёл валидацию схемы — executor НЕ вызывался
    REJECTED = "REJECTED"


@dataclass
class Observation:
    """Result of one tool execution attempt."""

    tool: str
    status: ObservationStatus
    summary: str = ""
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0          # measured seconds; 0.0 until execution ends
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Derived semantics — single source of truth for downstream layers.
    # ------------------------------------------------------------------
    @property
    def executed(self) -> bool:
        """True only when the executor ACTUALLY RAN and returned.

        NOT_IMPLEMENTED / BLOCKED / TIMEOUT are explicitly NOT executed:
        on timeout the worker may still be running in a background thread,
        so we cannot claim its completion.
        """
        return self.status in (ObservationStatus.SUCCESS, ObservationStatus.FAILURE)

    @property
    def succeeded(self) -> bool:
        """EXECUTED and positively reported by the executor.

        This is NOT VERIFIED — verification is a separate stage
        (Verification layer). A tool that returns failure or was never
        implemented can never produce this flag.
        """
        return self.status == ObservationStatus.SUCCESS

    @property
    def verified_hint(self) -> bool:
        """Honest per-tool verification hint carried from the executor.

        Kept separate from `succeeded` so legacy adapters can report
        'attempted but unconfirmed' (verified=False) without faking it.
        """
        return bool(self.metadata.get("verified", False))

    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "status": self.status.value if isinstance(self.status, ObservationStatus) else str(self.status),
            "summary": self.summary,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration": self.duration,
            "metadata": dict(self.metadata),
        }

    # ------------------------------------------------------------------
    # Task 6: compact structured context for observation-dependent execution.
    # This is the SMALL, explicit carrier of the previous attempt's outcome
    # into the next planner/step decision — deliberately NOT the whole raw
    # trace and NOT a second state store (ExecutionTrace stays the history).
    # ------------------------------------------------------------------
    def to_step_context(self) -> Dict[str, Any]:
        """Structured one-step context derived from this Observation."""
        error = None if self.succeeded else (self.stderr or self.summary or f"{self.status.value}: {self.tool}")
        return {
            "tool": self.tool,
            "status": self.status.value if isinstance(self.status, ObservationStatus) else str(self.status),
            "success": self.succeeded,
            "executed": self.executed,
            "verified": bool(self.metadata.get("verified", False)),
            "summary": self.summary,
            "error": error,
            "duration": self.duration,
            "data": self.data,
        }

    # ------------------------------------------------------------------
    # Legacy-compatible read-only properties. Baseline consumers (core
    # tests, legacy callers) treat registry output as ToolResult-shaped;
    # Observation is the new source of truth and these properties are a
    # pure derivation — no second state is introduced.
    # ------------------------------------------------------------------
    @property
    def success(self) -> bool:
        return self.succeeded

    @property
    def error(self) -> Optional[str]:
        if self.succeeded:
            return None
        return self.stderr or self.summary or f"{self.status.value}: {self.tool}"

    @property
    def data(self) -> Dict[str, Any]:
        """Lossless view of executor payload for legacy consumers."""
        d = dict(self.metadata.get("data") or {})
        if not d:
            if self.stdout:
                d["stdout"] = self.stdout
            d.update({k: v for k, v in self.metadata.items()
                      if k not in ("verified", "data")})
        return d

    @property
    def verified(self) -> bool:
        return bool(self.metadata.get("verified", False))

    def to_trace_observation(self) -> Dict[str, Any]:
        """Backward-compatible mapping into ExecutionTrace observations.

        Existing core layers (Verifier / Responder / tests) consume dicts
        shaped like {"success", "data", "error", "verified"}. This is the
        explicit boundary conversion — the legacy shape stays derived from
        the structured Observation, never invented independently.
        """
        success = self.succeeded
        return {
            "success": success,
            "data": self.data,
            "error": None if success else (self.stderr or self.summary or f"{self.status.value}: {self.tool}"),
            # EXECUTED != VERIFIED: never invent verification from a mere
            # successful execution. `verified` is taken ONLY from the
            # executor's honest hint; absent hint -> False (UNKNOWN),
            # which existing Verifier treats as unconfirmed and checks
            # independently against expected postconditions.
            "verified": bool(self.metadata.get("verified", False)),
            # New structured fields (additive; old consumers ignore them):
            "status": self.status.value,
            "duration": self.duration,
        }

    # ------------------------------------------------------------------
    # Factories — deterministic constructors for every honest outcome.
    # ------------------------------------------------------------------
    @staticmethod
    def not_implemented(tool: str, reason: str = "") -> "Observation":
        return Observation(
            tool=tool,
            status=ObservationStatus.NOT_IMPLEMENTED,
            summary=reason or f"Tool '{tool}' is registered but has no executor.",
            metadata={"registered": True, "implemented": False},
        )

    @staticmethod
    def blocked(tool: str, reason: str) -> "Observation":
        return Observation(
            tool=tool,
            status=ObservationStatus.BLOCKED,
            summary=reason,
            metadata={"policy_blocked": True},
        )

    @staticmethod
    def timeout(tool: str, limit_seconds: float, started_at: Optional[float] = None) -> "Observation":
        now = started_at if started_at is not None else time.time()
        return Observation(
            tool=tool,
            status=ObservationStatus.TIMEOUT,
            summary=f"Executor exceeded {limit_seconds}s wall-clock limit.",
            duration=round(now - started_at, 6) if started_at is not None else round(limit_seconds, 6),
            metadata={"timeout_limit": limit_seconds, "worker_may_still_run": True},
        )

    @staticmethod
    def cancelled(tool: str, reason: str = "Cancelled before execution.") -> "Observation":
        return Observation(
            tool=tool,
            status=ObservationStatus.CANCELLED,
            summary=reason,
        )

    @staticmethod
    def failure(tool: str, error: str, duration: float = 0.0,
                stdout: str = "", stderr: str = "",
                metadata: Optional[Dict[str, Any]] = None) -> "Observation":
        return Observation(
            tool=tool,
            status=ObservationStatus.FAILURE,
            summary=error,
            stdout=stdout,
            stderr=stderr or error,
            duration=duration,
            metadata=metadata or {},
        )
