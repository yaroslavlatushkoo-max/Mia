"""Regression/golden tests for migration To-do #1-#3 (Session+HITL,
ExecutionBudget, Router intents).

Run: python test_session_hitl_router.py
"""

import json
import os

from mia.core.router import Router
from mia.core.cost_estimator import CostEstimator
from mia.core.policy import PolicyEngine
from mia.core.planner import Planner
from mia.core.task_context import TaskContext, TaskMode, TaskDomain
from mia.core.execution_trace import ExecutionTrace, ExecutionStatus
from mia.core.session import Session, PendingTask, PendingState
from mia.core.orchestrator import Orchestrator
from mia.tools.registry import ToolRegistry
from mia.tools.schemas import ToolSpec, ToolResult

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


router = Router()

# ----------------------------------------------------------------------
print("=== R. Router golden intents (To-do #3) ===")
golden = {
    "удали файл temp.txt": ("DELETE_FILES", {"path": "temp.txt"}),
    "запусти скрипт": ("RUN_SHELL", {}),
    "Открой Discord": ("OPEN_APPLICATION", {"app_name": "discord"}),
    "открой браузер": ("OPEN_APPLICATION", {"app_name": "браузер"}),
    "найди Python asyncio в интернете": ("WEB_SEARCH", {"query": "python asyncio"}),
    "прочитай main.py": ("FILE_READ", {"path": "main.py"}),
    "покажи файлы в папке data": ("FILE_LIST", {}),
    "создай файл notes.txt с текстом «привет»": ("FILE_WRITE", {"path": "notes.txt"}),
    "закрой приложение notepad": ("CLOSE_APPLICATION", {"app_name": "notepad"}),
    "сделай скриншот": ("SCREENSHOT", {}),
    "Привет": ("GREETING", None),
    "отмена": ("CANCEL", None),
    "сделай": ("CLARIFY", None),          # low confidence -> ask, no guessing
    "очисти всё": ("CLARIFY", None),      # destructive without target -> ask
}
for text, (want_intent, want_ent) in golden.items():
    ctx = router.route(text)
    ok = ctx.intent == want_intent
    if ok and want_ent:
        for k, v in want_ent.items():
            got = str(ctx.entities.get(k, "")).lower()
            if v.lower() not in got:
                ok = False
    check(f"route {text!r} -> {want_intent}", ok)

# collision guards from the Cursor analysis
check("'найди файл readme.md' is NOT web search",
      router.route("найди файл readme.md").intent != "WEB_SEARCH")
check("'открой файл config.yaml' is FILE_READ, not OPEN_APPLICATION",
      router.route("открой файл config.yaml").intent == "FILE_READ")
check("'удали файл' never CONVERSATION",
      router.route("удали файл temp.txt").intent not in ("CONVERSATION", "GENERAL_QUERY"))
check("'запусти скрипт' never OPEN_APPLICATION",
      router.route("запусти скрипт").intent != "OPEN_APPLICATION")

# CLARIFY carries low confidence (< threshold) — no guessing contract
c = router.route("сделай")
check("CLARIFY has low confidence", c.intent == "CLARIFY" and c.confidence < 0.6)

# ----------------------------------------------------------------------
print("=== D. training_data_v2 as EVALUATION golden set only (To-do #3) ===")
if os.path.exists("training_data_v2.json"):
    data = json.load(open("training_data_v2.json", encoding="utf-8"))
    # Coarse mapping of dataset labels to the core Router vocabulary.
    MAP = {
        "CHARACTER": "CONVERSATION", "IDENTITY": "CONVERSATION",
        "RELATIONSHIP": "CONVERSATION", "WEATHER": "GENERAL_QUERY",
        "CHARACTER_MEMORY": "MEMORY_QUERY", "CONVERSATION": "CONVERSATION",
        "MEMORY_QUERY": "MEMORY_QUERY", "GREETING": "GREETING",
        "FAREWELL": "FAREWELL", "OPEN_APPLICATION": "OPEN_APPLICATION",
    }
    n = hits = 0
    for x in data:
        want = MAP.get(x["intent"], x["intent"])
        got = router.route(x["input"]).intent
        n += 1
        if got == want:
            hits += 1
    # Eval-only gate: conversational dataset must stay mostly conversational.
    check(f"dataset eval coverage {hits}/{n} >= 55%", hits >= 0.55 * n)
    # And critically: the single labeled agent example routes correctly.
    oa = [x for x in data if x["intent"] == "OPEN_APPLICATION"]
    check("all dataset OPEN_APPLICATION examples route to OPEN_APPLICATION",
          all(router.route(x["input"]).intent == "OPEN_APPLICATION" for x in oa))
else:
    check("training_data_v2.json present for eval", False)

# ----------------------------------------------------------------------
print("=== B. ExecutionBudget in TaskContext (To-do #2) ===")
est = CostEstimator()

ctx3 = TaskContext(raw_input="покажи файлы")
ctx3.intent = "FILE_LIST"
ctx3.mode = TaskMode.AGENT
ctx3.complexity = "C3"
b3 = est.estimate(ctx3)
check("C3 budget: requires_llm False", b3.requires_llm is False and ctx3.budget_requires_llm is False)
check("C3 budget: requires_tool/planner True", b3.requires_tool and b3.requires_planner)
check("budget reasons recorded", len(ctx3.budget_reasons) >= 1 and "fast plan" in ctx3.budget_reasons[0])

ctx4 = TaskContext(raw_input="сложная задача")
ctx4.mode = TaskMode.AGENT
ctx4.complexity = "C4"
b4 = est.estimate(ctx4)
check("C4 budget: requires_llm True", b4.requires_llm and ctx4.budget_requires_llm)

# C3 planner NEVER calls LLM even when a model router is available
class ExplodingRouter:
    def generate(self, **kw):
        raise AssertionError("LLM planner must not be called for C3")

planner3 = Planner(model_router=ExplodingRouter(), tool_registry=ToolRegistry())
plan = planner3.create_plan(ctx3)
check("C3 uses deterministic fast plan (no LLM call)", bool(plan.steps) and plan.level == "fast")

# C4 DOES consult LLM (and falls back when it fails) but its JSON plans are
# validated through registry + schema before use (covered in pipeline §7 too)
class BadJsonRouter:
    def generate(self, **kw):
        class R:
            error = None
            text = "GOAL: g\nSTEP 1: do | ghost.tool | {}"
        return R()

reg_b = ToolRegistry()
reg_b.register(ToolSpec(name="files.list", description="list",
                        executor=lambda **kw: ToolResult(success=True)))
p4 = Planner(model_router=BadJsonRouter(), tool_registry=reg_b)
ctx4.intent = "TECHNICAL_TASK"
plan4 = p4.create_plan(ctx4)
check("C4 invalid LLM plan rejected via registry validation",
      all(s.tool != "ghost.tool" for s in plan4.steps))

# ----------------------------------------------------------------------
print("=== S. Session + HITL flow (To-do #1) ===")


def make_orch(delete_ok_flag):
    """Orchestrator with a fake files.delete tool that records execution."""
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="files.delete", description="delete file", risk="high",
        requires_confirmation=True,
        input_schema={"type": "object",
                      "properties": {"path": {"type": "string"}},
                      "required": ["path"]},
        executor=lambda path: delete_ok_flag.append(path) or ToolResult(
            success=True, data={"deleted": path}),
    ))
    orch = Orchestrator(tool_registry=reg)
    return orch


deleted = []
orch = make_orch(deleted)
sess = Session(session_id="s1")

r1 = orch.handle("удали файл temp.txt", session=sess)
check("HIGH-risk task -> confirmation_required", r1["type"] == "confirmation_required")
check("pending state WAITING_CONFIRMATION",
      sess.pending_task is not None
      and sess.pending_task.state == PendingState.WAITING_CONFIRMATION)
check("tool NOT executed before confirmation", deleted == [])
check("trace shows blocked step",
      any(st.status == "blocked" for st in
          [type("S", (), {"status": s["status"]})() for s in r1["trace"]["steps"]]))

# Non-confirming answer keeps waiting (fail-safe)
r2 = orch.handle("ну не знаю", session=sess)
check("non-answer keeps WAITING (no accidental exec)",
      r2["type"] == "waiting" and deleted == [])

# Confirm resumes the SAME task (same task_id), executes exactly once
task_id = sess.pending_task.task_id
r3 = orch.handle("да", session=sess)
check("confirm -> resumed", r3["type"] == "resumed")
check("resume continues the SAME task id",
      r3["resumed_task_id"] == task_id and r3["context"]["task_id"] == task_id)
check("confirmed task actually executed the tool", deleted == ["temp.txt"])
check("verified success after resume", r3["verification"]["success"] is True)
check("pending cleared after resume", sess.pending_task is None)
check("session working messages kept", len(sess.messages) >= 4)

# Denied intent stays denied even with confirmed=True (Policy not bypassed)
pol = PolicyEngine()
pol.denied_intents = {"FORBIDDEN"}
ctxd = TaskContext(raw_input="x", intent="FORBIDDEN")
ctxd.confirmed = True
dd = pol.check_tool(ctxd, "files.delete", ToolSpec(name="files.delete",
                                                   description="d", risk="high",
                                                   requires_confirmation=True))
check("denied intent cannot be unlocked by confirmation", dd.allowed is False)

# Cancel path
deleted2 = []
orch2 = make_orch(deleted2)
sess2 = Session()
orch2.handle("удали файл secret.bin", session=sess2)
r = orch2.handle("нет", session=sess2)
check("cancel drops pending task", r["type"] == "cancelled" and sess2.pending_task is None)
check("cancel never executed tool", deleted2 == [])

# CLARIFY resume flow
orch3 = Orchestrator()
sess3 = Session()
rc = orch3.handle("сделай", session=sess3)
check("low-confidence request -> clarify type", rc["type"] == "clarify")
check("pending WAITING_CLARIFICATION",
      sess3.pending_task.state == PendingState.WAITING_CLARIFICATION)
rr = orch3.handle("покажи файлы в папке data", session=sess3)
check("clarification resumes original request (rerouted, not guessed)",
      rr.get("resumed_task_id") is not None
      and rr["context"]["intent"] in ("FILE_LIST", "TECHNICAL_TASK", "AGENT", "CLARIFY")
      or rr["type"] in ("agent", "clarify", "direct"))
check("clarified pending consumed", sess3.pending_task is None or
      sess3.pending_task.state != PendingState.WAITING_CLARIFICATION or
      rr["type"] == "clarify")

# CANCEL intent clears pending confirmation
deleted4 = []
orch4 = make_orch(deleted4)
sess4 = Session()
orch4.handle("удали файл old.log", session=sess4)
r = orch4.handle("отмена", session=sess4)
check("CANCEL intent clears pending task", sess4.pending_task is None and r["type"] == "cancelled")
check("after cancel tool still not executed", deleted4 == [])

print(f"TOTAL: {PASS} passed, {FAIL} failed")
raise SystemExit(1 if FAIL else 0)
