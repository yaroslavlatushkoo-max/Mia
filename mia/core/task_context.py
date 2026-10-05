from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum
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

    created_at: float = field(default_factory=time.time)

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
            "created_at": self.created_at,
        }