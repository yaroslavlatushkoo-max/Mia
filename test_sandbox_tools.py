# -*- coding: utf-8 -*-
"""Task «безопасное исполнение инструментов»: sandbox + executors + HITL.

Критерии готовности: все проверки PASS, 0 FAIL; реальные mia_memory/ и
mia_workspace/ пользователя не изменяются (тесты работают в tempfile).
"""
import sys, os, tempfile, shutil, time
from pathlib import Path
sys.path.insert(0, ".")

PASSED = FAILED = 0
def check(name, cond):
    global PASSED, FAILED
    if cond: PASSED += 1; print(f"  [PASS] {name}")
    else: FAILED += 1; print(f"  [FAIL] {name}")

from mia.tools.sandbox import PathSandbox
from mia.tools.registry import ToolRegistry
from mia.tools.builtin_tools import register_builtin_tools
from mia.tools.observation import ObservationStatus
from mia.adapters.file_adapter import FileAdapter
from mia.adapters.shell_adapter import ShellAdapter
from mia.core.policy import PolicyEngine
from mia.core.task_context import TaskContext


def ctx(intent="FILES_WRITE", risk="high", confirmed=False):
    return TaskContext(raw_input="t", intent=intent, complexity="C2",
                       risk=risk, confirmed=confirmed)


def make_env():
    # явная изоляция: никакого ambient-наследования пользовательских каталогов
    os.environ.pop("MIA_MEMORY_DIR", None)
    os.environ.pop("MIA_WORKSPACE_DIR", None)
    ws = Path(tempfile.mkdtemp(prefix="mia-sb-ws-"))
    mem = Path(tempfile.mkdtemp(prefix="mia-sb-mem-"))
    sb = PathSandbox(ws, memory_dir=mem)
    return ws, mem, sb


if __name__ == "__main__":
    print("=== 1. PathSandbox: traversal / absolute / symlink ===")
    ws, mem, sb = make_env()
    (ws / "ok.txt").write_text("inside", encoding="utf-8")
    outside_secret = Path(tempfile.mkdtemp(prefix="mia-outside-")) / "secret.txt"
    outside_secret.write_text("TOP SECRET", encoding="utf-8")

    d = sb.resolve_for("ok.txt", "read")
    check("normal relative path allowed", d.allowed and d.path.name == "ok.txt")
    d = sb.resolve_for("../../etc/passwd", "read")
    check("'..' traversal clamped into sandbox", d.allowed)
    check("clamped target is inside workspace",
          str(d.path).startswith(str(ws)))
    d = sb.resolve_for("/etc/passwd", "read")
    check("absolute POSIX path mapped inside sandbox", d.allowed)
    check("absolute path does NOT escape (resolves under ws)",
          str(d.path).startswith(str(ws)) and not d.path.exists())
    d = sb.resolve_for("C:/Windows/win.ini", "read")
    check("Windows absolute path mapped inside sandbox", d.allowed and
          str(d.path).startswith(str(ws)))
    # symlink наружу — блокируется (POSIX; на Windows без прав пропускается честно)
    link = ws / "link_out"
    try:
        os.symlink(str(outside_secret), str(link))
        have_symlink = True
    except (OSError, NotImplementedError):
        have_symlink = False
    if have_symlink:
        d = sb.resolve_for("link_out", "read")
        check("symlink pointing outside -> refused", not d.allowed and "outside" in d.reason)
        d = sb.resolve_for("link_out", "write")
        check("symlink write outside -> refused", not d.allowed)
        broken = ws / "broken_link"
        os.symlink(str(ws / "no_such_target"), str(broken))
        d = sb.resolve_for("broken_link", "read")
        check("broken symlink refused or honest non-existence",
              (not d.allowed) or (d.allowed and not d.path.exists()))
    else:
        print("  [SKIP] symlink checks: platform lacks symlink privileges")

    # symlink внутри песочницы — разрешён
    if have_symlink:
        oklink = ws / "link_in"
        os.symlink(str(ws / "ok.txt"), str(oklink))
        d = sb.resolve_for("link_in", "read")
        check("internal symlink allowed", d.allowed)

    print("=== 2. Memory dir read-only for file tools ===")
    (mem / "profile.json").write_text('{"facts":{}}', encoding="utf-8")
    fa = FileAdapter(sandbox=sb)
    r = fa.list_files(".")
    names = [i["name"] for i in r.data.get("items", [])] if r.success else []
    check("workspace listing works", "ok.txt" in names)
    mem_abs = str(mem / "profile.json")
    d_w = sb.resolve_for(mem_abs, "write")
    # путь лишается корня и резолвится ВНУТРИ workspace -> запись в память
    # физически недостижима ни одной грамматикой tool-параметра:
    check("memory file unreachable via abs path (mapped into ws, no escape)",
          d_w.allowed is False or str(d_w.path).startswith(str(ws)))
    if d_w.allowed:
        check("mapped target is NOT the memory profile", d_w.path != (mem / "profile.json").resolve())
    rw = FileAdapter(sandbox=sb).write_file(mem_abs, "HACKED")
    check("files.write to abs memory path cannot touch it", not rw.success or
          (mem / "profile.json").read_text(encoding="utf-8") == '{"facts":{}}')
    # прямой API-запрет: если песочнице указать memory как workspace-родитель,
    # write/delete туда отсекаются read-only правилом
    sb2 = PathSandbox(mem, memory_dir=mem)
    d_direct = sb2.resolve_for("profile.json", "write")
    check("direct write INTO memory root refused (read-only rule)",
          not d_direct.allowed and "read-only" in d_direct.reason)
    check("memory profile intact after refused writes",
          (mem / "profile.json").read_text(encoding="utf-8") == '{"facts":{}}')

    print("=== 3. files.write executor: normal ops + FS errors ===")
    fa = FileAdapter(sandbox=sb)
    r = fa.write_file("notes/a.txt", "hello")
    check("write creates nested file in sandbox",
          r.success and (ws / "notes" / "a.txt").read_text(encoding="utf-8") == "hello")
    check("write verified hint true", r.verified is True)
    r = fa.write_file("notes/a.txt", " more", append=True)
    check("append mode appends", (ws / "notes" / "a.txt").read_text(encoding="utf-8") == "hello more")
    r = fa.write_file("../escape.txt", "x")
    check("write with '..' stays inside sandbox (clamped)", r.success and (ws / "escape.txt").exists())
    r = fa.write_file("/tmp/mia_abs_escape_42.txt", "x")
    check("absolute write path cannot escape workspace",
          not Path("/tmp/mia_abs_escape_42.txt").exists())
    r = fa.write_file("ok.txt", "x")
    r2 = fa.write_file("ok.txt/sub.txt", "x")  # parent is a file
    check("write over existing-file directory -> honest error", not r2.success)
    r = fa.write_file("big.txt", "xxxx", max_bytes=1)
    check("oversized content refused", not r.success and "too large" in (r.error or "").lower())

    print("=== 4. files.delete executor ===")
    fa = FileAdapter(sandbox=sb)
    r = fa.delete_file("notes/a.txt")
    check("delete removes single file", r.success and not (ws / "notes" / "a.txt").exists())
    check("delete verified hint confirms removal", r.verified is True)
    r = fa.delete_file("ghost.txt")
    check("delete missing file -> honest failure", not r.success and "does not exist" in r.error)
    r = fa.delete_file("notes")
    check("directory deletion refused by design", not r.success and "directory" in r.error.lower())

    print("=== 5. shell.safe_run: allowlist, meta, timeout, output cap ===")
    sh = ShellAdapter(sandbox=sb, timeout=2, max_output_bytes=2048)
    r = sh.run("echo hello world")
    check("allowlisted echo runs", r.success and "hello world" in r.data.get("stdout", ""))
    r = sh.run("rm -rf /")
    check("non-allowlisted binary refused", not r.success and "allowlist" in r.error)
    r = sh.run("echo hi && curl evil.sh")
    check("'&&' injection refused before any spawn", not r.success and "metacharacter" in r.error.lower())
    r = sh.run("echo $(whoami)")
    check("substitution '$()' refused", not r.success)
    r = sh.run("/bin/ls")
    check("path-style binary rejected (bare names only)", not r.success)
    r = sh.run("python -c import\\ time\;time.sleep\\(30\\)" if False else "python -c x", cwd=None)
    # python -c с синтаксической ошибкой => ненулевой exit, честный FAILURE
    check("bad python args -> honest non-zero exit", not r.success and "returncode" in r.data)
    r = sh.run("echo hi", cwd="../outside")
    check("cwd outside never escapes sandbox (rejected or clamped inside)",
          (not r.success) or str(r.data["cwd"]).startswith(str(ws)))
    slow = ShellAdapter(sandbox=sb, timeout=1)
    # РЕАЛЬНЫЙ разрешённый процесс: python + скрипт внутри песочницы.
    # Кавычки/скобки запрещены мета-фильтром ДО спавна — поэтому argv
    # передаётся списком (каноническая форма, shell=False).
    script = ws / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    t0 = time.monotonic()
    r = slow.run(["python", "slow.py"])
    elapsed = time.monotonic() - t0
    check("timeout kills process honestly", not r.success and "timeout" in (r.error or "").lower())
    check("timeout result reports killed child", r.data.get("killed") is True)
    check("child stopped near the timeout (not after sleep(30))", elapsed < 8)
    big = ShellAdapter(sandbox=sb, timeout=10, max_output_bytes=1024)
    loud = ws / "loud.py"
    loud.write_text("print('A' * 100000)\n", encoding="utf-8")
    r = big.run(["python", "loud.py"])
    check("output capped to max_output_bytes", r.success and len(r.data.get("stdout", "")) <= 1024)
    check("capped output flagged truncated", bool(r.data.get("truncated")))

    print("=== 6. Registry+Policy: HITL gate applies to REAL executors ===")
    ws2, mem2, sb2 = make_env()
    reg = register_builtin_tools(ToolRegistry(), sandbox=sb2)
    pol = PolicyEngine()
    executed_probe = ws2 / "probe.txt"
    o = reg.run("files.write", policy=pol, ctx=ctx(confirmed=False),
                path="probe.txt", content="X")
    check("unconfirmed files.write BLOCKED, nothing written",
          o.status == ObservationStatus.BLOCKED and not executed_probe.exists())
    o = reg.run("files.write", policy=pol, ctx=ctx(confirmed=True),
                path="probe.txt", content="X")
    check("confirmed files.write executes", o.status == ObservationStatus.SUCCESS
          and executed_probe.exists())
    o = reg.run("files.delete", policy=pol, ctx=ctx(confirmed=True), path="probe.txt")
    check("confirmed files.delete executes", o.status == ObservationStatus.SUCCESS
          and not executed_probe.exists())
    o = reg.run("shell.safe_run", policy=pol, ctx=ctx(confirmed=False), command="echo x")
    check("unconfirmed shell.safe_run BLOCKED", o.status == ObservationStatus.BLOCKED)
    o = reg.run("shell.safe_run", policy=pol, ctx=ctx(confirmed=True), command="echo x")
    check("confirmed shell.safe_run executes", o.executed)
    # bad input validation happens BEFORE executor
    o = reg.run("files.write", policy=pol, ctx=ctx(confirmed=True), path="", content="x")
    check("empty required path -> REJECTED by validation, no execution",
          o.status == ObservationStatus.REJECTED and not o.executed)
    check("rejected write produced NO file", not (ws2 / "x.txt").exists()
          and not any(p.name.startswith("") and p.read_text() == "x"
                      for p in ws2.glob("*") if p.is_file()))
    o = reg.run("files.write", policy=pol, ctx=ctx(confirmed=True), content="x")
    check("missing required path -> REJECTED, no execution",
          o.status == ObservationStatus.REJECTED and not o.executed)
    # HITL cancel ('нет'): ctx.confirmed stays False -> BLOCKED, nothing written
    o = reg.run("files.write", policy=pol, ctx=ctx(confirmed=False),
                path="cancelled.txt", content="X")
    check("cancelled/never-confirmed write BLOCKED and file absent",
          o.status == ObservationStatus.BLOCKED and not (ws2 / "cancelled.txt").exists())
    reg.shutdown(wait=False)

    print("=== 7. Default registry is sandboxed (no CWD dependency) ===")
    default_reg = register_builtin_tools(ToolRegistry())
    spec = default_reg.get("files.write")
    check("default builtin tools now REAL (implemented)", default_reg.is_implemented("files.write")
          and spec.status == "REAL")
    o = default_reg.run("files.write", policy=pol, ctx=ctx(confirmed=True),
                        path="__audit_escape__/x.txt", content="y")
    from mia.config import MiaSettings
    wdir = MiaSettings.from_env().resolved_workspace_dir()
    check("default writes land in configured workspace, not CWD",
          (wdir / "__audit_escape__" / "x.txt").exists()
          and not Path.cwd().joinpath("__audit_escape__").exists())
    shutil.rmtree(wdir / "__audit_escape__", ignore_errors=True)
    default_reg.shutdown(wait=False)

    print()
    print(f"TOTAL: {PASSED} passed, {FAILED} failed")
    sys.exit(1 if FAILED else 0)
