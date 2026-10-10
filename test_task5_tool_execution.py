# -*- coding: utf-8 -*-
"""Task 5 regression suite: Tool Execution + Timeout + Observation.

All tests are UNIT level with deterministic fakes; no real Ollama, no
real Windows GUI launch. Live-environment checks are explicitly marked
as NOT RUN in the final report (see docstrings), never faked as passing.
"""
import sys, time, threading
sys.path.insert(0, ".")

PASSED = FAILED = 0
def check(name, cond):
    global PASSED, FAILED
    if cond: PASSED += 1; print(f"  [PASS] {name}")
    else: FAILED += 1; print(f"  [FAIL] {name}")

from mia.tools.registry import ToolRegistry
from mia.tools.schemas import ToolSpec, ToolResult
from mia.tools.observation import Observation, ObservationStatus
from mia.tools.compressor import ObservationCompressor
from mia.tools.builtin_tools import register_builtin_tools
from mia.core.policy import PolicyEngine
from mia.core.task_context import TaskContext
from mia.core.execution_trace import ExecutionTrace


def make_ctx(text="тест", intent="FILES_LIST", risk="low", confirmed=False):
    return TaskContext(raw_input=text, intent=intent,
                       complexity="C2", risk=risk, confirmed=confirmed)


if __name__ == "__main__":
    print("=== 1. Registry: REGISTERED / IMPLEMENTED / EXECUTED states ===")
    reg = ToolRegistry()
    calls = []
    reg.register(ToolSpec(name="ok.tool", description="d",
                          executor=lambda: (calls.append(1), ToolResult(success=True, data={"v": 1}))[1]))
    reg.register(ToolSpec(name="no.exec", description="d", status="ADAPTER", executor=None))
    reg.register(ToolSpec(name="boom.tool", description="d",
                          executor=lambda: (_ for _ in ()).throw(RuntimeError("executor exploded"))))
    reg.register(ToolSpec(name="badret.tool", description="d", executor=lambda: "not a ToolResult"))
    reg.register(ToolSpec(name="fail.tool", description="d",
                          executor=lambda: ToolResult(success=False, error="business failure")))

    check("registered tool is found", reg.get("ok.tool") is not None)
    check("is_registered true for registered", reg.is_registered("ok.tool"))
    check("is_registered false for unknown", not reg.is_registered("ghost.tool"))
    check("is_implemented true with executor", reg.is_implemented("ok.tool"))
    check("is_implemented false without executor", not reg.is_implemented("no.exec"))

    r = reg.run("ok.tool")
    check("executed tool -> Observation", isinstance(r, Observation))
    check("executed tool -> SUCCESS", r.status == ObservationStatus.SUCCESS)
    check("executor actually called", len(calls) == 1)
    # EXECUTED != VERIFIED, proven behaviorally: a successful execution whose
    # executor could NOT confirm its effect must not be reported as verified.
    no_ver_reg = ToolRegistry()
    no_ver_reg.register(ToolSpec(name="unver.tool", description="d",
                                 executor=lambda: ToolResult(success=True, verified=False)))
    no_ver_obs = no_ver_reg.run("unver.tool")
    check("EXECUTED without verification hint -> succeeded True", no_ver_obs.succeeded)
    check("EXECUTED without verification hint -> executed True", no_ver_obs.executed)
    check("EXECUTED without verification hint -> verified False", not no_ver_obs.verified)
    check("EXECUTED without verification hint -> trace verified False",
          no_ver_obs.to_trace_observation()["verified"] is False)
    # Registry itself never fabricates the hint: absent metadata.verified -> False
    bare = Observation(tool="x", status=ObservationStatus.SUCCESS)
    check("bare SUCCESS Observation defaults to verified False (UNKNOWN)", not bare.verified)
    check("bare SUCCESS trace shape keeps verified False",
          bare.to_trace_observation()["verified"] is False)
    r2 = reg.run("ghost.tool")
    check("unknown tool -> legacy honest failure", not r2.success and not r2.verified)
    rb = reg.run("boom.tool")
    check("raising executor -> FAILURE Observation", rb.status == ObservationStatus.FAILURE)
    check("raising executor -> not success", not rb.success)
    check("raising executor keeps error text", "exploded" in (rb.error or ""))
    rr = reg.run("badret.tool")
    check("unsupported return type -> FAILURE (never fake SUCCESS)",
          rr.status == ObservationStatus.FAILURE)
    rf = reg.run("fail.tool")
    check("returned failure stays FAILURE", rf.status == ObservationStatus.FAILURE)
    check("failure has no success flag", not rf.success)

    print("=== 2. NOT_IMPLEMENTED honesty ===")
    rn = reg.run("no.exec")
    check("missing executor -> NOT_IMPLEMENTED", rn.status == ObservationStatus.NOT_IMPLEMENTED)
    check("NOT_IMPLEMENTED is not success", not rn.success)
    check("NOT_IMPLEMENTED is not executed", not rn.executed)
    check("NOT_IMPLEMENTED metadata says implemented=false",
          rn.metadata.get("implemented") is False)

    print("=== 3. Observation fields / duration / stdout / stderr ===")
    obs = Observation(tool="x", status=ObservationStatus.SUCCESS, summary="s",
                      stdout="out", stderr="", duration=0.5, metadata={"k": "v"})
    check("fields present", obs.tool == "x" and obs.stdout == "out" and obs.duration == 0.5)
    d = obs.to_dict()
    check("to_dict has all keys", set(d) == {"tool","status","summary","stdout","stderr","duration","metadata"})
    check("statuses enum complete", {s.value for s in ObservationStatus} ==
          {"SUCCESS","FAILURE","TIMEOUT","NOT_IMPLEMENTED","BLOCKED","CANCELLED","REJECTED"})

    # duration measured for real
    slow_reg = ToolRegistry()
    slow_reg.register(ToolSpec(name="slow.ok", description="d", timeout=5,
                               executor=lambda: (time.sleep(0.2), ToolResult(success=True))[1]))
    rs = slow_reg.run("slow.ok")
    check("duration really measured (>0.15s)", rs.duration > 0.15)
    # stdout captured from legacy data
    so = ToolRegistry(); so.register(ToolSpec(name="echo", description="d",
            executor=lambda: ToolResult(success=True, data={"stdout": "hello out"})))
    re_ = so.run("echo")
    check("stdout captured into Observation", re_.stdout == "hello out")
    se = ToolRegistry(); se.register(ToolSpec(name="err", description="d",
            executor=lambda: ToolResult(success=False, error="bad thing happened")))
    res_ = se.run("err")
    check("stderr carries error info", "bad thing" in res_.stderr)

    print("=== 4. REAL TIMEOUT: blocking executor does not block caller ===")
    tout_reg = ToolRegistry()
    release = threading.Event()
    def hanging():
        release.wait(30)  # blocks far beyond tool timeout
        return ToolResult(success=True)
    tout_reg.register(ToolSpec(name="hang.tool", description="d", timeout=1, executor=hanging))
    t0 = time.monotonic()
    rt = tout_reg.run("hang.tool")
    elapsed = time.monotonic() - t0
    check("timeout returned control quickly (<3s)", elapsed < 3.0)
    check("hanging executor -> TIMEOUT", rt.status == ObservationStatus.TIMEOUT)
    check("TIMEOUT is not success", not rt.success)
    check("TIMEOUT is not executed (worker may still run)", not rt.executed)
    check("TIMEOUT honestly reports worker_may_still_run",
          rt.metadata.get("worker_may_still_run") is True)
    check("TIMEOUT duration ~ limit", 0.9 <= rt.duration < 3.0)
    release.set()  # cleanup background worker
    # no per-call pool leak: single shared pool reused
    p1 = tout_reg._executor_pool(); p2 = tout_reg._executor_pool()
    check("shared bounded pool reused (no new pool per call)", p1 is p2)
    tout_reg.shutdown(wait=False)
    check("shutdown releases pool", tout_reg._pool is None)

    print("=== 5. Compressor: head/tail/marker/determinism/errors preserved ===")
    comp = ObservationCompressor(max_chars=200)
    short = "small output"
    c1, t1 = comp.compress_stream(short)
    check("short output unchanged", c1 == short and t1 is False)
    long_text = ("HEADMARKER-" + "x" * 5000 + "-TAILMARKER")
    c2, t2 = comp.compress_stream(long_text)
    check("long output truncated", t2 is True and len(c2) < len(long_text))
    check("head preserved", c2.startswith("HEADMARKER-"))
    check("tail preserved", c2.endswith("-TAILMARKER"))
    check("truncation marker present", "omitted" in c2)
    c3, _ = comp.compress_stream(long_text)
    check("deterministic: same input -> same output", c2 == c3)
    big_err = "ValueError: root cause here\n" + ("noise line\n" * 2000) + "File \"app.py\", line 1"
    obig = Observation(tool="t", status=ObservationStatus.FAILURE, summary="ValueError: root cause here",
                       stderr=big_err, stdout="y" * 10000)
    cob = comp.compress(obig)
    check("error headline survives compression", "root cause" in cob.stderr)
    check("traceback end survives compression", 'File "app.py"' in cob.stderr)
    check("compression flags recorded", "stderr" in cob.metadata.get("compressed_streams", []) and
          "stdout" in cob.metadata.get("compressed_streams", []))
    check("status/summary not destroyed by compression",
          cob.status == ObservationStatus.FAILURE and cob.summary == obig.summary)
    check("input observation not mutated", obig.stdout.count("y") == 10000)

    print("=== 6. open_app adapter over LEGACY SystemSkills/config.APPS ===")
    import mia.adapters.system_adapter as sa_mod
    import mia.adapters.legacy_system_bridge as bridge_mod

    class FakeSkills:
        def __init__(self): self.find_calls = []; self.fuzzy_calls = []
        def find_app(self, exe):
            self.find_calls.append(exe)
            return {"notepad.exe": "C:\\Windows\\notepad.exe"}.get(exe)
        def find_app_fuzzy(self, name):
            self.fuzzy_calls.append(name)
            return None

    fake_skills = FakeSkills()
    orig_get = bridge_mod.get_system_skills
    bridge_mod.get_system_skills = lambda: fake_skills
    sa_mod.get_system_skills = lambda: fake_skills
    try:
        # resolution goes through legacy find_app — no second APPS dict
        target, available = bridge_mod.resolve_app.__wrapped__ if hasattr(bridge_mod.resolve_app, "__wrapped__") else (None, None)
    finally:
        pass

    # Re-point resolve_app's internal lookup at our fake by patching module attr
    # used inside resolve_app: it calls get_system_skills() from its own module.
    target, avail = bridge_mod.resolve_app("блокнот")
    check("legacy stack detected available", avail is True)
    check("resolve went through legacy find_app/fuzzy",
          bool(fake_skills.find_calls) or bool(fake_skills.fuzzy_calls))

    adapter = sa_mod.SystemAdapter()
    # app found + launch attempted successfully (monkeypatch _launch to observe path)
    launched = {}
    def fake_launch(t, n):
        launched["target"] = t
        return ToolResult(success=True, data={"app_name": n, "target": t, "resolver": "legacy"}, verified=True)
    adapter._launch = fake_launch
    ra = adapter.open_app("notepad")
    check("found app -> attempted launch with resolved target",
          ra.success and launched.get("target") == "C:\\Windows\\notepad.exe")
    check("result marks legacy resolver used", ra.data.get("resolver") == "legacy")

    # app not found
    target_none, avail_none = bridge_mod.resolve_app("несуществующая_программа_xyz")
    check("unknown app resolves to None while legacy available",
          target_none is None and avail_none is True)
    rn2 = sa_mod.SystemAdapter().open_app("несуществующая_программа_xyz")
    check("unknown app -> FAILURE, not success", not rn2.success and rn2.verified is False)
    check("unknown app reason is APP_NOT_FOUND", rn2.data.get("reason") == "APP_NOT_FOUND")

    # launch failure
    def fail_launch(t, n):
        return ToolResult(success=False, error=f"Launch failed for '{n}'", verified=False,
                          data={"reason": "LAUNCH_FAILED"})
    af = sa_mod.SystemAdapter(); af._launch = fail_launch
    # ensure resolve finds something
    fake_skills2 = FakeSkills(); fake_skills2.find_app = lambda exe: "C:\\a\\b.exe"
    bridge_mod.get_system_skills = lambda: fake_skills2
    rl = af.open_app("b")
    check("launch failure -> FAILURE honest", not rl.success and rl.data.get("reason") == "LAUNCH_FAILED")

    # legacy unavailable (Linux reality) -> honest failure, no fake success
    bridge_mod.get_system_skills = lambda: None
    ru = sa_mod.SystemAdapter().open_app("notepad")
    check("legacy unavailable -> honest FAILURE", not ru.success)
    check("legacy unavailable reason reported", ru.data.get("reason") == "LEGACY_UNAVAILABLE")
    bridge_mod.get_system_skills = orig_get

    # registry-level: system.open_app goes through adapter
    full_reg = register_builtin_tools(ToolRegistry())
    check("builtin registry implements system.open_app", full_reg.is_implemented("system.open_app"))
    ropen = full_reg.run("system.open_app", app_name="notepad")
    check("open_app via registry returns Observation", isinstance(ropen, Observation))
    check("on Linux env open_app never reports fake SUCCESS", not ropen.success)

    print("=== 7. files.write / files.delete / shell.safe_run: sandbox + HITL honesty ===")
    # Contract history: at Task 5 these tools were REGISTERED-but-NOT_IMPLEMENTED.
    # Now they have REAL executors, but safety must be provably unchanged:
    # unconfirmed calls stay BLOCKED (executor never invoked), confirmed calls
    # execute ONLY inside the configured sandbox.
    import tempfile as _tf
    from pathlib import Path as _P
    from mia.tools.sandbox import PathSandbox as _PS
    _ws = _P(_tf.mkdtemp(prefix="mia-ws-")); _mem = _P(_tf.mkdtemp(prefix="mia-mem-"))
    _sb_reg = register_builtin_tools(ToolRegistry(), sandbox=_PS(_ws, memory_dir=_mem))
    pol7 = PolicyEngine()
    for tname in ("files.write", "files.delete", "shell.safe_run"):
        check(f"{tname} registered", _sb_reg.is_registered(tname))
        check(f"{tname} now implemented (real executor)", _sb_reg.is_implemented(tname))
        spec = _sb_reg.get(tname)
        check(f"{tname} high-risk + confirmation contract",
              spec.risk == "high" and spec.requires_confirmation)
        payload = ({"path": "a.txt", "content": "x"} if "files" in tname else {"command": "echo hi"})
        blocked = _sb_reg.run(tname, policy=pol7,
                              ctx=make_ctx(intent="DELETE_FILES", risk="high"), **payload)
        check(f"{tname} UNCONFIRMED -> BLOCKED (HITL not bypassed)",
              blocked.status == ObservationStatus.BLOCKED and not blocked.executed)
        ok_ctx = make_ctx(intent="DELETE_FILES", risk="high", confirmed=True)
        done = _sb_reg.run(tname, policy=pol7, ctx=ok_ctx, **payload)
        check(f"{tname} CONFIRMED -> executed inside sandbox",
              done.status in (ObservationStatus.SUCCESS, ObservationStatus.FAILURE) and done.executed)
    # write+delete roundtrip with verification hints
    wobs = _sb_reg.run("files.write", policy=pol7,
                       ctx=make_ctx(risk="high", confirmed=True),
                       path="note.txt", content="hello sandbox")
    check("files.write SUCCESS on disk", wobs.status == ObservationStatus.SUCCESS)
    check("files.write effect verified", (_ws / "note.txt").read_text(encoding="utf-8") == "hello sandbox")
    dabs = _sb_reg.run("files.delete", policy=pol7,
                       ctx=make_ctx(risk="high", confirmed=True), path="note.txt")
    check("files.delete SUCCESS removes file", dabs.status == ObservationStatus.SUCCESS
          and not ( _ws / "note.txt").exists())
    _sb_reg.shutdown(wait=False)

    print("=== 8. Policy gate BEFORE executor (defense-in-depth in Registry) ===")
    executed_flag = []
    pol_reg = ToolRegistry()
    pol_reg.register(ToolSpec(name="danger.tool", description="d", risk="high",
                              requires_confirmation=True,
                              executor=lambda: (executed_flag.append(1), ToolResult(success=True))[1]))
    policy = PolicyEngine()
    ctx_danger = make_ctx(intent="DELETE_FILES", risk="high")
    rp = pol_reg.run("danger.tool", policy=policy, ctx=ctx_danger)
    check("unconfirmed dangerous tool -> BLOCKED", rp.status == ObservationStatus.BLOCKED)
    check("BLOCKED means executor was NEVER invoked", executed_flag == [])
    check("BLOCKED not success", not rp.success)
    ctx_ok = make_ctx(intent="DELETE_FILES", risk="high", confirmed=True)
    rp2 = pol_reg.run("danger.tool", policy=policy, ctx=ctx_ok)
    check("confirmed execution proceeds", rp2.status == ObservationStatus.SUCCESS)
    check("after confirmation executor ran", executed_flag == [1])

    print("=== 9. ExecutionTrace integration: Observation -> trace, EXECUTED!=VERIFIED ===")
    trace = ExecutionTrace(task_id="tt")
    step_rec = trace.add_step("do", "ok.tool", {})
    trace_obs = r.to_trace_observation()   # r = successful Observation from section 1
    trace.record_observation(step_rec, observation=trace_obs, error=trace_obs.get("error"))
    check("trace step got observation", step_rec.observation is not None)
    check("observation stored in trace artifacts (single history)",
          any(a.get("kind") == "observation" and a.get("tool") == "ok.tool" for a in trace.artifacts))
    check("trace observation carries structured status", trace_obs.get("status") == "SUCCESS")
    # TIMEOUT must not look verified-successful in trace terms
    tout_obs = rt.to_trace_observation()
    check("TIMEOUT -> success False in trace shape", tout_obs["success"] is False)
    check("TIMEOUT -> verified False in trace shape", tout_obs["verified"] is False)
    check("TIMEOUT -> error present", bool(tout_obs["error"]))

    print("=== 10. Session/HITL regression: confirmation flow still gates execution ===")
    from mia.core.session import Session, PendingTask, PendingState

    sess = Session(session_id="s1")
    sess.pending_task = PendingTask(
        task_id="hitl1", raw_input="удали все файлы", intent="DELETE_FILES",
        state=PendingState.WAITING_CONFIRMATION, reason="high risk",
    )
    resume_yes = sess.try_resume("да")
    check("WAITING_CONFIRMATION + 'да' -> confirm resume",
          resume_yes is not None and resume_yes["kind"] == "confirm")

    sess2 = Session(session_id="s2")
    sess2.pending_task = PendingTask(
        task_id="hitl2", raw_input="удали все файлы", intent="DELETE_FILES",
        state=PendingState.WAITING_CONFIRMATION, reason="high risk",
    )
    resume_no = sess2.try_resume("нет")
    check("WAITING_CONFIRMATION + 'нет' -> cancel resume",
          resume_no is not None and resume_no["kind"] == "cancel")

    sess3 = Session(session_id="s3")
    sess3.pending_task = PendingTask(
        task_id="hitl3", raw_input="удали все файлы", intent="DELETE_FILES",
        state=PendingState.WAITING_CONFIRMATION, reason="high risk",
    )
    resume_other = sess3.try_resume("а какая у меня память")
    check("non-confirm answer keeps risky action blocked (fail-safe)",
          resume_other is None or resume_other.get("kind") not in ("confirm",))

    # End-to-end semantics of the HITL contract at Registry boundary:
    ex_before = list(executed_flag)
    r_unconf = pol_reg.run("danger.tool", policy=policy,
                           ctx=make_ctx(intent="DELETE_FILES", risk="high"))
    check("unconfirmed run BLOCKED, executor untouched",
          r_unconf.status == ObservationStatus.BLOCKED and executed_flag == ex_before)
    r_conf = pol_reg.run("danger.tool", policy=policy,
                         ctx=make_ctx(intent="DELETE_FILES", risk="high", confirmed=True))
    check("after user confirmation ('да' -> ctx.confirmed) executor runs exactly once",
          r_conf.status == ObservationStatus.SUCCESS and len(executed_flag) == len(ex_before) + 1)

    print("=== 11. Regression: budget exhausted at entry (max_steps == 0) ===")
    # Boundary fix regression: AgentLoop.run() with a NON-EMPTY plan but zero
    # remaining step budget must terminate gracefully — previously it raised
    # UnboundLocalError on the unbound `verification` variable.
    from mia.core.agent_loop import AgentLoop
    from mia.core.execution_trace import ExecutionStatus
    from mia.core.planner import Plan, PlanStep


    class _OneStepPlanner:
        def create_plan(self, ctx):
            return Plan(goal="g", steps=[
                PlanStep(step_id=1, action="do", tool="ok.tool", input_data={})
            ])

        def replan(self, ctx, plan, error):
            return plan


    _exec_before = len(calls)
    loop0 = AgentLoop(tool_registry=reg, planner=_OneStepPlanner())
    ctx0 = make_ctx()
    trace0 = ExecutionTrace(task_id="tt0")
    trace0.max_steps = 0
    res0 = loop0.run(ctx0, trace0)   # must NOT raise
    check("max_steps=0 -> no exception, graceful terminal outcome", True)
    check("max_steps=0 -> status FAILED (no fake success)",
          trace0.status == ExecutionStatus.FAILED)
    check("max_steps=0 -> verification is None (nothing was verified)",
          res0["verification"] is None)
    check("max_steps=0 -> executor never called", len(calls) == _exec_before)
    check("max_steps=0 -> no steps recorded in trace", len(trace0.steps) == 0)
    check("max_steps=0 -> trace finalized (finished_at set)",
          trace0.finished_at is not None)
    check("max_steps=0 -> honest error recorded in trace",
          any("budget" in e.lower() for e in trace0.errors))
    check("max_steps=0 -> final answer produced", bool(res0["answer"]))

    print()
    print(f"TOTAL: {PASSED} passed, {FAILED} failed")
    sys.exit(1 if FAILED else 0)
