from __future__ import annotations

"""AgentLoop — real observe/act/verify/replan cycle.

Implements docs/CORE_MIGRATION.md §6:
- plan -> execute -> observe -> verify -> next step / final;
- on failure: bounded replan (max_replans), bounded execution steps;
- explicit failure state, no false success;
- Policy enforcement point before every tool call (§3);
- observations persist in ExecutionTrace for Verification/Responder.

Task 6 — reliability hardening (this module is the SINGLE owner of all
execution counters; TaskContext only carries the boundary state):

- BOUNDED per-step retry (max_retries_per_step, default 1 == at most one
  retry). Retry applies ONLY to TIMEOUT and FAILURE. SUCCESS / BLOCKED /
  NOT_IMPLEMENTED / CANCELLED are never retried.
- Retry NEVER resets max_steps / total_budget / tool_budget / max_replans
  and never touches the replan counter; replan never resets retry counts.
- Every launched attempt consumes one slot of the GLOBAL attempt budget
  (total_budget := min(trace.max_steps, ctx.total_budget if set)), so:
      executed_attempts <= max_steps          (termination invariant)
      replans           <= max_replans
      retries/step      <= max_retries_per_step
      tool_calls        <= tool_budget (when > 0)
  The outer loop additionally decrements `remaining_budget` by the exact
  number of attempts spent in each pass — retries can never resurrect it.
- Cooperative cancellation via CancelToken checked BEFORE every new tool
  launch, AFTER every attempt and between passes. A running blocking tool
  may finish (Python threads cannot be force-killed — we do not claim
  otherwise); the NEXT boundary observes the signal and stops.
- Observation-dependent execution: after every attempt a compact structured
  context (status/summary/error/verification/data) is written into
  ctx.previous_observation and injected into the next step's input_data and
  into planner.replan() — the trace stays the single full history.
- Honest terminal outcomes recorded once in trace.terminal_outcome:
  SUCCESS / FAILED / CANCELLED / BUDGET_EXCEEDED / MAX_STEPS_EXCEEDED /
  BLOCKED / EMPTY_PLAN. No fake success anywhere.
"""

import inspect
from typing import Any, Dict, List, Optional, Tuple

from .task_context import TaskContext, CancelToken
from .execution_trace import ExecutionTrace, ExecutionStatus, StepRecord
from .planner import Planner, Plan
from .verifier import Verifier
from .policy import PolicyEngine, PolicyDecision
from .responder import Responder

from ..tools.registry import ToolRegistry
from ..tools.observation import Observation, ObservationStatus


# ----------------------------------------------------------------------
# Retry classification — pure function, deterministic, unit-testable.
# ----------------------------------------------------------------------
RETRYABLE_STATUSES = frozenset({"TIMEOUT", "FAILURE"})
NON_RETRYABLE_STATUSES = frozenset(
    {"SUCCESS", "NOT_IMPLEMENTED", "BLOCKED", "CANCELLED"}
)


def classify_retry(observation: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """Decide whether an execution attempt may be retried.

    Returns (retry_allowed, reason). Classification precedence:
    - structured Observation.status wins when present;
    - legacy dict shape falls back to boolean success (-> FAILURE);
    - unknown evidence defaults to NO RETRY (never optimistic).
    """
    if observation is None:
        return False, "no observation"
    status = observation.get("status")
    if status is None:
        # Legacy dict without structured status: success means nothing to
        # retry; an error-shaped dict is treated as FAILURE.
        if observation.get("success"):
            return False, "SUCCESS (legacy shape)"
        status = "FAILURE"
    status = str(status).upper()
    if status in NON_RETRYABLE_STATUSES:
        return False, f"{status} is not retryable"
    if status in RETRYABLE_STATUSES:
        return True, f"{status} is retryable"
    # Unknown status: conservative — no retry.
    return False, f"unknown status '{status}' is not retryable"


class AgentLoop:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        planner: Optional[Planner] = None,
        verifier: Optional[Verifier] = None,
        policy: Optional[PolicyEngine] = None,
        responder: Optional[Responder] = None,
        max_replans: int = 1,
        max_retries_per_step: Optional[int] = None,
    ):
        self.tool_registry = tool_registry
        self.planner = planner or Planner()
        self.verifier = verifier or Verifier()
        self.policy = policy or PolicyEngine()
        self.responder = responder or Responder()
        # Bounded, deterministic replan budget (CORE_MIGRATION.md §6).
        self.max_replans = max_replans
        # Task 6 FINAL contract (single, unambiguous):
        #   max_retries_per_step = N  -> at most N retries after attempt 1
        #                                (N=0 => attempt 1 -> STOP; N=1 =>
        #                                attempt 1 -> retry -> attempt 2 -> STOP)
        #   None (constructor default) -> inherit ctx.max_retries_per_step.
        # It is NOT a max-attempts counter and there is no tri-state/negative
        # sentinel: 0 means explicitly "no retries" everywhere (loop AND ctx).
        self.max_retries_per_step = (
            None if max_retries_per_step is None else int(max_retries_per_step)
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _is_cancelled(ctx: TaskContext) -> bool:
        return bool(ctx.cancel_token and ctx.cancel_token.cancelled)

    @staticmethod
    def _cancel_reason(ctx: TaskContext) -> str:
        if ctx.cancel_token is not None:
            return ctx.cancel_token.reason
        return "Cancelled."

    # ------------------------------------------------------------------
    def run(self, ctx: TaskContext, trace: ExecutionTrace) -> Dict[str, Any]:
        plan = self.planner.create_plan(ctx)
        trace.status = ExecutionStatus.PLANNING

        # Task 6 FINAL: cooperative cancellation boundary BEFORE the planner.
        # If cancellation was requested before run() started, no planning and
        # no tool execution happens; the loop terminates as CANCELLED. The
        # trace records an honest CANCELLED step (tool NOT launched) so the
        # cancellation is reconstructable from the trace itself.
        if self._is_cancelled(ctx):
            cancelled_reason = self._cancel_reason(ctx)
            if plan.steps:
                self._record_cancelled_step(ctx, trace, plan.steps[0], 1)
            trace.status = ExecutionStatus.CANCELLED
            trace.set_terminal_outcome("CANCELLED", reason=cancelled_reason)
            trace.finished_at = _now()
            answer = self.responder.respond(ctx, trace, plan, None)
            trace.final_answer = answer
            return {
                "answer": answer,
                "plan": plan.to_dict(),
                "verification": None,
                "replans": 0,
                "attempts": 0,
                "outcome": "CANCELLED",
                "retries": 0,
                "tool_calls": 0,
            }

        # ---- Global termination budget (single counter, no double count) --
        # total_budget caps ALL execution attempts INCLUDING retries.
        # It is derived from trace.max_steps unless the caller set a stricter
        # ctx.total_budget. This is THE termination invariant:
        #     executed_attempts <= total_budget <= max_steps.
        if ctx.total_budget is None:
            ctx.total_budget = max(0, trace.max_steps)
        else:
            ctx.total_budget = max(0, min(int(ctx.total_budget), max(0, trace.max_steps)))
        # Replan never creates fresh budget: counters/budgets live on ctx and
        # trace for the whole run(); nothing below resets them. AgentLoop is
        # the SINGLE owner of these counters during run() — they start at 0
        # per call (one AgentLoop.run == one task execution).
        ctx.attempts_used = 0
        ctx.tool_calls = 0
        ctx.replans_used = 0
        ctx.retries_used = 0

        # Effective retry bound — FINAL Task 6 contract (no tri-state, no
        # negative sentinel):
        #   loop value is None  -> inherit ctx.max_retries_per_step;
        #   loop value explicit (0,1,2,...) -> wins over context.
        # On BOTH sources: 0 == explicitly NO retries (attempt 1 -> stop).
        # Negative values are clamped to 0 defensively (never "inherit").
        if self.max_retries_per_step is None:
            ctx_retries = getattr(ctx, "max_retries_per_step", None)
            if ctx_retries is None:
                effective_retries = 1  # documented default: one retry
            else:
                effective_retries = max(0, int(ctx_retries))
        else:
            effective_retries = max(0, int(self.max_retries_per_step))
        self._effective_retries = effective_retries

        if not plan.steps:
            trace.status = ExecutionStatus.FAILED
            trace.errors.append("Planner returned empty plan.")
            trace.set_terminal_outcome("EMPTY_PLAN", reason="Planner returned empty plan.")
            trace.finished_at = _now()
            answer = self.responder.respond(ctx, trace, plan, None)
            trace.final_answer = answer
            return {
                "answer": answer,
                "plan": plan.to_dict(),
                "verification": None,
                "replans": 0,
                "attempts": 0,
                "outcome": "EMPTY_PLAN",
            }

        remaining_budget = max(0, ctx.total_budget - ctx.attempts_used)
        blocked_reason: Optional[str] = None
        cancelled_reason: Optional[str] = None
        budget_exhausted = False
        verification: Optional[Dict[str, Any]] = None
        outcome: Optional[str] = None

        while remaining_budget > 0:
            prev_attempts = ctx.attempts_used
            exec_info: Dict[str, Any] = {}
            executed_any, blocked_reason = self._execute_plan(
                ctx, trace, plan, remaining_budget, exec_info
            )
            # Attempts consumed in this pass (retries included) — the budget
            # shrinks by EXACTLY what ran; retry can never reset it.
            remaining_budget -= ctx.attempts_used - prev_attempts

            if exec_info.get("cancelled"):
                cancelled_reason = exec_info.get("cancel_reason") or self._cancel_reason(ctx)
                break
            if exec_info.get("budget_exhausted"):
                budget_exhausted = True
                break

            verification = self.verifier.verify_plan_execution(plan, trace)

            if verification["success"]:
                trace.status = ExecutionStatus.COMPLETED
                outcome = "SUCCESS"
                break

            # Between-pass cancellation boundary (before any next action).
            if self._is_cancelled(ctx):
                cancelled_reason = self._cancel_reason(ctx)
                break

            # Failure path: bounded replan (real control flow, not dead code).
            if (
                ctx.replans_used < self.max_replans
                and remaining_budget > 0
                and not blocked_reason  # policy block is terminal, not retryable
                and verification.get("retryable", True)
            ):
                ctx.replans_used += 1
                replans_used = ctx.replans_used
                # Task 6 regression fix: evidence comes from the VERIFICATION
                # result, not from trace.errors. trace.errors is append-only
                # historical evidence (failed attempts stay there forever);
                # treating it as current status resurrected resolved failures
                # and made them terminal (e.g. NOT_IMPLEMENTED), which both
                # broke bounded retry/replan semantics and produced a fake
                # task-level success in the Verifier supersession path.
                error_text = "; ".join(
                    (verification or {}).get("reasons", [])
                ) or "verification failed"
                # Observation-dependent replanning: the planner receives the
                # structured context of the LAST attempt (status/summary/error),
                # not just an error string.
                # Task 6 regression fix: pass `previous_observation` only when
                # the planner signature actually accepts it — legacy/third-party
                # planners (and existing test fakes) implement the original
                # 3-arg `replan(ctx, failed_plan, error)` contract and must not
                # break with a TypeError.
                replan_kwargs: Dict[str, Any] = {}
                try:
                    params = inspect.signature(self.planner.replan).parameters
                    if "previous_observation" in params or any(
                        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
                    ):
                        replan_kwargs["previous_observation"] = ctx.previous_observation
                except (TypeError, ValueError):
                    replan_kwargs["previous_observation"] = ctx.previous_observation
                new_plan = self.planner.replan(
                    ctx, plan, error_text, **replan_kwargs,
                )
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
                        # Task 6: prove replan did NOT reset retry/attempt state
                        "after_attempts": ctx.attempts_used,
                        "after_retries": ctx.retries_used,
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

        # ---------------- Terminal classification (honest, structured) ----
        if cancelled_reason is not None:
            trace.status = ExecutionStatus.CANCELLED
            trace.errors.append(f"Execution cancelled: {cancelled_reason}")
            trace.set_terminal_outcome(
                "CANCELLED",
                reason=cancelled_reason,
                attempts=ctx.attempts_used,
                retries=ctx.retries_used,
                replans=ctx.replans_used,
            )
            outcome = "CANCELLED"
        elif trace.status != ExecutionStatus.COMPLETED:
            trace.status = ExecutionStatus.FAILED
            if blocked_reason:
                outcome = "BLOCKED"
                trace.set_terminal_outcome(
                    "BLOCKED", reason=blocked_reason, attempts=ctx.attempts_used
                )
            elif budget_exhausted or remaining_budget <= 0:
                outcome = "BUDGET_EXCEEDED"
                trace.set_terminal_outcome(
                    "BUDGET_EXCEEDED",
                    attempts=ctx.attempts_used,
                    max_attempts=ctx.total_budget,
                    tool_calls=ctx.tool_calls,
                )
            else:
                outcome = "FAILED"
                trace.set_terminal_outcome(
                    "FAILED",
                    reasons=(verification or {}).get("reasons", []),
                    attempts=ctx.attempts_used,
                    retries=ctx.retries_used,
                    replans=ctx.replans_used,
                )
        else:
            trace.set_terminal_outcome(
                "SUCCESS",
                attempts=ctx.attempts_used,
                retries=ctx.retries_used,
                replans=ctx.replans_used,
            )

        # Budget-exhausted-at-entry path: the loop never ran, so nothing was
        # executed and no verification exists. Record it honestly in the
        # trace (no fake success — status stays FAILED).
        if verification is None and outcome in ("BUDGET_EXCEEDED", "EMPTY_PLAN"):
            trace.errors.append("Execution budget exhausted before any step ran.")
        elif verification is None and outcome is None:
            # Defensive: non-empty plan but zero global budget -> honest FAILED.
            trace.errors.append("Execution budget exhausted before any step ran.")
            trace.status = ExecutionStatus.FAILED
            trace.set_terminal_outcome("BUDGET_EXCEEDED", attempts=0, max_attempts=ctx.total_budget)
            outcome = "BUDGET_EXCEEDED"

        trace.finished_at = _now()
        answer = self.responder.respond(ctx, trace, plan, verification)
        trace.final_answer = answer

        return {
            "answer": answer,
            "plan": plan.to_dict(),
            "verification": verification,
            "replans": ctx.replans_used,
            "attempts": ctx.attempts_used,
            "retries": ctx.retries_used,
            "tool_calls": ctx.tool_calls,
            "outcome": outcome or ("CANCELLED" if trace.status == ExecutionStatus.CANCELLED else "FAILED"),
        }

    # ------------------------------------------------------------------
    def _execute_plan(
        self,
        ctx: TaskContext,
        trace: ExecutionTrace,
        plan: Plan,
        budget: int,
        info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Execute pending plan steps within the given ATTEMPT budget.

        Each logical step runs up to `1 + max_retries_per_step` attempts;
        EVERY launched attempt consumes one unit of the shared `budget`
        (and of ctx.attempts_used / trace.current_step — single counting).

        Returns (executed_any, policy_blocked_reason). Side-channel `info`
        reports cancellation / budget exhaustion to the caller.
        """
        info = info if info is not None else {}
        trace.status = ExecutionStatus.RUNNING
        executed_any = False
        blocked_reason: Optional[str] = None

        for step in plan.steps:
            existing = self._find_successful_record(trace, step)
            if existing is not None:
                # Already resolved successfully (possibly in a previous plan
                # iteration). Still refresh the observation context so the
                # NEXT step sees the latest known result of its predecessor.
                obs_ctx = self._context_from_record(existing)
                if obs_ctx is not None:
                    ctx.previous_observation = obs_ctx
                continue  # already attempted & resolved — never re-run

            attempt_number = 1 + self._prior_attempt_count(trace, step)

            while True:
                # --- Cancellation boundary BEFORE launching any new tool ---
                if self._is_cancelled(ctx):
                    self._record_cancelled_step(ctx, trace, step, attempt_number)
                    info["cancelled"] = True
                    info["cancel_reason"] = self._cancel_reason(ctx)
                    return executed_any, blocked_reason

                # --- Global attempt/tool budget (shared across retries) ---
                if ctx.attempts_used >= ctx.total_budget or budget <= 0:
                    trace.errors.append("Max steps exceeded.")
                    info["budget_exhausted"] = True
                    return executed_any, blocked_reason
                tb = ctx.tool_budget
                if tb is not None and tb > 0 and ctx.tool_calls >= tb:
                    trace.errors.append(
                        f"Tool budget exceeded ({ctx.tool_calls}/{tb})."
                    )
                    info["budget_exhausted"] = True
                    return executed_any, blocked_reason

                spec = self.tool_registry.get(step.tool) if step.tool else None

                # --- Observation-dependent execution: inject the PREVIOUS
                # structured observation into this step's inputs (additive
                # key; ToolRegistry strips it before executor dispatch —
                # it is a control carrier, not tool payload). ---
                effective_input = dict(step.input_data or {})
                if ctx.previous_observation is not None:
                    effective_input["previous_observation"] = ctx.previous_observation

                trace_step = trace.add_step(
                    action=step.action, tool=step.tool,
                    input_data=effective_input, attempt_number=attempt_number,
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
                    return executed_any, blocked_reason

                # Count the attempt as soon as it is committed to execution
                # (single source of truth: ctx counters mirror trace.current_step).
                ctx.attempts_used += 1
                trace.current_step += 1
                budget -= 1
                executed_any = True

                if spec is None:
                    # Unregistered tool: NOT_IMPLEMENTED — never retried.
                    observation = {
                        "success": False,
                        "error": f"Tool not found: {step.tool}",
                        "verified": False,
                        "status": ObservationStatus.NOT_IMPLEMENTED.value,
                    }
                    trace.record_observation(
                        trace_step, observation=observation,
                        error=f"Tool not found: {step.tool}",
                    )
                    ctx.previous_observation = self._context_from_record(trace_step)
                    break  # NOT_IMPLEMENTED: no retry, move to next step

                ctx.tool_calls += 1
                result = self.tool_registry.run(
                    step.tool, policy=self.policy, ctx=ctx, **effective_input
                )

                # Task 5 boundary: Registry returns a structured Observation;
                # the legacy dict shape is derived from it explicitly (single
                # source of truth stays in ExecutionTrace — no second history).
                if isinstance(result, Observation):
                    observation = result.to_trace_observation()
                    obs_obj = result
                else:
                    observation = result.to_observation()
                    obs_obj = getattr(result, "_observation", None) or None
                trace.record_observation(
                    trace_step, observation=observation,
                    error=observation.get("error"),
                    # Task 6 bugfix: honest execution evidence. This branch
                    # is reached ONLY after a real Registry.run() dispatch,
                    # so the attempt demonstrably executed regardless of the
                    # outcome status (SUCCESS/FAILURE/TIMEOUT all ran).
                    # The heuristic in complete_step cannot see this fact for
                    # FAILURE-shaped observations, which would otherwise make
                    # execution_verified False for attempts that really ran.
                    execution_verified=True,
                )

                # --- Post-execution cancellation check (cooperative) ---
                if self._is_cancelled(ctx):
                    info["cancelled"] = True
                    info["cancel_reason"] = self._cancel_reason(ctx)

                # --- Deterministic retry decision ---
                retry_ok, retry_reason = classify_retry(observation)
                will_retry = (
                    retry_ok
                    and (attempt_number - 1) < self._effective_retries
                    and budget > 0
                    and ctx.attempts_used < ctx.total_budget
                    and not info.get("cancelled", False)
                    and not self._is_cancelled(ctx)
                )
                trace.record_retry({
                    "action": step.action,
                    "tool": step.tool,
                    "attempt": attempt_number,
                    "status": observation.get("status"),
                    "classification": retry_reason,
                    "will_retry": will_retry,
                    "max_retries_per_step": self._effective_retries,
                })
                if not will_retry:
                    # Observation-dependent execution: publish this attempt's
                    # compact structured context for the NEXT step / replan.
                    ctx.previous_observation = self._context_from_record(trace_step)
                    break

                # Retry: SAME action, NEW attempt record. Budgets untouched.
                ctx.retries_used += 1
                attempt_number += 1

        return executed_any, blocked_reason

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _record_cancelled_step(
        self, ctx: TaskContext, trace: ExecutionTrace, step, attempt_number: int
    ) -> StepRecord:
        """Record an honest CANCELLED step WITHOUT launching the tool."""
        reason = self._cancel_reason(ctx)
        trace_step = trace.add_step(
            action=step.action, tool=step.tool,
            input_data=dict(step.input_data or {}),
            attempt_number=attempt_number,
        )
        observation = Observation.cancelled(step.tool or "", reason).to_trace_observation()
        trace.record_observation(trace_step, observation=observation, error=None)
        trace_step.error = reason
        ctx.previous_observation = self._context_from_record(trace_step)
        return trace_step

    @staticmethod
    def _context_from_record(rec: StepRecord) -> Optional[Dict[str, Any]]:
        """Compact structured context of an attempt (small carrier, not a
        second history): status/summary/error/verification/data."""
        if rec.observation is None:
            return None
        obs = rec.observation
        data = obs.get("data") if isinstance(obs.get("data"), dict) else {}
        summary = data.get("stdout") or data.get("message") or data.get("result") or ""
        return {
            "tool": rec.tool,
            "status": obs.get("status") or ("SUCCESS" if rec.status == "success" else "FAILURE"),
            "success": bool(obs.get("success", False)),
            "executed": bool(getattr(rec, "execution_verified", False)),
            "verified": bool(obs.get("verified", False)),
            "summary": str(summary)[:500],
            "error": obs.get("error"),
            "attempt_number": rec.attempt_number,
            "data": data,
        }

    @staticmethod
    def _find_successful_record(trace: ExecutionTrace, step) -> Optional[StepRecord]:
        """Latest RESOLVED record for this logical step (success only).

        Failed attempts must be re-attemptable (retry semantics); blocked
        records keep the historical terminal-block behavior. Matching is on
        the PLAN payload (step.input_data), not on the effective inputs —
        the injected `previous_observation` carrier must never make an
        already-resolved step look "new".
        """
        plan_input = dict(step.input_data or {})
        found: Optional[StepRecord] = None
        for rec in trace.steps:
            rec_input = {k: v for k, v in (rec.input_data or {}).items()
                         if k != "previous_observation"}
            if (
                rec.action == step.action
                and rec.tool == step.tool
                and rec_input == plan_input
                and rec.status in ("success", "blocked")
            ):
                found = rec
        return found

    @staticmethod
    def _prior_attempt_count(trace: ExecutionTrace, step) -> int:
        plan_input = dict(step.input_data or {})
        n = 0
        for rec in trace.steps:
            rec_input = {k: v for k, v in (rec.input_data or {}).items()
                         if k != "previous_observation"}
            if rec.action == step.action and rec.tool == step.tool and rec_input == plan_input:
                n += 1
        return n

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
