from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .task_context import TaskContext


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
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


class Planner:
    def __init__(self, model_router=None):
        self.model_router = model_router
        self.available_tools = [
            "system.open_app",
            "files.list",
            "files.read",
            "browser.open",
            "web.search",
        ]

    def create_plan(self, ctx: TaskContext) -> Plan:
        if self.model_router:
            llm_plan = self._try_llm_plan(ctx)
            if llm_plan and llm_plan.steps:
                return llm_plan
        return self._rule_based_plan(ctx)

    def _try_llm_plan(self, ctx: TaskContext) -> Optional[Plan]:
        try:
            tools_desc = "\n".join([f"- {t}" for t in self.available_tools])

            prompt = f"""Ты — планировщик задач для ИИ-ассистента Мии.

Доступные инструменты:
{tools_desc}

ВАЖНО: Для browser.open ВСЕГДА используй только Google-поиск:
{{"url": "https://www.google.com/search?q=ЗАПРОС"}}

НЕ придумывай прямые URL! Только Google-поиск.

Запрос пользователя: {ctx.raw_input}

Создай план из 1-5 шагов. Ответь строго в формате:
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
                            query = ctx.raw_input.replace(" ", "+")
                            input_data["url"] = f"https://www.google.com/search?q={query}"

                    steps.append(PlanStep(
                        step_id=step_num,
                        action=action,
                        tool=tool if tool in self.available_tools else None,
                        input_data=input_data,
                        description=action
                    ))
            elif line.startswith("SUCCESS:"):
                success_criteria.append(line[8:].strip())

        return Plan(goal=goal, steps=steps, success_criteria=success_criteria)

    def _rule_based_plan(self, ctx: TaskContext) -> Plan:
        if ctx.intent == "OPEN_APPLICATION":
            return Plan(
                goal=f"Open application: {ctx.entities.get('app_name', 'unknown')}",
                steps=[PlanStep(
                    step_id=1,
                    action="open_application",
                    tool="system.open_app",
                    input_data={"app_name": ctx.entities.get("app_name", "")},
                    description="Open requested application"
                )],
                success_criteria=["Application open command executed"]
            )

        if ctx.intent == "WEB_SEARCH":
            query = ctx.raw_input
            return Plan(
                goal=f"Search: {query}",
                steps=[PlanStep(
                    step_id=1,
                    action="open_search",
                    tool="browser.open",
                    input_data={"url": "https://www.google.com/search?q=" + query.replace(" ", "+")},
                    description="Open search page"
                )],
                success_criteria=["Search page opened"]
            )

        if ctx.intent == "TECHNICAL_TASK":
            return Plan(
                goal=ctx.raw_input,
                steps=[
                    PlanStep(1, "inspect_directory", "files.list", {"path": ".", "limit": 30}),
                ],
                success_criteria=["Directory inspected"]
            )

        return Plan(goal=ctx.raw_input, steps=[], success_criteria=[])

    def replan(self, ctx: TaskContext, failed_plan: Plan, error: str) -> Plan:
        new_steps = []

        for step in failed_plan.steps:
            if step.tool == "files.read" and "not found" in error.lower():
                continue
            new_steps.append(step)

        if not new_steps:
            new_steps = [PlanStep(1, "fallback_search", "browser.open", {
                "url": "https://www.google.com/search?q=" + ctx.raw_input.replace(" ", "+")
            })]

        return Plan(
            goal=failed_plan.goal,
            steps=new_steps,
            success_criteria=failed_plan.success_criteria
        )