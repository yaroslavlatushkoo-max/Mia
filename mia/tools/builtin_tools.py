from __future__ import annotations

from ..adapters.system_adapter import SystemAdapter
from ..adapters.file_adapter import FileAdapter
from ..adapters.browser_adapter import BrowserAdapter
from ..adapters.web_adapter import WebAdapter

from .registry import ToolRegistry
from .schemas import ToolSpec
from ..adapters.shell_adapter import ShellAdapter


def register_builtin_tools(
    registry: ToolRegistry,
    sandbox=None,
) -> ToolRegistry:
    """Register the built-in tool set.

    ``sandbox`` (mia.tools.sandbox.PathSandbox) — единый настроенный рабочий
    каталог для файловых операций и shell.safe_run. Если он не передан,
    создаётся песочница по умолчанию из MiaSettings (каталог mia_workspace/,
    не зависит от CWD): файлы вне границы не читаются, не пишутся и не
    удаляются никогда. Обратная совместимость сигнатуры сохранена.
    """
    if sandbox is None:
        from ..config import MiaSettings
        sandbox = MiaSettings.from_env().build_sandbox()

    system = SystemAdapter()
    files = FileAdapter(sandbox=sandbox)
    shell = ShellAdapter(sandbox=sandbox)
    browser = BrowserAdapter()
    web = WebAdapter()

    registry.register(
        ToolSpec(
            name="system.open_app",
            description=(
                "Open a Windows application by its name or executable path "
                "(e.g. notepad, calc, msedge). ALWAYS use this tool to launch "
                "installed applications; do NOT use browser.open for apps."
            ),
            risk="medium",
            requires_confirmation=False,
            input_schema={
                "type": "object",
                "properties": {
                    "app_name": {"type": "string"}
                },
                "required": ["app_name"]
            },
            aliases={"app_name": ["app", "application", "name"]},
            executor=lambda app_name: system.open_app(app_name),
        )
    )

    registry.register(
        ToolSpec(
            name="files.list",
            description="List files and folders in a directory.",
            risk="low",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer"}
                }
            },
            aliases={"path": ["directory", "dir", "folder"]},
            executor=lambda path=".", limit=50: files.list_files(path, int(limit)),
        )
    )

    registry.register(
        ToolSpec(
            name="files.read",
            description="Read a text file.",
            risk="low",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer"}
                },
                "required": ["path"]
            },
            aliases={"path": ["file", "file_path"]},
            executor=lambda path, max_chars=4000: files.read_file(path, int(max_chars)),
        )
    )

    registry.register(
        ToolSpec(
            name="browser.open",
            description="Open a URL. Use background=True to not steal focus.",
            risk="low",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "background": {"type": "boolean", "default": False}
                },
                "required": ["url"]
            },
            executor=lambda url, background=False: browser.open_url(url, background),
        )
    )

    registry.register(
        ToolSpec(
            name="web.search",
            description=(
                "Search the web for a query. STUB: real search backend is "
                "not connected yet; prefer browser.open with a Google search URL."
            ),
            risk="low",
            status="STUB",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            },
            executor=lambda query: web.search(query),
        )
    )

    # ------------------------------------------------------------------
    # Task: safe tool execution — files.write / files.delete / shell.safe_run
    # получили РЕАЛЬНЫЕ executor-ы, но только внутри PathSandbox (единый
    # настроенный рабочий каталог) и только через существующий HITL-механизм:
    # requires_confirmation=True + risk="high" по-прежнему оценивает
    # PolicyEngine.check_tool до любого вызова executor'а. Без подтверждения
    # операция не выполняется (Registry/AgentLoop блокируют на входе).
    # ------------------------------------------------------------------
    registry.register(
        ToolSpec(
            name="files.write",
            description=(
                "Write text content to a file inside the configured Mia "
                "workspace directory (sandboxed; paths outside are refused)."
            ),
            risk="high",
            requires_confirmation=True,
            status="REAL",
            side_effects=["filesystem.write"],
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {"type": "boolean", "default": False},
                },
                "required": ["path", "content"],
            },
            aliases={"path": ["file", "file_path"]},
            executor=lambda path, content, append=False: files.write_file(
                path, content, bool(append)),
        )
    )

    registry.register(
        ToolSpec(
            name="files.delete",
            description=(
                "Delete a single file inside the configured Mia workspace "
                "directory (sandboxed; directories and external paths refuse)."
            ),
            risk="high",
            requires_confirmation=True,
            status="REAL",
            side_effects=["filesystem.delete"],
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            aliases={"path": ["file", "file_path"]},
            executor=lambda path: files.delete_file(path),
        )
    )

    registry.register(
        ToolSpec(
            name="shell.safe_run",
            description=(
                "Run an allowlisted command (echo/dir/ls/pwd/python...) with "
                "no shell interpreter, sandbox cwd, timeout and output cap. "
                "Arbitrary execution is forbidden."
            ),
            risk="high",
            requires_confirmation=True,
            status="REAL",
            side_effects=["process.spawn"],
            timeout=20,
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                },
                "required": ["command"],
            },
            aliases={"command": ["cmd", "script"]},
            executor=lambda command, cwd=None: shell.run(command, cwd),
        )
    )

    return registry