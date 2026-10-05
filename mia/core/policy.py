from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .task_context import TaskContext


@dataclass
class PolicyDecision:
    """Result of a Policy evaluation.

    Per docs/CORE_MIGRATION.md section 3, Policy must influence actual
    execution, not merely produce metadata. AgentLoop consumes this
    decision as the enforcement point before every tool call.
    """

    allowed: bool = True
    risk: str = "low"
    requires_confirmation: bool = False
    confirmed: bool = False
    reason: str = ""
    local_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "confirmed": self.confirmed,
            "reason": self.reason,
            "local_only": self.local_only,
        }


class PolicyEngine:
    def __init__(self):
        self.high_risk_intents = {
            "DELETE_FILES",
            "SYSTEM_CHANGE",
            "INSTALL_SOFTWARE",
            "RUN_SHELL",
        }

        self.confirmation_tools = {
            "files.delete",
            "shell.run",
            "system.modify",
        }

        # Intents that are never executable as agent tasks at this stage;
        # they must be refused by Policy, not silently executed or faked.
        self.denied_intents: set[str] = set()

    # ------------------------------------------------------------------
    # Task-level pre-planning evaluation (backward compatible)
    # ------------------------------------------------------------------
    def evaluate(self, ctx: TaskContext, planned_tool: str | None = None) -> TaskContext:
        ctx.risk = "low"
        ctx.requires_confirmation = False

        if ctx.intent in self.high_risk_intents:
            ctx.risk = "high"
            ctx.requires_confirmation = True

        if planned_tool in self.confirmation_tools:
            ctx.risk = "high"
            ctx.requires_confirmation = True

        if ctx.complexity in {"C4", "C5"}:
            if ctx.risk == "low":
                ctx.risk = "medium"

        return ctx

    # ------------------------------------------------------------------
    # Enforcement point: evaluated per tool call inside AgentLoop
    # ------------------------------------------------------------------
    def check_tool(
        self,
        ctx: TaskContext,
        tool_name: str,
        spec=None,
        decision: Optional[PolicyDecision] = None,
    ) -> PolicyDecision:
        """Decide whether a concrete tool call may execute right now.

        This is the real enforcement point required by the migration
        contract (CORE_MIGRATION.md sections 3, 6, 15). It combines:
        - intent-level policy from TaskContext (set by evaluate());
        - tool metadata from ToolRegistry (risk / requires_confirmation);
        - explicit blocking of risky actions without confirmation.
        """
        d = decision or PolicyDecision()

        if ctx.intent in self.denied_intents:
            d.allowed = False
            d.reason = f"Intent denied by policy: {ctx.intent}"
            return d

        tool_risk = getattr(spec, "risk", "low") or "low"
        tool_requires = bool(getattr(spec, "requires_confirmation", False))

        # Merge task-level and tool-level risk (highest wins).
        risk_order = {"low": 0, "medium": 1, "high": 2}
        d.risk = max(d.risk, tool_risk, key=lambda r: risk_order.get(r, 0))

        # High-risk intent from TaskContext elevates any tool.
        if ctx.risk == "high":
            d.risk = "high"

        needs_confirm = (
            d.requires_confirmation
            or tool_requires
            or tool_name in self.confirmation_tools
            or d.risk == "high"
            or ctx.requires_confirmation
        )
        d.requires_confirmation = needs_confirm

        # Confirmation is the gate: risky tools are blocked while unconfirmed,
        # but once the user has explicitly confirmed (d.confirmed=True) and no
        # other denial applies, execution is allowed. Weakening this branch
        # would make confirmation meaningless; keeping it strict for
        # unconfirmed calls preserves the safety contract.
        if needs_confirm and not d.confirmed:
            d.allowed = False
            d.reason = (
                f"Tool '{tool_name}' requires user confirmation "
                f"(risk={d.risk}); execution blocked until confirmed."
            )
            return d

        # Confirmed (or never required): clear the stale block left by a
        # previous unconfirmed decision passed in via `decision` — otherwise
        # confirmation would never actually unlock execution.
        d.allowed = True
        if "requires user confirmation" in (d.reason or ""):
            d.reason = f"Tool '{tool_name}' confirmed by user; execution allowed."
        return d
