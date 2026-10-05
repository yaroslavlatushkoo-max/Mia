from __future__ import annotations

"""Session + HITL state (migration To-do #1).

A Session carries the working conversation state and at most one
pending task. A pending task is a TaskContext that could not proceed
automatically:

- WAITING_CONFIRMATION — Policy blocked a high-risk action; the user's
  explicit confirmation must RESUME THE SAME TASK (same task_id, same
  entities, same plan goal), not re-plan it from scratch;
- WAITING_CLARIFICATION — Router confidence was too low to act safely;
  the user's answer refines the original request and reroutes it.

Confirmation is never a Policy bypass: resume sets ctx.confirmed=True
and the normal AgentLoop/Policy enforcement point re-evaluates every
rule (denied intents stay denied even after confirmation).
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PendingState(str, Enum):
    NONE = "NONE"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    WAITING_CLARIFICATION = "WAITING_CLARIFICATION"


CONFIRM_WORDS = {
    "да", "yes", "y", "подтверждаю", "подтвердить", "ок", "okay", "окей",
    "хорошо", "согласен", "согласна", "делай", "выполняй", "продолжай",
    "разрешаю", "го", "+",
}

CANCEL_WORDS = {
    "нет", "no", "n", "отмена", "отмени", "отменить", "cancel",
    "не надо", "не нужно", "передумал", "передумала", "забудь",
    "stop", "стоп",
}


@dataclass
class PendingTask:
    """A suspended task kept inside the session."""

    task_id: str
    raw_input: str
    intent: str
    state: PendingState
    reason: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "raw_input": self.raw_input,
            "intent": self.intent,
            "state": self.state.value,
            "reason": self.reason,
            "entities": dict(self.entities),
            "created_at": self.created_at,
        }


@dataclass
class Session:
    session_id: str = "default_session"
    user_id: str = "local_user"

    # Working conversation state (short-lived messages for this session).
    messages: List[Dict[str, str]] = field(default_factory=list)

    pending_task: Optional[PendingTask] = None

    # --------------------------------------------------------------
    # Working state helpers
    # --------------------------------------------------------------
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        # Keep the working window bounded (session-local, deterministic).
        if len(self.messages) > 40:
            del self.messages[: len(self.messages) - 40]

    def clear_pending(self):
        self.pending_task = None

    # --------------------------------------------------------------
    # HITL classification of the user's next utterance
    # --------------------------------------------------------------
    def classify_response(self, text: str) -> str:
        """Deterministic classification: 'confirm' / 'cancel' / 'other'.

        Exact short-answer matching keeps confirm/cancel detection
        side-effect free (no fuzzy substring traps like 'ненужно' vs
        long unrelated requests).
        """
        t = text.strip().lower().rstrip("!.? ,")
        if t in CONFIRM_WORDS:
            return "confirm"
        if t in CANCEL_WORDS:
            return "cancel"
        return "other"

    # --------------------------------------------------------------
    # Resume logic (used by Orchestrator.handle before routing new input)
    # --------------------------------------------------------------
    def try_resume(self, user_text: str) -> Optional[Dict[str, Any]]:
        """Interpret `user_text` against the pending task.

        Returns a resume descriptor or None when the pending task cannot
        be resumed with this text (caller should then treat the input as
        a brand-new request; an unconfirmed pending task stays pending,
        so Policy still protects any later execution).

        Descriptor kinds:
          confirm   — resume the SAME task object with confirmed=True
                      (no re-planning from scratch);
          cancel    — drop the pending task honestly;
          clarify   — refine the ORIGINAL request with the user's answer
                      and reroute it (new route over merged entities);
          waiting   — the pending clarification received another vague
                      answer: keep waiting, do not guess.
        """
        p = self.pending_task
        if p is None:
            return None

        kind = self.classify_response(user_text)

        if p.state == PendingState.WAITING_CONFIRMATION:
            if kind == "confirm":
                return {"kind": "confirm", "pending": p}
            if kind == "cancel":
                return {"kind": "cancel", "pending": p}
            # Anything else is NOT a confirmation: the risky action stays
            # blocked (fail-safe default).
            return {"kind": "waiting", "pending": p}

        if p.state == PendingState.WAITING_CLARIFICATION:
            if kind == "cancel":
                return {"kind": "cancel", "pending": p}
            answer = user_text.strip()
            if not answer or len(answer) < 2:
                return {"kind": "waiting", "pending": p}
            return {"kind": "clarify", "pending": p, "answer": answer}

        return None
