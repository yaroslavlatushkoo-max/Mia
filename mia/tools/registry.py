from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schemas import ToolSpec, ToolResult


class ToolRegistry:
    """Capability layer (CORE_MIGRATION.md §5).

    Single source of truth for executable tools. The Planner must obtain
    its capabilities from this registry — never from a duplicated list.
    """

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

    def capabilities(self) -> List[Dict[str, Any]]:
        """Planner-facing capability list, excluding non-executable tools."""
        return [
            t.to_capability()
            for t in self._tools.values()
            if t.executor is not None and t.status != "BROKEN"
        ]

    def capability_names(self) -> List[str]:
        return [c["name"] for c in self.capabilities()]

    def run(self, name: str, **kwargs) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool not found: {name}",
                verified=False,
            )
        return tool.run(**kwargs)