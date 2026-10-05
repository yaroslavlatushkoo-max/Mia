from __future__ import annotations

from .task_context import TaskContext


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