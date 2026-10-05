from __future__ import annotations

from typing import Dict, List, Optional

from .schemas import ToolSpec, ToolResult


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolSpec]:
        return list(self._tools.values())

    def list_names(self) -> List[str]:
        return list(self._tools.keys())

    def run(self, name: str, **kwargs) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(success=False, error=f"Tool not found: {name}")
        return tool.run(**kwargs)