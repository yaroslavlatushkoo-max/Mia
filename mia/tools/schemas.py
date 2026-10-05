from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolResult:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    # Verification hint: a tool must report honestly whether its
    # advertised effect was actually observed (CORE_MIGRATION.md §7).
    verified: bool = True

    def to_observation(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "verified": self.verified,
        }


@dataclass
class ToolSpec:
    name: str
    description: str
    risk: str = "low"
    requires_confirmation: bool = False
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    executor: Optional[Callable[..., ToolResult]] = None
    # Migration classification (CORE_MIGRATION.md §5): REAL / ADAPTER / STUB / BROKEN.
    status: str = "REAL"
    side_effects: List[str] = field(default_factory=list)
    timeout: int = 30

    def validate_input(self, kwargs: Dict[str, Any]) -> Optional[str]:
        """Deterministic input validation against the declared schema.

        Returns an error string or None when the call is acceptable.
        """
        schema = self.input_schema or {}
        props = schema.get("properties", {})
        required = schema.get("required", [])

        for key in required:
            if key not in kwargs or kwargs[key] in (None, ""):
                return f"Missing required input '{key}' for tool {self.name}"

        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
        }
        for key, value in kwargs.items():
            prop = props.get(key)
            if not prop:
                continue
            expected = type_map.get(prop.get("type"))
            if expected and value is not None and not isinstance(value, expected):
                try:
                    if expected is int and isinstance(value, str) and value.isdigit():
                        continue
                except Exception:
                    pass
                return f"Input '{key}' of tool {self.name} has wrong type"
        return None

    def to_capability(self) -> Dict[str, Any]:
        """Compact capability description consumed by the Planner."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "status": self.status,
        }

    def run(self, **kwargs) -> ToolResult:
        if not self.executor:
            return ToolResult(
                success=False,
                error=f"Tool {self.name} has no executor",
                verified=False,
            )
        validation_error = self.validate_input(kwargs)
        if validation_error:
            return ToolResult(success=False, error=validation_error, verified=False)
        try:
            return self.executor(**kwargs)
        except Exception as e:
            return ToolResult(success=False, error=str(e), verified=False)