from __future__ import annotations

"""Task-level verification (docs/CORE_MIGRATION.md §7).

Answers "was the user's task actually accomplished?", not "did at
least half of the steps avoid raising an exception". Deterministic
evidence first; optional LLM semantic check may only downgrade, never
upgrade, a deterministic result. False success is forbidden.
"""

from collections import Counter
from typing import Any, Dict, List, Optional


class Verifier:
    def __init__(self, model_router=None):
        self.model_router = model_router

    def verify_plan_execution(self, plan, trace) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        executed_steps = 0
        failed_steps = 0
        blocked_steps = 0

        for step in trace.steps:
            obs = step.observation or {}
            tool_ok = bool(
                step.status == "success"
                and step.error is None
                and obs.get("success", True)
                and obs.get("verified", True)
            )
            check = {
                "step_index": step.step_index,
                "action": step.action,
                "tool": step.tool,
                "status": step.status,
                "success": tool_ok,
                "error": step.error,
            }
            checks.append(check)
            if step.status == "failed" or (step.status == "success" and not tool_ok):
                failed_steps += 1
            elif step.status == "blocked":
                blocked_steps += 1
            elif tool_ok:
                executed_steps += 1

        planned = len(plan.steps) if plan and plan.steps else 0
        unattempted = 0
        superseded_failures = 0
        superseded_indices: set = set()
        if planned:
            # Match attempted steps against the CURRENT (possibly replanned)
            # plan; steps from earlier failed attempts must not count.
            plan_counter = Counter((s.action, s.tool) for s in plan.steps)
            attempted_counter = Counter(
                (s.action, s.tool)
                for s in trace.steps
                if s.status in ("success", "failed")
            )
            unattempted = sum(
                max(0, plan_counter[k] - attempted_counter.get(k, 0))
                for k in plan_counter
            )

            # Replan semantics: a failed step is superseded when the replan
            # demonstrably resolved the same planned goal. Evidence-based,
            # not a blanket pass:
            # - only applies when trace.replans is non-empty (real replan);
            # - only failures recorded BEFORE that replan are considered;
            # - the resolving verified success must be recorded AFTER the
            #   failure (same-action retry or alternative capability);
            # - failures with no later verified success still count.
            plan_actions = {st.action for st in plan.steps}
            plan_tools = {st.tool for st in plan.steps if st.tool}
            replan_marks = [r.get("at_after_steps") for r in (trace.replans or [])]

            ordered = sorted(trace.steps, key=lambda s: s.step_index)

            def _attempt_ok(s):
                return (
                    s.status == "success"
                    and s.error is None
                    and (s.observation or {}).get("success", True)
                    and (s.observation or {}).get("verified", True)
                )

            for pos, s in enumerate(ordered):
                if s.status != "failed":
                    continue
                # Supersession requires a real replan recorded after this step.
                resolving_replan = next(
                    (m for m in replan_marks if m is not None and pos < m), None
                )
                if resolving_replan is None:
                    continue  # no replan happened after this failure: still real
                # The failed step must be resolved by the replan outcome:
                # either it became stale (its action/tool is no longer planned)
                # or it was retried under the same action — in both cases a
                # verified successful observation must exist AFTER the failure.
                resolved_by_retry = any(
                    _attempt_ok(later) and later.action == s.action
                    for later in ordered[pos + 1:]
                )
                resolved_by_alternative = (
                    s.action not in plan_actions and s.tool not in plan_tools
                    and any(_attempt_ok(later) for later in ordered[pos + 1:])
                )
                if resolved_by_retry or resolved_by_alternative:
                    superseded_failures += 1
                    superseded_indices.add(s.step_index)

        errors = list(trace.errors or [])
        budget_exceeded = "Max steps exceeded." in errors
        policy_blocked = blocked_steps > 0 or any(
            "requires user confirmation" in e or "denied by policy" in e for e in errors
        )

        # Honest replan bookkeeping: a failed step that was later retried via
        # replan and superseded (see above) must not keep the whole task in a
        # failed state. The same applies to its recorded error string — it is
        # historical evidence of the first attempt, not the current status.
        if superseded_indices:
            errors = [e for i, e in enumerate(errors) if i not in superseded_indices]

        # ---- Deterministic task-level decision (no false success) ----
        reasons: List[str] = []
        success = True

        effective_failed = max(0, failed_steps - superseded_failures)
        if executed_steps == 0:
            success = False
            reasons.append("no step produced a verified successful result")
        if effective_failed > 0:
            success = False
            reasons.append(f"{effective_failed} step(s) failed")
        if unattempted > 0:
            success = False
            reasons.append(f"{unattempted} planned step(s) were not executed")
        if budget_exceeded:
            success = False
            reasons.append("execution budget exhausted before completion")
        if policy_blocked:
            success = False
            reasons.append("execution blocked by policy (confirmation required)")

        # ---- Optional semantic supplement (may only downgrade) ----
        semantic_check = None
        if self.model_router and trace.steps and success:
            semantic_check = self._semantic_verify(plan, trace)
            if semantic_check is not None and not semantic_check.get("success", True):
                success = False
                reasons.append("semantic verification rejected the result")

        retryable = (
            not success
            and effective_failed > 0
            and not policy_blocked
            and not budget_exceeded
        )

        summary = (
            f"{executed_steps}/{len(trace.steps)} trace steps verified ok; "
            f"planned={planned}, unattempted={unattempted}, "
            f"failed={effective_failed}, blocked={blocked_steps}"
            + (f", superseded_by_replan={superseded_failures}" if superseded_failures else "")
        )

        return {
            "success": success,
            "executed_steps": executed_steps,
            "failed_steps": effective_failed,
            "superseded_failures": superseded_failures,
            "blocked_steps": blocked_steps,
            "unattempted_steps": unattempted,
            "budget_exceeded": budget_exceeded,
            "policy_blocked": policy_blocked,
            "retryable": retryable,
            "reasons": reasons,
            "semantic_check": semantic_check,
            "checks": checks,
            "summary": summary,
        }

    def _semantic_verify(self, plan, trace) -> Optional[Dict[str, Any]]:
        try:
            steps_summary = "\n".join([
                f"- {s.action}: {'OK' if s.status == 'success' else 'FAIL: ' + str(s.error)}"
                for s in trace.steps
            ])

            prompt = f"""Проверь, достигнута ли цель задачи.

Цель: {plan.goal}

Выполненные шаги:
{steps_summary}

Ответь строго:
SUCCESS: yes/no
REASON: <краткое объяснение>"""

            response = self.model_router.generate(
                prompt=prompt,
                system_prompt="Ты проверяющий качества. Отвечай только yes/no и причину.",
                max_tokens=128,
                preferred="chat"
            )

            if response.error or not response.text:
                return None

            text = response.text.lower()
            success = "success: yes" in text or "успех: да" in text

            return {
                "success": success,
                "reason": response.text
            }

        except Exception as e:
            print(f"[Verifier] Semantic check error: {e}")
            return None