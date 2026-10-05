from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class ToolResult:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class ToolSpec:
    name: str
    description: str
    risk: str = "low"
    requires_confirmation: bool = False
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    executor: Optional[Callable[..., ToolResult]] = None

    def run(self, **kwargs) -> ToolResult:
        if not self.executor:
            return ToolResult(success=False, error=f"Tool {self.name} has no executor")
        try:
            return self.executor(**kwargs)
        except Exception as e:
            return ToolResult(success=False, error=str(e))