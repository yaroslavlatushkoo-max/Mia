from __future__ import annotations

"""AgentLoop — real observe/act/verify/replan cycle.

Implements docs/CORE_MIGRATION.md §6:
- plan -> execute -> observe -> verify -> next step / final;
- on failure: bounded replan (max_replans), bounded execution steps;
- explicit failure state, no false success;
- Policy enforcement point before every tool call (§3);
- observations persist in ExecutionTrace for Verification/Responder.
"""

from typing import Any, Dict, Optional

from .task_context import TaskContext
from .execution_trace import ExecutionTrace, ExecutionStatus
from .planner import Planner, Plan
from .verifier import Verifier
from .policy import PolicyEngine, PolicyDecision
from .responder import Responder

from ..tools.registry import ToolRegistry


class AgentLoop:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        planner: Optional[Planner] = None,
        verifier: Optional[Verifier] = None,
        policy: Optional[PolicyEngine] = None,
        responder: Optional[Responder] = None,
        max_replans: int = 1,
    ):
        self.tool_registry = tool_registry
        self.planner = planner or Planner()
        self.verifier = verifier or Verifier()
        self.policy = policy or PolicyEngine()
        self.responder = responder or Responder()
        # Bounded, deterministic replan budget (CORE_MIGRATION.md §6).
        self.max_replans = max_replans

    # ------------------------------------------------------------------
    def run(self, ctx: TaskContext, trace: ExecutionTrace) -> Dict[str, Any]:
        plan = self.planner.create_plan(ctx)
        trace.status = ExecutionStatus.PLANNING

        if not plan.steps:
            trace.status = ExecutionStatus.FAILED
            trace.errors.append("Planner returned empty plan.")
            answer = self.responder.respond(ctx, trace, plan, None)
            trace.final_answer = answer
            return {
                "answer": answer,
                "plan": plan.to_dict(),
                "verification": None,
                "replans": 0,
            }

        remaining_budget = max(0, trace.max_steps - trace.current_step)
        blocked_reason: Optional[str] = None
        replans_used = 0

        while remaining_budget > 0:
            prev_step = trace.current_step
            executed_any, blocked_reason = self._execute_plan(
                ctx, trace, plan, remaining_budget
            )
            # Steps consumed in this pass (bounded execution budget).
            remaining_budget -= trace.current_step - prev_step
            verification = self.verifier.verify_plan_execution(plan, trace)

            if verification["success"]:
                trace.status = ExecutionStatus.COMPLETED
                break

            # Failure path: bounded replan (real control flow, not dead code).
            if (
                replans_used < self.max_replans
                and remaining_budget > 0
                and not blocked_reason  # policy block is terminal, not retryable
                and verification.get("retryable", True)
            ):
                replans_used += 1
                error_text = "; ".join(trace.errors[-3:]) or "verification failed"
                new_plan = self.planner.replan(ctx, plan, error_text)
                trace.record_replan(
                    {
                        "attempt": replans_used,
                        "reason": error_text,
                        "goal": new_plan.goal,
                        "steps": len(new_plan.steps),
                        # Position marker: all trace steps with index below
                        # this value were recorded BEFORE the replan. The
                        # Verifier uses it to decide whether a failed step
                        # was superseded by the replan outcome.
                        "at_after_steps": len(trace.steps),
                    }
                )
                if new_plan.steps and self._plan_signature(new_plan) != self._plan_signature(plan):
                    plan = new_plan
                    continue
                # Replan produced the same plan — stop looping honestly.
                trace.errors.append("Replan produced no alternative steps.")
                break

            # Not retryable or budget exhausted.
            break

        # Loop ended without a successful verification (budget exhausted,
        # policy block, non-retryable failure or replan exhaustion).
        if trace.status != ExecutionStatus.COMPLETED:
            trace.status = ExecutionStatus.FAILED

        trace.finished_at = _now()
        answer = self.responder.respond(ctx, trace, plan, verification)
        trace.final_answer = answer

        return {
            "answer": answer,
            "plan": plan.to_dict(),
            "verification": verification,
            "replans": replans_used,
        }

    # ------------------------------------------------------------------
    def _execute_plan(
        self,
        ctx: TaskContext,
        trace: ExecutionTrace,
        plan: Plan,
        budget: int,
    ) -> (bool, Optional[str]):
        """Execute pending plan steps within the given step budget.

        Returns (executed_any, policy_blocked_reason).
        """
        trace.status = ExecutionStatus.RUNNING
        executed_any = False
        blocked_reason: Optional[str] = None

        for step in plan.steps:
            existing = self._find_step_record(trace, step)
            if existing is not None and existing.status in ("success", "failed", "blocked"):
                continue  # already attempted (possibly in a previous plan iteration)

            if trace.current_step >= trace.max_steps or budget <= 0:
                trace.errors.append("Max steps exceeded.")
                break

            spec = self.tool_registry.get(step.tool) if step.tool else None

            trace_step = trace.add_step(
                action=step.action, tool=step.tool, input_data=step.input_data
            )

            # --- Policy enforcement point (before execution) ---
            decision = self.policy.check_tool(ctx, step.tool or "", spec)
            trace.record_policy(decision)
            if not decision.allowed:
                trace_step.status = "blocked"
                trace_step.error = decision.reason
                trace_step.finished_at = _now()
                trace.errors.append(decision.reason)
                blocked_reason = decision.reason
                break

            if spec is None:
                trace.complete_step(
                    trace_step,
                    observation={"success": False, "error": f"Tool not found: {step.tool}"},
                    error=f"Tool not found: {step.tool}",
                )
                trace.current_step += 1
                budget -= 1
                executed_any = True
                continue

            result = self.tool_registry.run(step.tool, **step.input_data)
            observation = result.to_observation()
            trace.record_observation(trace_step, observation=observation, error=result.error)
            trace.current_step += 1
            budget -= 1
            executed_any = True

        return executed_any, blocked_reason

    @staticmethod
    def _plan_signature(plan: Plan):
        return [(s.action, s.tool, tuple(sorted(s.input_data.items()))) for s in plan.steps]

    @staticmethod
    def _find_step_record(trace: ExecutionTrace, step):
        for rec in trace.steps:
            if (
                rec.action == step.action
                and rec.tool == step.tool
                and rec.input_data == step.input_data
            ):
                return rec
        return None


def _now() -> float:
    import time

    return time.time()
