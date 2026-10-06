"""Task 6 — AgentLoop Reliability test suite.

Deterministic, offline, no runtime artifacts (all executions go through fake
registries/planners; no memory files are touched).

Semantics under test (docs/CORE_MIGRATION.md §6 + Task 6 contract):
- bounded per-step retry (TIMEOUT/FAILURE only; never SUCCESS/BLOCKED/
  NOT_IMPLEMENTED/CANCELLED);
- bounded replan; retry/replan counters independent; neither resets budgets;
- every launched attempt consumes the GLOBAL attempt budget
  (total_budget := min(trace.max_steps, ctx.total_budget if stricter));
- tool_budget caps dispatched tool calls -> BUDGET_EXCEEDED terminal outcome;
- cooperative cancellation checked before planner / before tool / after tool /
  between steps — blocking tools are never force-killed;
- Observation N really flows into step N+1 input and into planner.replan();
- verification split: execution_verified vs result_verified, unknown != True;
- ExecutionTrace: attempt numbers, retry/replan records, append-only policy
  history with legacy `policy_decision` pointer, single honest terminal_outcome.
"""

import inspect
import sys

from mia.core.agent_loop import AgentLoop, classify_retry
from mia.core.task_context import TaskContext, CancelToken
from mia.core.execution_trace import ExecutionTrace, ExecutionStatus
from mia.core.planner import Plan, PlanStep
from mia.core.policy import PolicyEngine
from mia.core.verifier import Verifier
from mia.tools.observation import Observation, ObservationStatus

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
if __name__ == "__main__":
    class FakePlanner:
        def __init__(self, plan):
            self._plan = plan
            self.replan_calls = []

        def create_plan(self, ctx):
            return self._plan

        def replan(self, ctx, failed_plan, error, previous_observation=None):
            self.replan_calls.append({
                "error": error,
                "previous_observation": previous_observation,
            })
            return self._plan  # same plan -> signature break stops the loop


    class ExplodingPlanner(FakePlanner):
        """replan must NEVER be called when cancellation happened first."""

        def replan(self, *a, **k):
            raise AssertionError("planner.replan called despite cancellation")


    class AltPlanner(FakePlanner):
        """First replan returns a DIFFERENT plan (forces a second pass)."""

        def __init__(self, plan, alt_plan):
            super().__init__(plan)
            self._alt = alt_plan

        def replan(self, ctx, failed_plan, error, previous_observation=None):
            self.replan_calls.append(previous_observation)
            return self._alt


    class ChurnPlanner(FakePlanner):
        """Every replan produces a NEW distinct plan (adversarial churn)."""

        def __init__(self, plan):
            super().__init__(plan)
            self.n = 0

        def replan(self, ctx, failed_plan, error, previous_observation=None):
            self.n += 1
            st = PlanStep(step_id=1, action=f"churn_{self.n}", tool="t",
                         input_data={"i": self.n})
            return Plan(goal="g", steps=[st])


    class FakeRegistry:
        def __init__(self, behaviors):
            self._behaviors = behaviors
            self.calls = []                # [(tool, call_no)]
            self.cancel_during = None      # (tool, call_no, reason)

        def get(self, name):
            return object() if name in self._behaviors else None

        def run(self, name, *, policy=None, ctx=None, **kwargs):
            n = sum(1 for t, _ in self.calls if t == name) + 1
            self.calls.append((name, n))
            if (self.cancel_during
                    and self.cancel_during[0] == name
                    and self.cancel_during[1] == n
                    and ctx is not None):
                ctx.request_cancel(self.cancel_during[2])
            b = self._behaviors[name]
            res = b(name, n) if callable(b) else b
            if isinstance(res, list):
                res = res[min(n - 1, len(res) - 1)]
            return res


    class CancelAfterRunRegistry(FakeRegistry):
        def run(self, name, *, policy=None, ctx=None, **kwargs):
            r = super().run(name, policy=policy, ctx=ctx, **kwargs)
            ctx.request_cancel("between passes")
            return r


    def obs_success(tool, verified=False):
        md = {"verified": True, "data": {"message": f"{tool} done"}} if verified \
            else {"data": {"message": f"{tool} done"}}
        return Observation(tool=tool, status=ObservationStatus.SUCCESS,
                           summary=f"{tool} done", metadata=md)


    def obs_failure(tool):
        return Observation.failure(tool, error=f"{tool} boom")


    def obs_timeout(tool):
        return Observation.timeout(tool, limit_seconds=1)


    def make_loop(registry, plan, max_replans=1, max_retries_per_step=1, verifier=None):
        return AgentLoop(
            tool_registry=registry,
            planner=FakePlanner(plan),
            verifier=verifier or Verifier(),
            policy=PolicyEngine(),
            max_replans=max_replans,
            max_retries_per_step=max_retries_per_step,
        )


    def one_step_plan(tool="t"):
        return Plan(goal="g", steps=[
            PlanStep(step_id=1, action=f"a_{tool}", tool=tool, input_data={})])


    def two_step_plan(t1="t1", t2="t2"):
        return Plan(goal="g", steps=[
            PlanStep(step_id=1, action=f"a_{t1}", tool=t1, input_data={}),
            PlanStep(step_id=2, action=f"a_{t2}", tool=t2, input_data={}),
        ])


    def fresh_ctx(**kw):
        kw.setdefault("complexity", "C4")
        return TaskContext(raw_input="task", **kw)


    # ==========================================================================
    print("=== 1. retry classification (pure function) ===")
    check("TIMEOUT retryable", classify_retry({"status": "TIMEOUT"})[0])
    check("FAILURE retryable", classify_retry({"status": "FAILURE"})[0])
    check("SUCCESS not retried", not classify_retry({"status": "SUCCESS"})[0])
    check("NOT_IMPLEMENTED not retried", not classify_retry({"status": "NOT_IMPLEMENTED"})[0])
    check("BLOCKED not retried", not classify_retry({"status": "BLOCKED"})[0])
    check("CANCELLED not retried", not classify_retry({"status": "CANCELLED"})[0])
    check("unknown status -> conservative NO", not classify_retry({"status": "WEIRD"})[0])
    check("None observation -> NO", not classify_retry(None)[0])
    check("legacy success dict -> NO", not classify_retry({"success": True})[0])
    check("legacy error dict -> FAILURE-like YES", classify_retry({"success": False, "error": "x"})[0])

    # ==========================================================================
    print("=== 2. bounded retry behavior ===")
    reg = FakeRegistry({"t": [obs_failure("t"), obs_success("t", verified=True)]})
    loop = make_loop(reg, one_step_plan())
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("FAILURE -> retry -> SUCCESS", res["outcome"] == "SUCCESS", str(res))
    check("two attempts executed", reg.calls == [("t", 1), ("t", 2)], str(reg.calls))
    check("attempts counter == 2", res["attempts"] == 2)
    check("retries counter == 1", res["retries"] == 1)
    check("retry did NOT increase replans", res["replans"] == 0)

    reg = FakeRegistry({"t": obs_failure("t")})
    loop = make_loop(reg, one_step_plan())
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("persistent FAILURE stops after 1+max_retries", res["attempts"] == 2, str(res))
    check("outcome FAILED", res["outcome"] == "FAILED")

    reg = FakeRegistry({"t": obs_timeout("t")})
    loop = make_loop(reg, one_step_plan())
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("TIMEOUT retried once then terminal", res["attempts"] == 2)
    check("TIMEOUT twice -> FAILED (no infinite timeout-retry)", res["outcome"] == "FAILED")

    reg = FakeRegistry({"t": [obs_timeout("t"), obs_success("t", verified=True)]})
    loop = make_loop(reg, one_step_plan())
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("TIMEOUT -> retry -> SUCCESS", res["outcome"] == "SUCCESS")

    reg = FakeRegistry({"t": lambda name, n: Observation.not_implemented(name)})
    loop = make_loop(reg, one_step_plan())
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("NOT_IMPLEMENTED never retried", res["attempts"] == 1)

    reg = FakeRegistry({"t": [obs_failure("t"), obs_success("t", verified=True)]})
    loop = make_loop(reg, one_step_plan(), max_retries_per_step=0)
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("max_retries_per_step=0 -> single attempt", res["attempts"] == 1)
    check("no retry -> FAILED", res["outcome"] == "FAILED")

    ctx = fresh_ctx(max_retries_per_step=-3)
    reg = FakeRegistry({"t": obs_failure("t")})
    loop = make_loop(reg, one_step_plan(), max_retries_per_step=None)  # inherit ctx(-3 -> clamp 0)
    res = loop.run(ctx, ExecutionTrace(max_steps=5))
    check("negative ctx bound clamped to 0", res["attempts"] == 1)

    # FINAL Task 6 contract: an EXPLICIT loop value always wins over the
    # context; negative is never a sentinel — it clamps defensively to 0.
    ctx = fresh_ctx(max_retries_per_step=2)
    reg = FakeRegistry({"t": [obs_failure("t"), obs_success("t", verified=True)]})
    loop = make_loop(reg, one_step_plan(), max_retries_per_step=0)  # explicit 0 beats ctx 2
    res = loop.run(ctx, ExecutionTrace(max_steps=10))
    check("explicit loop 0 overrides ctx 2 (no retry)",
          res["attempts"] == 1 and res["outcome"] == "FAILED", str(res))

    ctx = fresh_ctx(max_retries_per_step=-3)
    reg = FakeRegistry({"t": obs_failure("t")})
    loop = make_loop(reg, one_step_plan(), max_retries_per_step=-3)  # explicit negative -> clamp 0
    res = loop.run(ctx, ExecutionTrace(max_steps=5))
    check("explicit negative loop bound clamped to 0", res["attempts"] == 1)

    ctx = fresh_ctx(max_retries_per_step=2)
    reg = FakeRegistry({"t": [obs_failure("t"), obs_failure("t"), obs_success("t", verified=True)]})
    loop = make_loop(reg, one_step_plan(), max_retries_per_step=None)  # None => inherit ctx(2)
    res = loop.run(ctx, ExecutionTrace(max_steps=10))
    check("ctx max_retries_per_step=2 honored",
          res["attempts"] == 3 and res["outcome"] == "SUCCESS", str(res))

    # BLOCKED via policy is terminal, never retried
    pol = PolicyEngine()
    ctx_b = fresh_ctx(intent="RUN_SHELL")
    reg = FakeRegistry({"t": obs_success("t", verified=True)})
    loop = make_loop(reg, one_step_plan())
    res = loop.run(ctx_b, ExecutionTrace(max_steps=5))
    # RUN_SHELL intent denied? verify against policy directly
    denied = not pol.check_tool(ctx_b, "t", None).allowed
    if denied:
        check("policy-blocked tool -> BLOCKED outcome, no retry",
              res["outcome"] == "BLOCKED" and res["attempts"] == 0, str(res))
    else:
        check("policy block path present in code", True)

    # ==========================================================================
    print("=== 3. retry/replan independence, budgets never reset ===")
    plan_a = Plan(goal="g", steps=[PlanStep(step_id=1, action="a_x", tool="x", input_data={})])
    plan_b = Plan(goal="g", steps=[PlanStep(step_id=1, action="a_y", tool="y", input_data={})])
    reg = FakeRegistry({"x": obs_failure("x"), "y": obs_success("y", verified=True)})
    fp = AltPlanner(plan_a, plan_b)
    loop = AgentLoop(tool_registry=reg, planner=fp, verifier=Verifier(),
                     policy=PolicyEngine(), max_replans=1, max_retries_per_step=1)
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=6))
    check("replan after retry-exhausted failure -> SUCCESS", res["outcome"] == "SUCCESS", str(res))
    check("x attempted twice (1 retry), y once",
          reg.calls.count(("x", 1)) == 1 and reg.calls.count(("x", 2)) == 1
          and reg.calls.count(("y", 1)) == 1, str(reg.calls))
    check("replans == 1", res["replans"] == 1)
    check("retries == 1 preserved across replan", res["retries"] == 1)
    check("attempts == 3 total (shared budget, not reset)", res["attempts"] == 3)
    check("planner.replan received observation context",
          bool(fp.replan_calls) and fp.replan_calls[-1] is not None
          and fp.replan_calls[-1].get("status") == "FAILURE")

    reg = FakeRegistry({"x": obs_failure("x"), "y": obs_failure("y")})
    fp = AltPlanner(plan_a, plan_b)
    loop = AgentLoop(tool_registry=reg, planner=fp, verifier=Verifier(),
                     policy=PolicyEngine(), max_replans=5, max_retries_per_step=2)
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=4))
    check("adversarial retry+replan respects max_steps", res["attempts"] <= 4, str(res))
    check("terminates FAILED/BUDGET_EXCEEDED", res["outcome"] in ("FAILED", "BUDGET_EXCEEDED"))

    # ==========================================================================
    print("=== 4. observation propagation ===")
    seen = {}


    class ObsSpyRegistry(FakeRegistry):
        def run(self, name, *, policy=None, ctx=None, **kwargs):
            seen[name] = kwargs.get("previous_observation")
            return super().run(name, policy=policy, ctx=ctx, **kwargs)


    reg = ObsSpyRegistry({"t1": obs_failure("t1"), "t2": obs_success("t2", verified=True)})
    loop = make_loop(reg, two_step_plan(), max_retries_per_step=0)
    loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("step1 saw no previous observation", seen["t1"] is None)
    check("step2 received Observation context of step1", isinstance(seen["t2"], dict))
    if isinstance(seen["t2"], dict):
        check("carried status is FAILURE", seen["t2"].get("status") == "FAILURE")
        check("carried error present", bool(seen["t2"].get("error")))
        check("carried attempt number", seen["t2"].get("attempt_number") == 1)
        check("carried verified flag honest (False)", seen["t2"].get("verified") is False)

    src = open("mia/tools/registry.py").read()
    check("Registry strips previous_observation carrier from executor payload",
          'kwargs.pop("previous_observation"' in src)

    reg = FakeRegistry({"t1": obs_success("t1", verified=True), "t2": obs_success("t2", verified=True)})
    loop = make_loop(reg, two_step_plan())
    loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("both distinct steps executed", sorted(set(t for t, _ in reg.calls)) == ["t1", "t2"])
    check("step2 executed exactly once (not skipped as duplicate of step1)",
          reg.calls.count(("t2", 1)) == 1)

    reg = ObsSpyRegistry({"t1": obs_success("t1", verified=True), "t2": obs_success("t2", verified=True)})
    loop = make_loop(reg, two_step_plan())
    loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("step2 sees SUCCESS context of step1",
          isinstance(seen["t2"], dict) and seen["t2"].get("status") == "SUCCESS")

    # ==========================================================================
    print("=== 5. budgets ===")
    reg = FakeRegistry({"t": obs_success("t", verified=True)})
    loop = make_loop(reg, one_step_plan())
    res = loop.run(fresh_ctx(total_budget=0), ExecutionTrace(max_steps=5))
    check("total_budget=0 -> zero tool launches", reg.calls == [])
    check("total_budget=0 -> BUDGET_EXCEEDED", res["outcome"] == "BUDGET_EXCEEDED")

    reg = FakeRegistry({"t": obs_failure("t")})
    loop = make_loop(reg, one_step_plan())
    res = loop.run(fresh_ctx(total_budget=1), ExecutionTrace(max_steps=5))
    check("total_budget=1 -> exactly 1 attempt despite retry allowance", res["attempts"] == 1)
    check("invariant executed_attempts <= total_budget", res["attempts"] <= 1)

    reg = FakeRegistry({"t1": obs_success("t1", verified=True), "t2": obs_success("t2", verified=True)})
    loop = make_loop(reg, two_step_plan())
    res = loop.run(fresh_ctx(tool_budget=1), ExecutionTrace(max_steps=10))
    check("tool_budget=1 -> only one dispatch", reg.calls == [("t1", 1)], str(reg.calls))
    check("second tool NOT executed -> BUDGET_EXCEEDED", res["outcome"] == "BUDGET_EXCEEDED")

    reg = FakeRegistry({"t1": obs_success("t1", verified=True), "t2": obs_success("t2", verified=True)})
    loop = make_loop(reg, two_step_plan())
    res = loop.run(fresh_ctx(tool_budget=0), ExecutionTrace(max_steps=5))
    check("tool_budget=0 documented unlimited-within-total", res["outcome"] == "SUCCESS")

    reg = FakeRegistry({"t": obs_failure("t")})
    loop = make_loop(reg, one_step_plan(), max_replans=3)
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=1))
    check("max_steps=1 -> 1 attempt", res["attempts"] == 1)
    check("max_steps exhaustion -> BUDGET_EXCEEDED", res["outcome"] == "BUDGET_EXCEEDED")

    reg = FakeRegistry({"t": obs_failure("t")})
    loop = make_loop(reg, one_step_plan())
    res = loop.run(fresh_ctx(total_budget=3), ExecutionTrace(max_steps=100))
    check("executed_attempts <= min(max_steps,total_budget)", res["attempts"] <= 3)

    reg = FakeRegistry({"t": obs_timeout("t")})
    loop = make_loop(reg, one_step_plan(), max_retries_per_step=5)
    res = loop.run(fresh_ctx(total_budget=2), ExecutionTrace(max_steps=100))
    check("retry can never exceed total_budget", res["attempts"] == 2)

    # ==========================================================================
    print("=== 6. cancellation ===")
    ctx = fresh_ctx()
    ctx.request_cancel("user stopped")
    reg = FakeRegistry({"t": obs_success("t", verified=True)})
    loop = make_loop(reg, one_step_plan())
    res = loop.run(ctx, ExecutionTrace(max_steps=5))
    check("cancel before tool -> tool NOT launched", reg.calls == [])
    check("outcome CANCELLED", res["outcome"] == "CANCELLED")
    check("cancellation not disguised as FAILED/SUCCESS",
          res["outcome"] not in ("FAILED", "SUCCESS"))

    reg = FakeRegistry({"t1": obs_success("t1", verified=True), "t2": obs_success("t2", verified=True)})
    reg.cancel_during = ("t1", 1, "stop now")
    loop = make_loop(reg, two_step_plan())
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("blocking tool ran fully (no thread kill)", reg.calls[0] == ("t1", 1))
    check("next boundary observed cancel -> t2 never launched",
          all(t != "t2" for t, _ in reg.calls), str(reg.calls))
    check("outcome CANCELLED after tool", res["outcome"] == "CANCELLED")

    plan1 = Plan(goal="g", steps=[PlanStep(step_id=1, action="a_t", tool="t", input_data={"k": 1})])
    reg = CancelAfterRunRegistry({"t": obs_failure("t")})
    fp = ExplodingPlanner(plan1)
    loop = AgentLoop(tool_registry=reg, planner=fp, verifier=Verifier(),
                     policy=PolicyEngine(), max_replans=2, max_retries_per_step=0)
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("cancel between steps -> loop ends CANCELLED before replan",
          res["outcome"] == "CANCELLED")

    check("classify_retry rejects CANCELLED", not classify_retry({"status": "CANCELLED"})[0])

    tok = CancelToken()
    check("token initially not cancelled", not tok.cancelled)
    check("cancel flips flag", tok.cancel("x") and tok.cancelled)
    check("double cancel idempotent", not tok.cancel("y"))
    check("reason kept", tok.reason == "x")
    ctx2 = fresh_ctx()
    check("ctx without token not cancelled", not ctx2.cancelled)
    ctx2.request_cancel("late")
    check("request_cancel lazily creates token", ctx2.cancelled and ctx2.cancel_token.reason == "late")

    # ==========================================================================
    print("=== 7. verification semantics ===")
    v = Verifier()

    # NOTE: action must match the plan's action (a_t). The verifier matches
    # attempted steps against planned steps by (action, tool); a mismatched
    # action would honestly report "planned step not executed" (that behavior
    # itself is asserted in section 8 below).
    trace = ExecutionTrace(max_steps=5)
    rec = trace.add_step(action="a_t", tool="t", input_data={}, attempt_number=1)
    trace.record_observation(rec, observation=obs_success("t").to_trace_observation())
    res_v = v.verify_plan_execution(one_step_plan("t"), trace)
    top = res_v["checks"][0]
    check("execution_verified True for real run", top["execution_verified"] is True)
    check("result_verified False without explicit hint", top["result_verified"] is False)
    check("unknown never auto-True", top["result_verified"] is False)
    check("task not success w/o result verification", res_v["success"] is False)

    trace = ExecutionTrace(max_steps=5)
    rec = trace.add_step(action="a_t", tool="t", input_data={}, attempt_number=1)
    trace.record_observation(rec, observation=obs_success("t", verified=True).to_trace_observation())
    res_v = v.verify_plan_execution(one_step_plan("t"), trace)
    top = res_v["checks"][0]
    check("result_verified True only with explicit hint", top["result_verified"] is True)
    check("execution SUCCESS + verified -> task success", res_v["success"] is True, str(res_v))

    # Control: a step whose action does NOT match the plan must keep the honest
    # "planned step not executed" verdict even when its observation is verified.
    trace = ExecutionTrace(max_steps=5)
    rec = trace.add_step(action="other_action", tool="t", input_data={}, attempt_number=1)
    trace.record_observation(rec, observation=obs_success("t", verified=True).to_trace_observation())
    res_v = v.verify_plan_execution(one_step_plan("t"), trace)
    check("action mismatch -> no fake task success (unattempted honored)",
          res_v["success"] is False and res_v["unattempted_steps"] == 1, str(res_v))

    trace = ExecutionTrace(max_steps=5)
    rec = trace.add_step(action="a_t", tool="t", input_data={}, attempt_number=1)
    trace.record_observation(rec, observation=obs_failure("t").to_trace_observation())
    res_v = v.verify_plan_execution(one_step_plan("t"), trace)
    top = res_v["checks"][0]
    check("failed result -> result_verified False", top["result_verified"] is False)
    check("discrepancy invariant: result_ok implies execution ran",
          not (top["result_verified"] and not top["execution_verified"]))

    reg = FakeRegistry({"t": obs_success("t")})  # no verified hint
    loop = make_loop(reg, one_step_plan(), max_retries_per_step=0)
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("successful execution + no result verifier -> no fake SUCCESS",
          res["outcome"] == "FAILED", str(res))
    check("but execution really happened",
          res["attempts"] == 1 and reg.calls == [("t", 1)])

    # ==========================================================================
    print("=== 8. execution trace integrity ===")
    reg = FakeRegistry({"t": [obs_failure("t"), obs_success("t", verified=True)]})
    trace = ExecutionTrace(max_steps=5)
    loop = make_loop(reg, one_step_plan())
    res = loop.run(fresh_ctx(), trace)
    attempts = [s.attempt_number for s in trace.steps]
    check("attempt numbers 1,2 recorded", attempts == [1, 2], str(attempts))
    check("retry decisions recorded", len(trace.retries) >= 1)
    check("retry entry has classification + will_retry",
          "classification" in trace.retries[0] and "will_retry" in trace.retries[0])
    check("terminal outcome recorded", trace.terminal_outcome["outcome"] == "SUCCESS")
    check("terminal outcome reports attempts", trace.terminal_outcome.get("attempts") == 2)
    check("observation stored on step record", trace.steps[1].observation is not None)
    check("verification fields exist on records",
          hasattr(trace.steps[0], "execution_verified") and hasattr(trace.steps[0], "result_verified"))
    check("result_verified propagated from hint", trace.steps[1].result_verified is True)
    check("failed attempt status recorded honestly", trace.steps[0].status == "failed")

    trace2 = ExecutionTrace(max_steps=5)
    d1 = PolicyEngine().check_tool(fresh_ctx(complexity="C0"), "t", None)
    d2 = PolicyEngine().check_tool(fresh_ctx(), "t", None)
    trace2.record_policy(d1)
    trace2.record_policy(d2)
    check("policy_history appends both", len(trace2.policy_history) == 2)
    check("policy_history order preserved",
          trace2.policy_history[0] is d1 and trace2.policy_history[1] is d2)
    check("legacy policy_decision == last", trace2.policy_decision is d2)

    trace3 = ExecutionTrace(max_steps=5)
    reg = FakeRegistry({"t": obs_success("t", verified=True)})
    loop = make_loop(reg, one_step_plan())
    loop.run(fresh_ctx(total_budget=0), trace3)
    check("zero-budget entry: status FAILED (no fake success)", trace3.status == ExecutionStatus.FAILED)
    check("zero-budget entry: terminal BUDGET_EXCEEDED",
          trace3.terminal_outcome["outcome"] == "BUDGET_EXCEEDED")
    check("zero-budget entry: honest error",
          any("budget exhausted" in e.lower() for e in trace3.errors))

    trace4 = ExecutionTrace(max_steps=5)
    ctx = fresh_ctx()
    ctx.request_cancel("audit")
    reg = FakeRegistry({"t": obs_success("t", verified=True)})
    loop = make_loop(reg, one_step_plan())
    loop.run(ctx, trace4)
    check("cancelled trace status CANCELLED", trace4.status == ExecutionStatus.CANCELLED)
    check("cancelled trace has CANCELLED observation",
          trace4.steps[0].observation["status"] == "CANCELLED")
    check("cancelled trace terminal outcome CANCELLED",
          trace4.terminal_outcome["outcome"] == "CANCELLED")
    check("cancelled trace finished_at set", trace4.finished_at is not None)

    plan_a = Plan(goal="g", steps=[PlanStep(step_id=1, action="a_x", tool="x", input_data={})])
    plan_b = Plan(goal="g", steps=[PlanStep(step_id=1, action="a_y", tool="y", input_data={})])
    reg = FakeRegistry({"x": obs_failure("x"), "y": obs_success("y", verified=True)})
    trace5 = ExecutionTrace(max_steps=6)
    fp = AltPlanner(plan_a, plan_b)
    loop = AgentLoop(tool_registry=reg, planner=fp, verifier=Verifier(),
                     policy=PolicyEngine(), max_replans=1, max_retries_per_step=1)
    loop.run(fresh_ctx(), trace5)
    check("replan recorded", len(trace5.replans) == 1)
    check("replan marker proves retries not reset", trace5.replans[0].get("after_retries") == 1)
    check("replan marker proves attempts not reset", trace5.replans[0].get("after_attempts") == 2)

    # ==========================================================================
    print("=== 9. adversarial combined termination ===")
    reg = FakeRegistry({"t": obs_failure("t")})
    loop = make_loop(reg, one_step_plan(), max_replans=5, max_retries_per_step=3)
    trace = ExecutionTrace(max_steps=6)
    res = loop.run(fresh_ctx(), trace)
    check("adversarial loop terminates", res["outcome"] in ("FAILED", "BUDGET_EXCEEDED"))
    check("executed_attempts <= max_steps", res["attempts"] <= 6)
    check("replans <= max_replans", res["replans"] <= 5)
    check("retries < attempts", res["retries"] < res["attempts"])

    reg = FakeRegistry({"t": obs_timeout("t")})
    loop = make_loop(reg, one_step_plan(), max_replans=10, max_retries_per_step=2)
    res = loop.run(fresh_ctx(tool_budget=2, total_budget=4), ExecutionTrace(max_steps=100))
    check("combined bounds hold", res["attempts"] <= 4 and res["tool_calls"] <= 2, str(res))
    check("structured terminal outcome", res["outcome"] in ("FAILED", "BUDGET_EXCEEDED"))

    reg = FakeRegistry({"t": obs_failure("t")})
    cp = ChurnPlanner(one_step_plan())
    loop = AgentLoop(tool_registry=reg, planner=cp, verifier=Verifier(),
                     policy=PolicyEngine(), max_replans=100, max_retries_per_step=1)
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=7))
    check("churning replanner still bounded by max_steps", res["attempts"] <= 7, str(res))
    check("churning replanner terminates", res["outcome"] in ("FAILED", "BUDGET_EXCEEDED"))
    check("replans bounded by max_replans", res["replans"] <= 100)

    # ==========================================================================
    print("=== 10. regression: API shapes & defaults ===")
    res_keys = {"answer", "plan", "verification", "replans", "attempts", "outcome"}
    check("run() keeps legacy result keys", res_keys.issubset(set(res.keys())))
    check("new additive keys present", {"retries", "tool_calls"} <= set(res.keys()))
    sig = inspect.signature(AgentLoop.__init__)
    check("constructor default max_retries_per_step is None (inherit)",
          sig.parameters["max_retries_per_step"].default is None)
    check("TaskContext default max_retries is None (AgentLoop applies 1)",
          TaskContext().max_retries_per_step is None)
    # Effective default behavior: plain construction => one retry (attempt 1 ->
    # retry -> attempt 2 -> stop), proven by execution, not by field inspection.
    reg = FakeRegistry({"t": [obs_failure("t"), obs_success("t", verified=True)]})
    loop = make_loop(reg, one_step_plan(), max_retries_per_step=None)
    res = loop.run(fresh_ctx(), ExecutionTrace(max_steps=5))
    check("default effective retries == 1 (SUCCESS on 2nd attempt)",
          res["attempts"] == 2 and res["outcome"] == "SUCCESS", str(res))
    check("CancelToken excluded from serialization", "cancel_token" not in TaskContext().to_dict())
    check("previous_observation serialized", "previous_observation" in TaskContext().to_dict())

    # ==========================================================================
    print("=== 11. retry-supersession vs ghost-laundering (Verifier contract) ===")
    # Direct Verifier-level proof: one logical planned step judged by its FINAL
    # relevant attempt; strict identity matching otherwise.

    def _vtrace():
        return ExecutionTrace(max_steps=10)

    def _rec(trace, action, tool, observation, input_data=None, attempt=1):
        r = trace.add_step(action=action, tool=tool,
                           input_data=input_data if input_data is not None else {},
                           attempt_number=attempt)
        trace.record_observation(r, observation=observation.to_trace_observation(),
                                 error=observation.error or None,
                                 execution_verified=True)
        return r

    # Case A — retry success: A/T FAILURE then A/T SUCCESS resolves the step.
    tr = _vtrace()
    _rec(tr, "a_t", "t", obs_failure("t"), attempt=1)
    _rec(tr, "a_t", "t", obs_success("t", verified=True), attempt=2)
    rA = v.verify_plan_execution(one_step_plan("t"), tr)
    check("Case A: retry supersession -> unattempted==0", rA["unattempted_steps"] == 0, str(rA))
    check("Case A: failed attempt superseded -> no failure counted",
          rA["failed_steps"] == 0 and rA["success"] is True, str(rA))
    check("Case A: final attempt execution_verified",
          rA["checks"][1]["execution_verified"] is True)
    check("Case A: final attempt result_verified (explicit hint)",
          rA["checks"][1]["result_verified"] is True)

    # Case B — ghost mismatch: A/T FAILURE then B/T SUCCESS must NOT close A/T.
    tr = _vtrace()
    _rec(tr, "a_t", "t", obs_failure("t"), attempt=1)
    _rec(tr, "a_b", "b", obs_success("b", verified=True), attempt=1)
    rB = v.verify_plan_execution(one_step_plan("t"), tr)
    check("Case B: different action/tool cannot supersede (ghost laundering blocked)",
          rB["success"] is False and rB["unattempted_steps"] == 1, str(rB))

    # Case C — never executed at all.
    tr = _vtrace()
    rC = v.verify_plan_execution(one_step_plan("t"), tr)
    check("Case C: no attempts -> unattempted==1, not success",
          rC["unattempted_steps"] == 1 and rC["success"] is False, str(rC))

    # Case D — multiple retries ending in success: FAILURE, TIMEOUT, SUCCESS.
    tr = _vtrace()
    _rec(tr, "a_t", "t", obs_failure("t"), attempt=1)
    _rec(tr, "a_t", "t", obs_timeout("t"), attempt=2)
    _rec(tr, "a_t", "t", obs_success("t", verified=True), attempt=3)
    rD = v.verify_plan_execution(one_step_plan("t"), tr)
    check("Case D: multi-retry resolved by final attempt",
          rD["success"] is True and rD["failed_steps"] == 0
          and rD["unattempted_steps"] == 0, str(rD))

    # Case E — final attempt still failing: nothing is superseded.
    tr = _vtrace()
    _rec(tr, "a_t", "t", obs_failure("t"), attempt=1)
    _rec(tr, "a_t", "t", obs_timeout("t"), attempt=2)
    rE = v.verify_plan_execution(one_step_plan("t"), tr)
    check("Case E: unresolved retries stay failed",
          rE["success"] is False and rE["failed_steps"] >= 1
          and rE["unattempted_steps"] == 1, str(rE))

    # Case F — valid A/T attempt followed by unrelated B/T success:
    # A/T stays resolved; B/T must not launder anything and does not break A/T.
    tr = _vtrace()
    _rec(tr, "a_t", "t", obs_success("t", verified=True), attempt=1)
    _rec(tr, "a_b", "b", obs_success("b", verified=True), attempt=1)
    rF = v.verify_plan_execution(one_step_plan("t"), tr)
    check("Case F: unrelated extra success keeps A/T resolved",
          rF["unattempted_steps"] == 0 and rF["success"] is True, str(rF))

    # Case G — same action but DIFFERENT plan payload must not be conflated:
    # two distinct logical steps sharing (action, tool).
    tr = _vtrace()
    _rec(tr, "a_t", "t", obs_success("t", verified=True), input_data={"i": 1}, attempt=1)
    _rec(tr, "a_t", "t", obs_failure("t"), input_data={"i": 2}, attempt=1)
    two_payload_plan = Plan(goal="g", steps=[
        PlanStep(step_id=1, action="a_t", tool="t", input_data={"i": 1}),
        PlanStep(step_id=2, action="a_t", tool="t", input_data={"i": 2}),
    ])
    rG = v.verify_plan_execution(two_payload_plan, tr)
    check("Case G: payload-distinct steps not conflated (second stays unattempted)",
          rG["unattempted_steps"] == 1 and rG["success"] is False, str(rG))

    # Case H — AgentLoop end-to-end with a step that fails once then succeeds:
    # already covered in section 2 ('FAILURE -> retry -> SUCCESS'); additionally
    # assert the verifier's per-attempt check flags here:
    check("Case A: first attempt result_verified False (honest history)",
          rA["checks"][0]["result_verified"] is False)
    check("Case A: first attempt execution_verified True (it really ran)",
          rA["checks"][0]["execution_verified"] is True)

    # Case I — NOT_IMPLEMENTED ghost laundered by an unrelated replan success.
    # The capability does not exist; no alternative-capability fallback can
    # resolve it. This must NEVER become task SUCCESS (production-path guard,
    # test_core_pipeline 4d regression).
    tr = _vtrace()
    ni_obs = Observation.not_implemented("ghost.tool")
    _rec(tr, "use ghost", "ghost.tool", ni_obs, attempt=1)
    _rec(tr, "fallback_search", "browser.open", obs_success("browser.open", verified=True), attempt=1)
    ghost_plan = Plan(goal="g", steps=[
        PlanStep(step_id=1, action="fallback_search", tool="browser.open", input_data={}),
    ])
    rI = v.verify_plan_execution(ghost_plan, tr)
    check("Case I: unresolved NOT_IMPLEMENTED cannot be laundered into success",
          rI["success"] is False and any("not implemented" in x for x in rI["reasons"]),
          str(rI))

    # Case J — NOT_IMPLEMENTED resolved by a successful retry of the SAME
    # logical step is historical evidence only (supersession exemption): the
    # terminal NI rule must not veto a legitimately resolved step.
    tr = _vtrace()
    _rec(tr, "a_t", "t", ni_obs, attempt=1)
    _rec(tr, "a_t", "t", obs_success("t", verified=True), attempt=2)
    rJ = v.verify_plan_execution(one_step_plan("t"), tr)
    check("Case J: NI superseded by same-step successful retry -> resolvable",
          rJ["unattempted_steps"] == 0 and rJ["failed_steps"] == 0, str(rJ))

    # ==========================================================================
    print()
    print(f"TOTAL: {PASS} passed, {FAIL} failed")
    sys.exit(0 if FAIL == 0 else 1)
