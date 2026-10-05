from __future__ import annotations

"""Planner — Fast Plan / Deep Plan over ToolRegistry capabilities.

Per docs/CORE_MIGRATION.md §4: the LLM is an enhancement to planning,
not the only source of truth; rule-based fallback must remain working.
Capabilities always come from the ToolRegistry (single source of truth,
§5) — never from a duplicated hardcoded list.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .task_context import TaskContext

# Intent -> default tool mapping for the deterministic rule-based path.
INTENT_TOOL_MAP = {
    "OPEN_APPLICATION": "system.open_app",
    "CLOSE_APPLICATION": "system.close_app",
    "WEB_SEARCH": "browser.open",
    "TECHNICAL_TASK": "files.list",
    "FILE_LIST": "files.list",
    "FILE_READ": "files.read",
    "FILE_WRITE": "files.write",
    "DELETE_FILES": "files.delete",
    "RUN_SHELL": "shell.run",
    "SCREENSHOT": "screen.screenshot",
}


def _search_url(query: str) -> str:
    from urllib.parse import quote_plus

    return "https://www.google.com/search?q=" + quote_plus(query.strip())


def _rule_step(step_id: int, action: str, tool: str, input_data: Dict[str, Any]) -> PlanStep:
    """Build a rule-based plan step with a readable description."""
    return PlanStep(
        step_id=step_id,
        action=action,
        tool=tool,
        input_data=input_data,
        description=action.replace("_", " "),
    )


@dataclass
class PlanStep:
    step_id: int
    action: str
    tool: Optional[str]
    input_data: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class Plan:
    goal: str
    steps: List[PlanStep]
    success_criteria: List[str] = field(default_factory=list)
    level: str = "fast"  # "fast" (C2-C3) | "deep" (C4-C5)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "level": self.level,
            "steps": [
                {
                    "step_id": s.step_id,
                    "action": s.action,
                    "tool": s.tool,
                    "input_data": s.input_data,
                    "description": s.description,
                }
                for s in self.steps
            ],
            "success_criteria": self.success_criteria,
        }


def _search_url(query: str) -> str:
    from urllib.parse import quote_plus

    return "https://www.google.com/search?q=" + quote_plus(query.strip())


def _app_from_url(url: str) -> str:
    """Best-effort app name extraction from a search URL the LLM produced."""
    try:
        from urllib.parse import urlparse, parse_qs, unquote

        q = parse_qs(urlparse(url).query).get("q", [""])[0]
        return unquote(q).strip()
    except Exception:
        return ""


class Planner:
    def __init__(self, model_router=None, tool_registry=None):
        self.model_router = model_router
        # When no registry is provided the planner has NO tools and can
        # only produce empty plans — this forces the single-source-of-truth
        # wiring (Orchestrator passes the real registry).
        self.tool_registry = tool_registry

    # ------------------------------------------------------------------
    def available_tools(self) -> List[str]:
        if not self.tool_registry:
            return []
        return self.tool_registry.capability_names()

    def _is_available(self, tool: Optional[str]) -> bool:
        return bool(tool) and tool in self.available_tools()

    # ------------------------------------------------------------------
    def create_plan(self, ctx: TaskContext) -> Plan:
        level = "deep" if ctx.complexity in {"C4", "C5"} else "fast"

        # Budget-driven planning (To-do #2): the LLM planner is an
        # enhancer allowed only for C4/C5 (budget.requires_llm). For C3
        # and below the deterministic Fast Plan must be used — no LLM.
        llm_allowed = getattr(ctx, "budget_requires_llm", None)
        if llm_allowed is None:
            # Context did not pass through CostEstimator: derive from
            # complexity so the contract still holds.
            llm_allowed = ctx.complexity in {"C4", "C5"}

        if self.model_router and llm_allowed:
            llm_plan = self._try_llm_plan(ctx, level)
            if llm_plan and llm_plan.steps:
                # C4/C5 JSON plan must be validated against ToolRegistry
                # capabilities and tool input schemas before use.
                validated = self.validate_plan(llm_plan, ctx)
                if validated is not None:
                    validated.level = level
                    return validated
        return self._rule_based_plan(ctx, level)

    # ------------------------------------------------------------------
    def validate_plan(self, plan: Plan, ctx: Optional[TaskContext] = None) -> Optional[Plan]:
        """Validate an LLM-produced plan against ToolRegistry capabilities.

        Returns the (possibly repaired) plan, or None when the plan must be
        replaced by the deterministic rule-based fallback. Repair rules are
        capability-driven, not app-name hardcodes:
        - a step using browser.open to satisfy an OPEN_APPLICATION intent is
          rewritten to the registered system tool with the right parameter;
        - any remaining unknown/unavailable tool invalidates the whole plan;
        - every surviving step's input_data is checked against the tool's
          input_schema via ToolSpec.validate_input (schema validation is
          mandatory for C4/C5 LLM plans).
        """
        available = set(self.available_tools())
        system_tool = INTENT_TOOL_MAP.get("OPEN_APPLICATION")
        usable_system = bool(system_tool) and system_tool in available

        for step in plan.steps:
            if step.tool == "browser.open" and ctx is not None \
                    and ctx.intent == "OPEN_APPLICATION" and usable_system:
                # Wrong decomposition: opening an application is a SYSTEM
                # action, not a web search. Route it to the system tool.
                app_name = (
                    ctx.entities.get("app_name")
                    or step.input_data.get("app_name")
                    or _app_from_url(step.input_data.get("url", ""))
                    or ctx.raw_input
                )
                step.tool = system_tool
                step.action = step.action or "open_application"
                step.input_data = {"app_name": app_name}

        for step in plan.steps:
            if step.tool and step.tool not in available:
                return None
            # Schema-level validation against the registered tool contract.
            if step.tool and self.tool_registry is not None:
                spec = self.tool_registry.get(step.tool)
                if spec is not None:
                    normalized = spec.normalize_input(dict(step.input_data))
                    err = spec.validate_input(normalized)
                    if err:
                        return None
                    step.input_data = normalized
        return plan

    # ------------------------------------------------------------------
    def _try_llm_plan(self, ctx: TaskContext, level: str) -> Optional[Plan]:
        try:
            caps = self.tool_registry.capabilities() if self.tool_registry else []
            if not caps:
                return None
            tools_desc = "\n".join(
                [f"- {c['name']}: {c['description']} (risk={c['risk']})" for c in caps]
            )
            max_steps = 5 if level == "fast" else 8

            prompt = f"""Ты — планировщик задач для ИИ-ассистента Мии.

Доступные инструменты:
{tools_desc}

ВАЖНО: Для browser.open ВСЕГДА используй только Google-поиск:
{{"url": "https://www.google.com/search?q=ЗАПРОС"}}

НЕ придумывай прямые URL! Только Google-поиск.

Запрос пользователя: {ctx.raw_input}

Создай план из 1-{max_steps} шагов. Ответь строго в формате:
GOAL: <цель>
STEP 1: <action> | <tool> | <input_json>
STEP 2: ...
SUCCESS: <критерий успеха>"""

            response = self.model_router.generate(
                prompt=prompt,
                system_prompt="Ты планировщик. Используй только Google-поиск для browser.open. Не придумывай URL.",
                max_tokens=512,
                preferred="chat"
            )

            if response.error or not response.text:
                return None

            return self._parse_llm_plan(response.text, ctx)

        except Exception as e:
            print(f"[Planner] LLM ошибка: {e}")
            return None

    def _parse_llm_plan(self, text: str, ctx: TaskContext) -> Plan:
        lines = text.strip().split("\n")
        goal = ctx.raw_input
        steps = []
        success_criteria = []

        for line in lines:
            line = line.strip()
            if line.startswith("GOAL:"):
                goal = line[5:].strip()
            elif line.startswith("STEP"):
                parts = line.split("|")
                if len(parts) >= 2:
                    step_num = len(steps) + 1
                    action = parts[0].split(":", 1)[-1].strip() if ":" in parts[0] else parts[0].strip()
                    tool = parts[1].strip() if len(parts) > 1 else None
                    input_str = parts[2].strip() if len(parts) > 2 else "{}"

                    try:
                        import json
                        input_data = json.loads(input_str) if input_str.startswith("{") else {}
                    except:
                        input_data = {}

                    # Валидация URL для browser.open
                    if tool == "browser.open":
                        url = input_data.get("url", "")
                        if "google.com" not in url:
                            input_data["url"] = _search_url(ctx.raw_input)

                    steps.append(PlanStep(
                        step_id=step_num,
                        action=action,
                        # Keep unknown tools as explicit failed steps so
                        # Verification sees them — never silently drop them.
                        tool=tool,
                        input_data=input_data,
                        description=action
                    ))
            elif line.startswith("SUCCESS:"):
                success_criteria.append(line[8:].strip())

        return Plan(goal=goal, steps=steps, success_criteria=success_criteria)

    # ------------------------------------------------------------------
    def _rule_based_plan(self, ctx: TaskContext, level: str = "fast") -> Plan:
        intent = ctx.intent
        ent = ctx.entities

        if intent == "OPEN_APPLICATION":
            app_name = ent.get("app_name", "")
            return Plan(
                goal=f"Open application: {app_name or 'unknown'}",
                steps=[_rule_step(1, "open_application", "system.open_app", {"app_name": app_name})],
                success_criteria=["Application actually launched"],
                level=level,
            )

        if intent == "CLOSE_APPLICATION":
            app_name = ent.get("app_name", "")
            return Plan(
                goal=f"Close application: {app_name or 'unknown'}",
                steps=[_rule_step(1, "close_application", "system.close_app", {"app_name": app_name})],
                success_criteria=["Application actually closed"],
                level=level,
            )

        if intent == "WEB_SEARCH":
            query = ent.get("query") or ctx.raw_input
            return Plan(
                goal=f"Search: {query}",
                steps=[_rule_step(1, "open_search", "browser.open", {"url": _search_url(query)})],
                success_criteria=["Search page opened"],
                level=level,
            )

        if intent == "FILE_LIST":
            path = ent.get("path") or "."
            return Plan(
                goal=f"List files in: {path}",
                steps=[_rule_step(1, "list_files", "files.list", {"path": path, "limit": 50})],
                success_criteria=["Directory listed"],
                level=level,
            )

        if intent == "FILE_READ":
            path = ent.get("path") or ""
            return Plan(
                goal=f"Read file: {path or 'unknown'}",
                steps=[_rule_step(1, "read_file", "files.read", {"path": path})],
                success_criteria=["File content read"],
                level=level,
            )

        if intent == "FILE_WRITE":
            path = ent.get("path") or ""
            content = ent.get("content", "")
            return Plan(
                goal=f"Write file: {path or 'unknown'}",
                steps=[_rule_step(1, "write_file", "files.write", {"path": path, "content": content})],
                success_criteria=["File written and confirmed"],
                level=level,
            )

        if intent == "DELETE_FILES":
            path = ent.get("path") or ""
            return Plan(
                goal=f"Delete: {path or 'unspecified'}",
                steps=[_rule_step(1, "delete_file", "files.delete", {"path": path})],
                success_criteria=["File actually removed (requires confirmation)"],
                level=level,
            )

        if intent == "RUN_SHELL":
            command = ent.get("command") or ""
            return Plan(
                goal=f"Run command: {command or 'unspecified'}",
                steps=[_rule_step(1, "run_shell", "shell.run", {"command": command})],
                success_criteria=["Command executed with exit code 0 (requires confirmation)"],
                level=level,
            )

        if intent == "SCREENSHOT":
            path = ent.get("path") or "screenshot.png"
            return Plan(
                goal="Take a screenshot",
                steps=[_rule_step(1, "take_screenshot", "screen.screenshot", {"path": path})],
                success_criteria=["Screenshot file saved"],
                level=level,
            )

        if intent == "TECHNICAL_TASK":
            if level == "deep":
                # Deep plan: inspect directory, then read the most
                # relevant-looking file (deterministic skeleton; the LLM
                # may replace it with a richer plan when available).
                return Plan(
                    goal=ctx.raw_input,
                    steps=[
                        _rule_step(1, "inspect_directory", "files.list", {"path": ".", "limit": 30}),
                        _rule_step(2, "read_key_file", "files.read", {"path": "./main.py"}),
                    ],
                    success_criteria=["Directory inspected", "Relevant file content read"],
                    level=level,
                )
            return Plan(
                goal=ctx.raw_input,
                steps=[_rule_step(1, "inspect_directory", "files.list", {"path": ".", "limit": 30})],
                success_criteria=["Directory inspected"],
                level=level,
            )

        return Plan(goal=ctx.raw_input, steps=[], success_criteria=[], level=level)

    # ------------------------------------------------------------------
    def replan(self, ctx: TaskContext, failed_plan: Plan, error: str) -> Plan:
        """Produce an alternative plan after a failure (bounded use).

        Strategy: drop steps that failed for known reasons and substitute
        a capability-backed alternative when possible.
        """
        available = set(self.available_tools())
        new_steps: List[PlanStep] = []

        for step in failed_plan.steps:
            keep = True
            replacement: Optional[PlanStep] = None

            # web.search is a stub at this migration stage — replace it
            # with browser.open Google search when that capability exists.
            if step.tool == "web.search" and "stub" in error.lower():
                if "browser.open" in available:
                    replacement = PlanStep(
                        step_id=len(new_steps) + 1,
                        action="open_search",
                        tool="browser.open",
                        input_data={"url": _search_url(step.input_data.get("query", ctx.raw_input))},
                        description="Fallback: open Google search instead of stubbed web.search",
                    )
                keep = False

            # Missing file for files.read — drop the read, keep listing.
            if step.tool == "files.read" and ("does not exist" in error.lower() or "not found" in error.lower()):
                keep = False

            if keep:
                new_steps.append(step)
            elif replacement is not None:
                new_steps.append(replacement)

        # Reindex
        for i, s in enumerate(new_steps, start=1):
            s.step_id = i

        if not new_steps:
            if "browser.open" in available:
                new_steps = [PlanStep(1, "fallback_search", "browser.open", {
                    "url": _search_url(ctx.raw_input)
                })]

        return Plan(
            goal=failed_plan.goal,
            steps=new_steps,
            success_criteria=failed_plan.success_criteria,
            level=failed_plan.level,
        )