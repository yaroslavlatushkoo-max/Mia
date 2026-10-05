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

    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    final_answer: Optional[str] = None

    def add_step(self, action: str, tool: Optional[str] = None, input_data: Optional[Dict[str, Any]] = None) -> StepRecord:
        step = StepRecord(
            step_id=str(uuid.uuid4()),
            step_index=len(self.steps) + 1,
            action=action,
            tool=tool,
            input_data=input_data or {},
        )
        self.steps.append(step)
        return step

    def complete_step(self, step: StepRecord, observation: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        step.status = "failed" if error else "success"
        step.observation = observation
        step.error = error
        step.finished_at = time.time()

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
    ):
        """Store the tool observation on the step and mirror it into trace-level
        artifacts/errors so it survives beyond a single loop iteration."""
        self.complete_step(step, observation=observation, error=error)
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
        self.policy_decision = decision

    def record_replan(self, entry: Dict[str, Any]):
        self.replans.append(entry)