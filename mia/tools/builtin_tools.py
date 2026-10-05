from __future__ import annotations

from ..adapters.system_adapter import SystemAdapter
from ..adapters.file_adapter import FileAdapter
from ..adapters.browser_adapter import BrowserAdapter
from ..adapters.web_adapter import WebAdapter

from .registry import ToolRegistry
from .schemas import ToolSpec


def register_builtin_tools(registry: ToolRegistry) -> ToolRegistry:
    system = SystemAdapter()
    files = FileAdapter()
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

    return registry