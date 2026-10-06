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
                # Task 6 verification split (Blocker 3): EXECUTED != VERIFIED.
                # execution_verified — the attempt really ran and returned a
                # structured outcome (honest flag maintained by ExecutionTrace/
                # AgentLoop; never promoted from unknown).
                # result_verified — only an explicit verification hint makes it
                # True; absent evidence stays False ("unknown != verified").
                "execution_verified": bool(
                    getattr(step, "execution_verified", None)
                    if getattr(step, "execution_verified", None) is not None
                    else (step.status == "success" and step.error is None)
                ),
                "result_verified": bool(tool_ok),
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

        # ---- Task 6 RETRY-SUPERSESSION (logical-step semantics) ----------
        # One logical planned step may have several physical attempts
        # (attempt 1 FAILURE -> retry attempt 2 SUCCESS). The step's outcome
        # is judged by its FINAL relevant attempt, not per-attempt. This is
        # strict identity matching only — no ghost laundering:
        #   * grouping key is the exact logical identity (action, tool,
        #     plan payload `input_data` with the injected control carrier
        #     `previous_observation` stripped — the same normalization the
        #     AgentLoop uses in _find_successful_record/_prior_attempt_count);
        #   * an attempt of a DIFFERENT action/tool can never close this step
        #     (a B/T success does not supersede an A/T failure);
        #   * steps without trace records stay unattempted;
        #   * if the final relevant attempt is FAILURE/TIMEOUT/CANCELLED/...
        #     the step is NOT verified — only a real SUCCESS resolves it.
        ordered_all = sorted(trace.steps, key=lambda s: s.step_index)

        def _logical_identity(rec) -> tuple:
            rec_input = {k: v for k, v in (rec.input_data or {}).items()
                         if k != "previous_observation"}
            return (rec.action, rec.tool, tuple(sorted(rec_input.items())))

        groups: Dict[tuple, List[Any]] = {}
        for rec in ordered_all:
            groups.setdefault(_logical_identity(rec), []).append(rec)

        def _step_final_ok(st) -> bool:
            """True iff the logical planned step has trace evidence whose
            FINAL relevant attempt is a successful execution."""
            key = (st.action, st.tool,
                   tuple(sorted((st.input_data or {}).items())))
            recs = groups.get(key)
            if not recs:
                return False
            final = recs[-1]  # latest attempt of THIS logical step
            obs_f = final.observation or {}
            return bool(
                final.status == "success"
                and final.error is None
                and obs_f.get("success", True)
                and obs_f.get("verified", True)
            )

        # Failed attempts that were later RESOLVED by a successful retry of
        # the SAME logical step are historical evidence, not current failures.
        resolved_retry_failures = 0
        resolved_failure_indices: set = set()
        for st in (plan.steps or []):
            recs = groups.get(
                (st.action, st.tool,
                 tuple(sorted((st.input_data or {}).items()))), []
            )
            if len(recs) > 1 and _step_final_ok(st):
                for r in recs[:-1]:
                    if r.status == "failed":
                        resolved_retry_failures += 1
                        resolved_failure_indices.add(r.step_index)

        if planned:
            # ---- Honest attempt accounting (single source of truth) ----
            # Only RESOLVED attempts count toward plan coverage: a failed
            # attempt of a logical step is NOT an execution of that planned
            # step. Counting failed attempts as coverage produced phantom
            # "unattempted==0" states and masked missing executions.
            resolved_counter: Counter = Counter()
            for s in trace.steps:
                if s.status != "success":
                    continue
                obs_s = s.observation or {}
                if obs_s and not (
                    bool(obs_s.get("success", False))
                    and bool(obs_s.get("verified", False))
                ):
                    continue  # legacy heuristic status without evidence
                resolved_counter[(s.action, s.tool)] += 1
            plan_counter = Counter((st.action, st.tool) for st in plan.steps)
            unattempted = sum(
                max(0, plan_counter[k] - resolved_counter.get(k, 0))
                for k in plan_counter
            )

            # Replan semantics: a failed step is superseded when the replan
            # demonstrably resolved the same planned goal. Evidence-based,
            # not a blanket pass:
            # - only applies when trace.replans is non-empty (real replan);
            # - only failures recorded BEFORE that replan marker qualify;
            # - resolution evidence is one of:
            #     (a) a verified successful attempt of the SAME logical step
            #         (retry / re-execution — identity via plan payload), or
            #     (b) an ALTERNATIVE-CAPABILITY resolution: the failed step's
            #         own action AND tool are both absent from the current
            #         plan (it was genuinely pruned/replaced by the replan)
            #         AND a verified success covering a CURRENT plan step
            #         exists after the replan marker.
            # Guards against laundering: a ghost/NOT_IMPLEMENTED failure does
            # NOT qualify for (b) because Planner fallbacks keep the original
            # action name (only the tool changes) — so `action in plan_actions`
            # stays true and the unrelated browser.open success cannot make a
            # never-implemented step "superseded".
            plan_actions = {st.action for st in plan.steps}
            plan_tools = {st.tool for st in plan.steps if st.tool}
            plan_keys = {(st.action, st.tool) for st in plan.steps}
            replan_marks = [r.get("at_after_steps") for r in (trace.replans or [])]

            ordered = sorted(trace.steps, key=lambda s: s.step_index)

            def _attempt_ok(s):
                obs = s.observation or {}
                if obs:
                    return (
                        s.status == "success"
                        and s.error is None
                        and bool(obs.get("success", False))
                        and bool(obs.get("verified", False))
                    )
                return s.status == "success" and s.error is None

            def _same_logical_step(a, b):
                ia = {k: v for k, v in (a.input_data or {}).items()
                      if k != "previous_observation"}
                ib = {k: v for k, v in (b.input_data or {}).items()
                      if k != "previous_observation"}
                if ia or ib:
                    return (
                        a.action == b.action
                        and a.tool == b.tool
                        and ia == ib
                    )
                return a.action == b.action and a.tool == b.tool

            for pos, s in enumerate(ordered):
                if s.status != "failed":
                    continue
                # Supersession requires a real replan recorded after this step.
                resolving_replan = next(
                    (m for m in replan_marks if m is not None and pos < m), None
                )
                if resolving_replan is None:
                    continue  # no replan happened after this failure: still real
                resolved_by_retry = any(
                    _attempt_ok(later) and _same_logical_step(later, s)
                    for later in ordered[pos + 1:]
                )
                step_genuinely_pruned = (
                    s.action not in plan_actions and s.tool not in plan_tools
                )
                resolved_by_alternative = (
                    step_genuinely_pruned
                    and any(
                        _attempt_ok(later)
                        and (later.action, later.tool) in plan_keys
                        for later in ordered[resolving_replan:]
                    )
                )
                if resolved_by_retry or resolved_by_alternative:
                    superseded_failures += 1
                    superseded_indices.add(s.step_index)

        # ---- Task 6 FINAL: NOT_IMPLEMENTED is terminal for the whole run. --
        # A step whose tool is not implemented cannot be repaired by replan
        # (the capability simply does not exist). The Planner's alternative-
        # capability fallback may execute other registered tools, but it can
        # never resolve the missing capability itself — so laundering a ghost
        # failure into task SUCCESS via an unrelated successful replan step is
        # forbidden. This also fixes the "unknown tool not falsely successful"
        # production-path regression (test_core_pipeline 4d): with the old
        # action-name guard the real Planner renamed the action on fallback
        # and the failure silently lost its blocked status.
        # Retry supersession exemption: a NOT_IMPLEMENTED attempt that was
        # later resolved by a SUCCESSFUL retry of the SAME logical step is
        # historical evidence (Case D semantics), exactly like plain failures.
        unresolved_ni_indices = {
            r.step_index for r in trace.steps
            if str((r.observation or {}).get("status", "")).upper() == "NOT_IMPLEMENTED"
        } - resolved_failure_indices
        not_implemented_steps = len(unresolved_ni_indices)

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

        # Task 6 retry-supersession: remove error strings belonging to failed
        # attempts that were RESOLVED by a successful retry of the SAME
        # logical step (strict identity match above). Only exact matches are
        # dropped; unresolved failures stay (no laundering).
        if resolved_failure_indices:
            resolved_msgs = {
                rec.error for rec in trace.steps
                if rec.step_index in resolved_failure_indices and rec.error
            }
            if resolved_msgs:
                errors = [e for e in errors if e not in resolved_msgs]

        # ---- Deterministic task-level decision (no false success) ----
        reasons: List[str] = []
        success = True

        # Retry supersession at the DECISION level: failed attempts of a
        # logical step whose FINAL relevant attempt succeeded are historical
        # evidence, not current failures. Unresolved failures stay counted.
        effective_failed = max(0, failed_steps - superseded_failures - resolved_retry_failures)
        if executed_steps == 0:
            success = False
            reasons.append("no step produced a verified successful result")
        if effective_failed > 0:
            success = False
            reasons.append(f"{effective_failed} step(s) failed")
        if not_implemented_steps > 0:
            # Terminal capability gap: never laundered into success.
            success = False
            reasons.append(
                f"{not_implemented_steps} step(s) required a tool that is not implemented"
            )
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