from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum
import threading
import time
import uuid


class TaskMode(str, Enum):
    COMPANION = "COMPANION"
    ASSISTANT = "ASSISTANT"
    AGENT = "AGENT"


class TaskDomain(str, Enum):
    GENERAL = "GENERAL"
    CHARACTER = "CHARACTER"
    MEMORY = "MEMORY"
    SYSTEM = "SYSTEM"
    TECHNICAL = "TECHNICAL"
    FILES = "FILES"
    BROWSER = "BROWSER"
    WEB = "WEB"
    WORLD = "WORLD"


class CancelToken:
    """Task 6: cooperative cancellation signal.

    Honest semantics (Python cannot safely force-kill an arbitrary running
    thread — we never claim otherwise):

        cancel requested
        -> already-running blocking tools may finish on their own;
        -> AgentLoop checks this token at every boundary (before each new
           tool attempt, after each attempt, before replan/next action) and
           stops launching NEW work;
        -> the loop terminates with status CANCELLED.

    Thread-safe via a plain Event flag. No exception is raised by cancel().
    """

    __slots__ = ("_event", "_reason")

    def __init__(self, reason: str = "", cancelled: bool = False) -> None:
        """Task 6 bugfix: a token constructed WITH a reason is by definition
        an already-cancelled signal (that is how callers used it:
        `CancelToken("late")`). Previously the event was never set here, so
        `cancelled` stayed False forever for such tokens. Default call with
        no reason keeps the old "armed but not fired" semantics."""
        self._event = threading.Event()
        self._reason = reason or ""
        if cancelled or reason:
            self._event.set()

    def cancel(self, reason: str = "") -> bool:
        """Request cancellation. Returns True if THIS call flipped the flag."""
        if reason and not self._reason:
            self._reason = reason
        flipped = not self._event.is_set()
        self._event.set()
        return flipped

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    # Method-style alias for readability at check sites.
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason or "Cancelled."


@dataclass
class TaskContext:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "local_user"
    session_id: str = "default_session"

    raw_input: str = ""
    source: str = "text"  # text / voice / event / vision
    language: str = "ru"

    intent: str = "UNKNOWN"
    mode: TaskMode = TaskMode.ASSISTANT
    domain: TaskDomain = TaskDomain.GENERAL
    complexity: str = "C1"

    entities: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0

    risk: str = "low"
    requires_confirmation: bool = False
    # HITL resume flag (migration To-do #1): set by Session when the user
    # explicitly confirmed the pending task. Policy consumes it inside
    # check_tool — confirmation is evaluated BY Policy, never around it.
    confirmed: bool = False

    # Execution budget flags (CORE_MIGRATION.md: CostEstimator output is
    # carried in the context so Planner/AgentLoop read requirements from
    # TaskContext instead of re-deriving them). Populated by
    # CostEstimator.estimate(); defaults keep old constructions valid.
    budget_requires_llm: bool = False
    budget_requires_tool: bool = False
    budget_requires_planner: bool = False
    budget_confidence: float = 0.0
    budget_reasons: list = field(default_factory=list)

    # ------------------------------------------------------------------
    # Task 6 — reliability state (execution-boundary data, NOT a second
    # AgentLoop). Semantics are fixed and documented once here:
    #   logical step        = one PlanStep of the current plan;
    #   execution attempt   = one real launch of a tool for that step
    #                         (retry creates a NEW attempt);
    #   tool call           = one Registry.run() dispatch (== executed attempt);
    #   replan              = one Planner.replan() cycle after verification
    #                         failure.
    # Budgets (all enforced in AgentLoop, none reset by retry/replan):
    #   total_budget  -> caps TOTAL EXECUTION ATTEMPTS (incl. retries);
    #                    None => derived from ExecutionTrace.max_steps.
    #   tool_budget   -> caps actual dispatched tool calls; 0/None =>
    #                    unlimited within total_budget (C0/C1 budgets set
    #                    tool_budget=0 honestly meaning "no tools expected").
    #   max_retries_per_step -> per-logical-step bounded retry. FINAL Task 6
    #                    contract: N == at most N retries after attempt 1
    #                    (0 => attempt 1 -> STOP; 1 => attempt 1 -> retry ->
    #                    attempt 2 -> STOP). It is NOT a max-attempts value.
    #                    None => AgentLoop default (one retry).
    # Counters are written ONLY by AgentLoop; consumers read them.
    # ------------------------------------------------------------------
    total_budget: Optional[int] = None
    tool_budget: Optional[int] = None
    max_retries_per_step: Optional[int] = None

    attempts_used: int = 0
    tool_calls: int = 0
    retries_used: int = 0
    replans_used: int = 0

    # Cooperative cancellation (see CancelToken). Deliberately EXCLUDED from
    # to_dict(): an Event is not serializable and cancellation is a runtime
    # signal, not persisted task state.
    cancel_token: Optional[CancelToken] = field(default=None, repr=False)

    # Observation-dependent execution: compact structured context of the
    # PREVIOUS attempt (status/summary/error/verification/data), rebuilt by
    # AgentLoop after every attempt. This is the small carrier into the next
    # planner/step decision — not a copy of the trace, not a second history.
    previous_observation: Optional[Dict[str, Any]] = None

    created_at: float = field(default_factory=time.time)

    def request_cancel(self, reason: str = "") -> None:
        """Convenience: mark this task cancelled (cooperative, see CancelToken).

        Task 6 bugfix: the lazily created token must be actually FLIPPED.
        Previously `CancelToken(reason)` only stored the reason without
        setting the event, so every boundary check (`cancelled`,
        `AgentLoop._is_cancelled`) stayed False and cancellation was dead
        code at runtime. Now lazy creation goes through `cancel()`.
        """
        if self.cancel_token is None:
            self.cancel_token = CancelToken()
        self.cancel_token.cancel(reason)

    @property
    def cancelled(self) -> bool:
        return bool(self.cancel_token and self.cancel_token.cancelled)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "raw_input": self.raw_input,
            "source": self.source,
            "language": self.language,
            "intent": self.intent,
            "mode": self.mode.value,
            "domain": self.domain.value,
            "complexity": self.complexity,
            "entities": self.entities,
            "confidence": self.confidence,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "confirmed": self.confirmed,
            "budget_requires_llm": self.budget_requires_llm,
            "budget_requires_tool": self.budget_requires_tool,
            "budget_requires_planner": self.budget_requires_planner,
            "budget_confidence": self.budget_confidence,
            "budget_reasons": list(self.budget_reasons),
            # Task 6 (additive): budgets, counters and observation context.
            # cancel_token is intentionally NOT serialized (runtime signal).
            "total_budget": self.total_budget,
            "tool_budget": self.tool_budget,
            "max_retries_per_step": self.max_retries_per_step,
            "attempts_used": self.attempts_used,
            "tool_calls": self.tool_calls,
            "retries_used": self.retries_used,
            "replans_used": self.replans_used,
            "cancelled": self.cancelled,
            "previous_observation": (
                dict(self.previous_observation)
                if self.previous_observation is not None
                else None
            ),
            "created_at": self.created_at,
        }