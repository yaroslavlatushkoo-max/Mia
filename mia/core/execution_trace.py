from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import time
import uuid


class ExecutionStatus(str, Enum):
    CREATED = "CREATED"
    ROUTED = "ROUTED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING_TOOL = "WAITING_TOOL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class StepRecord:
    step_id: str
    step_index: int
    action: str
    tool: Optional[str]
    status: str = "pending"
    input_data: Dict[str, Any] = field(default_factory=dict)
    observation: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    # Task 6 (reliability): attempt bookkeeping and verification split.
    # One StepRecord == one EXECUTION ATTEMPT (a retry of the same logical
    # plan step creates a NEW record with attempt_number incremented).
    attempt_number: int = 1
    execution_verified: bool = False   # did an attempt actually run & return?
    result_verified: bool = False      # was the outcome verified as correct?
    verification: Optional[Dict[str, Any]] = None  # per-attempt decision detail


@dataclass
class ExecutionTrace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""

    status: ExecutionStatus = ExecutionStatus.CREATED
    current_step: int = 0
    max_steps: int = 1

    steps: List[StepRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)

    # Replan history and last policy decision (CORE_MIGRATION.md §3:
    # the trace records replan history; Policy must influence execution).
    replans: List[Dict[str, Any]] = field(default_factory=list)
    policy_decision: Any = None
    # Task 6: full policy HISTORY (append-only; never overwrites earlier
    # decisions). `policy_decision` stays as a compatibility pointer to
    # the most recent decision — existing consumers keep working.
    policy_history: List[Any] = field(default_factory=list)
    # Task 6: retry decisions (attempt -> classification -> action), additive.
    retries: List[Dict[str, Any]] = field(default_factory=list)
    # Task 6: honest structured terminal outcome (SUCCESS / FAILED /
    # CANCELLED / BUDGET_EXCEEDED / MAX_STEPS_EXCEEDED / BLOCKED / EMPTY_PLAN).
    terminal_outcome: Optional[Dict[str, Any]] = None

    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    final_answer: Optional[str] = None

    def add_step(self, action: str, tool: Optional[str] = None, input_data: Optional[Dict[str, Any]] = None, attempt_number: int = 1) -> StepRecord:
        step = StepRecord(
            step_id=str(uuid.uuid4()),
            step_index=len(self.steps) + 1,
            action=action,
            tool=tool,
            input_data=input_data or {},
            attempt_number=attempt_number,
        )
        self.steps.append(step)
        return step

    def complete_step(self, step: StepRecord, observation: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        step.status = "failed" if error else "success"
        step.observation = observation
        step.error = error
        step.finished_at = time.time()

        # Task 6 verification split — EXECUTED != VERIFIED.
        # execution_verified: the attempt really ran and returned a
        # structured outcome (honest flag from Observation semantics;
        # TIMEOUT/BLOCKED/NOT_IMPLEMENTED/CANCELLED never executed).
        # result_verified: only an explicit verification hint makes it True.
        # Absent evidence is NEVER promoted to verified.
        obs = observation if isinstance(observation, dict) else {}
        status = obs.get("status")
        if status is not None:
            step.execution_verified = status in ("SUCCESS", "FAILURE")
        else:
            step.execution_verified = bool(obs.get("success", False)) or (error is not None)
        step.result_verified = bool(obs.get("verified", False))

        if error:
            self.errors.append(error)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "steps": [
                {
                    "step_id": s.step_id,
                    "step_index": s.step_index,
                    "action": s.action,
                    "tool": s.tool,
                    "status": s.status,
                    "input_data": s.input_data,
                    "observation": s.observation,
                    "error": s.error,
                    "started_at": s.started_at,
                    "finished_at": s.finished_at,
                    # Task 6 (additive): attempt bookkeeping + verification split
                    "attempt_number": s.attempt_number,
                    "execution_verified": s.execution_verified,
                    "result_verified": s.result_verified,
                    "verification": s.verification,
                }
                for s in self.steps
            ],
            "errors": self.errors,
            "artifacts": self.artifacts,
            "replans": list(self.replans),
            "policy_decision": (
                self.policy_decision.to_dict()
                if self.policy_decision is not None
                else None
            ),
            # Task 6 (additive): full policy history, retry decisions,
            # structured terminal outcome.
            "policy_history": [
                d.to_dict() if hasattr(d, "to_dict") else d
                for d in self.policy_history
            ],
            "retries": list(self.retries),
            "terminal_outcome": (
                dict(self.terminal_outcome)
                if self.terminal_outcome is not None
                else None
            ),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "final_answer": self.final_answer,
        }

    # ------------------------------------------------------------------
    # Observability helpers (CORE_MIGRATION.md §3: trace owns observations,
    # errors and replan history; AgentLoop/Verification/Responder reuse them)
    # ------------------------------------------------------------------
    def record_observation(
        self,
        step: StepRecord,
        observation: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        execution_verified: Optional[bool] = None,
    ):
        """Store the tool observation on the step and mirror it into trace-level
        artifacts/errors so it survives beyond a single loop iteration.

        Task 6 bugfix: `execution_verified` may be passed explicitly by the
        execution boundary (AgentLoop knows whether a real attempt ran).
        When omitted, complete_step derives the flag from the observation
        itself (legacy behavior for direct callers)."""
        self.complete_step(step, observation=observation, error=error)
        if execution_verified is not None:
            # Explicit evidence from the execution boundary wins over the
            # heuristic derivation; result_verified stays untouched.
            step.execution_verified = bool(execution_verified)
        if observation is not None:
            self.artifacts.append(
                {
                    "kind": "observation",
                    "step_index": step.step_index,
                    "tool": step.tool,
                    "observation": observation,
                }
            )

    def record_policy(self, decision):
        # Task 6: append-only history; `policy_decision` keeps pointing at
        # the most recent decision for backward compatibility.
        self.policy_history.append(decision)
        self.policy_decision = decision

    def record_replan(self, entry: Dict[str, Any]):
        self.replans.append(entry)

    def record_retry(self, entry: Dict[str, Any]):
        """Task 6: structured retry decision (attempt, classification, action)."""
        self.retries.append(entry)

    def set_terminal_outcome(self, outcome: str, **details):
        """Task 6: honest structured terminal outcome, recorded once."""
        if self.terminal_outcome is None:
            self.terminal_outcome = {"outcome": outcome, **details}