"""Core migration pipeline tests (docs/CORE_MIGRATION.md).

Covers the fundamental gaps closed in this migration stage:
- Policy enforcement point before tool execution;
- ToolRegistry as single capability source for the Planner;
- AgentLoop real observe/act/verify/replan cycle with bounded budget;
- Verification without false success;
- Responder as final layer;
- Observations preserved in ExecutionTrace.

Run: python test_core_pipeline.py
"""

from mia.core.task_context import TaskContext, TaskMode, TaskDomain
from mia.core.execution_trace import ExecutionTrace, ExecutionStatus
from mia.core.policy import PolicyEngine, PolicyDecision
from mia.core.planner import Planner, Plan, PlanStep
from mia.core.verifier import Verifier
from mia.core.responder import Responder
from mia.core.agent_loop import AgentLoop
from mia.tools.registry import ToolRegistry
from mia.tools.schemas import ToolSpec, ToolResult
from mia.tools.builtin_tools import register_builtin_tools


PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def make_ctx(intent="TECHNICAL_TASK", complexity="C3", raw="тест"):
    ctx = TaskContext(raw_input=raw)
    ctx.intent = intent
    ctx.mode = TaskMode.AGENT
    ctx.domain = TaskDomain.SYSTEM
    ctx.complexity = complexity
    return ctx


# ----------------------------------------------------------------------
print("=== 1. Policy: real enforcement point ===")
policy = PolicyEngine()

ctx = make_ctx(intent="DELETE_FILES")
policy.evaluate(ctx)
d = policy.check_tool(ctx, "files.delete", None)
check("high-risk intent blocks tool", not d.allowed and d.requires_confirmation)

reg = register_builtin_tools(ToolRegistry())
spec_open = reg.get("system.open_app")
ctx2 = make_ctx(intent="OPEN_APPLICATION")
policy.evaluate(ctx2)
d2 = policy.check_tool(ctx2, "system.open_app", spec_open)
check("low-risk allowed tool passes", d2.allowed)

# Simulated risky tool metadata — explicit two-branch policy test:
# unconfirmed -> deny, confirmed -> allow (and denial must stay strict).
risky = ToolSpec(name="shell.run", description="run shell", risk="high",
                 requires_confirmation=True)
ctx3 = make_ctx()
d3 = policy.check_tool(ctx3, "shell.run", risky)
check("unconfirmed risky tool is denied", not d3.allowed and d3.requires_confirmation)
check("deny reason mentions confirmation", "confirmation" in d3.reason)
d3.confirmed = True
d4 = policy.check_tool(ctx3, "shell.run", risky, decision=d3)
check("confirmed risky tool is allowed", d4.allowed)
check("confirmed decision keeps requires flag", d4.requires_confirmation)

# Denied intent stays denied even after confirmation (policy not weakened).
p_denied = PolicyEngine()
p_denied.denied_intents = {"FORBIDDEN_THING"}
ctx_deny = make_ctx(intent="FORBIDDEN_THING")
dd = p_denied.check_tool(ctx_deny, "shell.run", risky)
dd.confirmed = True
dd2 = p_denied.check_tool(ctx_deny, "shell.run", risky, decision=dd)
check("denied intent cannot be unlocked by confirmation", not dd2.allowed)

# ----------------------------------------------------------------------
print("=== 2. ToolRegistry: capability source ===")
caps = reg.capability_names()
check("registry exposes capabilities", len(caps) >= 5)
check("web.search marked STUB", reg.get("web.search").status == "STUB")

planner = Planner(tool_registry=reg)
check("planner reads tools from registry", planner.available_tools() == caps)
check("no duplicated tool list on planner", not hasattr(planner, "available_tools_list"))

result = reg.run("unknown.tool", x=1)
check("unknown tool -> honest failure", not result.success and not result.verified)

bad = reg.run("files.list", path=12345)  # wrong type per schema
check("schema validation rejects bad input", not bad.success)

# ----------------------------------------------------------------------
print("=== 3. Verification: no false success ===")
verifier = Verifier()

# 3a. half-failed plan must NOT be success
plan = Plan(goal="g", steps=[
    PlanStep(1, "a1", "files.list", {}),
    PlanStep(2, "a2", "files.read", {}),
])
trace = ExecutionTrace(task_id="t")
s1 = trace.add_step("a1", "files.list", {})
trace.record_observation(s1, observation={"success": True, "data": {}, "error": None, "verified": True})
s2 = trace.add_step("a2", "files.read", {})
trace.record_observation(s2, observation={"success": False, "error": "boom"}, error="boom")
v = verifier.verify_plan_execution(plan, trace)
check("partial failure is not success", not v["success"])
check("failed step counted", v["failed_steps"] == 1)

# 3b. max_steps truncation must NOT be success
trace2 = ExecutionTrace(task_id="t2", max_steps=1)
trace2.errors.append("Max steps exceeded.")
s = trace2.add_step("a1", "files.list", {})
trace2.record_observation(s, observation={"success": True, "data": {}, "verified": True})
v2 = verifier.verify_plan_execution(plan, trace2)
check("budget truncation is not success", not v2["success"] and v2["budget_exceeded"])

# 3c. unverified tool success (fake open_app) must NOT be success
plan_one = Plan(goal="g", steps=[PlanStep(1, "open", "system.open_app", {"app_name": "x"})])
trace3 = ExecutionTrace(task_id="t3")
s = trace3.add_step("open", "system.open_app", {"app_name": "x"})
trace3.record_observation(s, observation={"success": True, "data": {}, "verified": False})
v3 = verifier.verify_plan_execution(plan_one, trace3)
check("unverified tool result blocks success", not v3["success"])

# 3d. genuine full success IS success
trace4 = ExecutionTrace(task_id="t4")
sa = trace4.add_step("a1", "files.list", {})
trace4.record_observation(sa, observation={"success": True, "data": {"items": [1]}, "verified": True})
sb = trace4.add_step("a2", "files.read", {})
trace4.record_observation(sb, observation={"success": True, "data": {"content": "x"}, "verified": True})
v4 = verifier.verify_plan_execution(plan, trace4)
check("true success verified", v4["success"] and v4["executed_steps"] == 2)

# 3e. empty observations / zero executed steps
v5 = verifier.verify_plan_execution(plan, ExecutionTrace(task_id="t5"))
check("nothing executed -> failure", not v5["success"])

# 3f. REGRESSION: successful replan must be reflected in verification.
# Failed web.search step is superseded by the alternative capability
# (browser.open) that produced a verified success AFTER the replan marker.
plan_after_replan = Plan(goal="search", steps=[PlanStep(1, "open_search", "browser.open", {})])
tr = ExecutionTrace(task_id="t6")
f1 = tr.add_step("search", "web.search", {"query": "mia"})
tr.record_observation(f1, observation={"success": False, "error": "web.search is a stub"}, error="web.search is a stub")
tr.record_replan({"attempt": 1, "at_after_steps": len(tr.steps)})
ok1 = tr.add_step("open_search", "browser.open", {"url": "https://www.google.com/search?q=mia"})
tr.record_observation(ok1, observation={"success": True, "data": {"url": "x"}, "verified": True})
v6 = verifier.verify_plan_execution(plan_after_replan, tr)
check("successful replan verifies as success", v6["success"] and v6["executed_steps"] == 1)
check("superseded failure not counted", v6["failed_steps"] == 0)

# 3g. Negative controls for the same mechanism — no false success allowed.
# (i) replan happened but the resolving attempt FAILED -> still failure
tr2 = ExecutionTrace(task_id="t7")
f1 = tr2.add_step("search", "web.search", {})
tr2.record_observation(f1, observation={"success": False, "error": "stub"}, error="stub")
tr2.record_replan({"attempt": 1, "at_after_steps": len(tr2.steps)})
bad1 = tr2.add_step("open_search", "browser.open", {})
tr2.record_observation(bad1, observation={"success": False, "error": "driver crashed"}, error="driver crashed")
v7 = verifier.verify_plan_execution(plan_after_replan, tr2)
check("replan with failed resolution stays failure", not v7["success"])

# (ii) resolution marked 'success' but unverified -> cannot supersede
tr3 = ExecutionTrace(task_id="t8")
f1 = tr3.add_step("search", "web.search", {})
tr3.record_observation(f1, observation={"success": False, "error": "stub"}, error="stub")
tr3.record_replan({"attempt": 1, "at_after_steps": len(tr3.steps)})
uv = tr3.add_step("open_search", "browser.open", {})
tr3.record_observation(uv, observation={"success": True, "verified": False})
v8 = verifier.verify_plan_execution(plan_after_replan, tr3)
check("unverified resolution cannot supersede failure", not v8["success"])

# (iii) failure recorded AFTER the last replan -> counts as real failure
tr4 = ExecutionTrace(task_id="t9")
r1 = tr4.add_step("open_search", "browser.open", {})
tr4.record_observation(r1, observation={"success": True, "verified": True})
tr4.record_replan({"attempt": 1, "at_after_steps": len(tr4.steps)})
late_fail = tr4.add_step("verify_page", "files.read", {})
tr4.record_observation(late_fail, observation={"success": False, "error": "boom"}, error="boom")
plan_two = Plan(goal="g", steps=[
    PlanStep(1, "open_search", "browser.open", {}),
    PlanStep(2, "verify_page", "files.read", {}),
])
v9 = verifier.verify_plan_execution(plan_two, tr4)
check("post-replan failure is not superseded", not v9["success"] and v9["failed_steps"] == 1)

# ----------------------------------------------------------------------
print("=== 4. AgentLoop: real loop, policy block, replan budget ===")

# 4a. policy blocks risky tool BEFORE execution
executed_flag = []
blocking_reg = ToolRegistry()
blocking_reg.register(ToolSpec(
    name="files.delete", description="delete", risk="high",
    requires_confirmation=True,
    executor=lambda **kw: executed_flag.append(1) or ToolResult(success=True),
))
loop_policy = PolicyEngine()


class DeletePlanner(Planner):
    def _rule_based_plan(self, ctx, level="fast"):
        return Plan(goal="del", steps=[PlanStep(1, "delete", "files.delete", {"path": "x"})])


ctx_del = make_ctx(intent="DELETE_FILES")
loop_policy.evaluate(ctx_del)
trace_del = ExecutionTrace(task_id="td", max_steps=5)
loop = AgentLoop(blocking_reg, DeletePlanner(tool_registry=blocking_reg),
                 policy=loop_policy)
res = loop.run(ctx_del, trace_del)
check("blocked tool never executed", not executed_flag)
check("blocked task fails honestly", not res["verification"]["success"])
check("blocked status recorded", any(st.status == "blocked" for st in trace_del.steps))
check("answer does not claim success", "выполнено" not in res["answer"].lower()[:20])
check("policy decision stored in trace", trace_del.to_dict()["policy_decision"] is not None)

# 4b. replan: web.search stub -> browser.open fallback
replan_reg = ToolRegistry()
opened = []
replan_reg.register(ToolSpec(
    name="web.search", description="stub search", status="STUB",
    input_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
    executor=lambda query: ToolResult(success=False, error="web.search is a stub", verified=False),
))
replan_reg.register(ToolSpec(
    name="browser.open", description="open url",
    input_schema={"properties": {"url": {"type": "string"}}, "required": ["url"]},
    executor=lambda url: opened.append(url) or ToolResult(success=True, data={"url": url}),
))


class SearchStubPlanner(Planner):
    def _rule_based_plan(self, ctx, level="fast"):
        return Plan(goal="search", steps=[PlanStep(1, "search", "web.search", {"query": "mia"})])


ctx_s = make_ctx(intent="WEB_SEARCH")
trace_s = ExecutionTrace(task_id="ts", max_steps=6)
loop_s = AgentLoop(replan_reg, SearchStubPlanner(tool_registry=replan_reg),
                   policy=PolicyEngine())
res_s = loop_s.run(ctx_s, trace_s)
check("replan happened", res_s["replans"] >= 1)
check("replan used alternative tool", len(opened) == 1 and "google.com" in opened[0])
check("replanned task verified successful", res_s["verification"]["success"])
check("replan history in trace", len(trace_s.to_dict()["replans"]) >= 1)
check("observations persisted in trace artifacts",
      any(a.get("kind") == "observation" for a in trace_s.to_dict()["artifacts"]))

# 4c. replan budget is bounded (max_replans respected)
class AlwaysFailPlanner(Planner):
    def _rule_based_plan(self, ctx, level="fast"):
        return Plan(goal="g", steps=[PlanStep(1, "fail", "flaky.tool", {})])

    def replan(self, ctx, failed_plan, error):
        # produce a different-but-still-failing plan each time
        n = len(failed_plan.steps) + 1
        return Plan(goal="g", steps=[PlanStep(1, f"fail{n}", "flaky.tool", {"n": n})])


fail_reg = ToolRegistry()
calls = []
fail_reg.register(ToolSpec(
    name="flaky.tool", description="always fails",
    executor=lambda **kw: calls.append(1) or ToolResult(success=False, error="nope", verified=False),
))
ctx_f = make_ctx()
trace_f = ExecutionTrace(task_id="tf", max_steps=20)
loop_f = AgentLoop(fail_reg, AlwaysFailPlanner(tool_registry=fail_reg), max_replans=2)
res_f = loop_f.run(ctx_f, trace_f)
check("replan count bounded", res_f["replans"] <= 2)
check("failing loop terminates", trace_f.status == ExecutionStatus.FAILED)
check("failure reported honestly", not res_f["verification"]["success"])
check("failure answer admits problem", "не смогла" in res_f["answer"] or "не выполнила" in res_f["answer"])

# 4d. unknown tool -> explicit failed step, no fake success
class GhostPlanner(Planner):
    def _rule_based_plan(self, ctx, level="fast"):
        return Plan(goal="g", steps=[PlanStep(1, "use ghost", "ghost.tool", {})])


trace_g = ExecutionTrace(task_id="tg", max_steps=5)
loop_g = AgentLoop(register_builtin_tools(ToolRegistry()), GhostPlanner(tool_registry=reg))
res_g = loop_g.run(make_ctx(), trace_g)
check("unknown tool produces failed step", any(st.status == "failed" for st in trace_g.steps))
check("unknown tool not falsely successful", not res_g["verification"]["success"])

# ----------------------------------------------------------------------
print("=== 5. Responder: final layer after verification ===")
resp = Responder()

ctx_r = make_ctx(intent="OPEN_APPLICATION", raw="открой блокнот")
ctx_r.entities["app_name"] = "notepad"
trace_ok = ExecutionTrace(task_id="tr")
st = trace_ok.add_step("open_application", "system.open_app", {"app_name": "notepad"})
trace_ok.record_observation(st, observation={
    "success": True, "verified": True,
    "data": {"app_name": "notepad", "method": "start"}, "error": None,
})
answer = resp.respond(ctx_r, trace_ok, None, {"success": True})
check("success answer mentions app", "notepad" in answer)
check("success answer not hardcoded generic", answer != "Я выполнила задачу по плану.")

trace_bad = ExecutionTrace(task_id="tb")
trace_bad.errors.append("boom")
st2 = trace_bad.add_step("x", "files.read", {})
trace_bad.complete_step(st2, error="boom")
answer2 = resp.respond(ctx_r, trace_bad, None, {"success": False})
check("failure answer admits failure", "не смогла" in answer2)

# Styling separation: responder applies stylist only at the end.
class TagStylist:
    def style(self, text, mode="ASSISTANT"):
        return text + " ~"

resp_styled = Responder(stylist=TagStylist())
ans3 = resp_styled.respond(ctx_r, trace_ok, None, {"success": True})
check("character styling applied by responder", ans3.endswith("~"))

# ----------------------------------------------------------------------
print("=== 6. system.open_app honesty (non-Windows dev env) ===")
from mia.adapters.system_adapter import SystemAdapter

r = SystemAdapter().open_app("some-gui-app")
if r.success:
    check("open_app success carries evidence", r.data.get("method") in ("start", "path"))
else:
    check("open_app reports honest failure", r.verified is False)

print()
print(f"TOTAL: {PASS} passed, {FAIL} failed")
raise SystemExit(1 if FAIL else 0)
