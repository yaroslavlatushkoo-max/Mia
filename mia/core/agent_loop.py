from __future__ import annotations

from typing import Any, Dict, Optional

from .task_context import TaskContext
from .execution_trace import ExecutionTrace, ExecutionStatus
from .planner import Planner, Plan
from .verifier import Verifier

from ..tools.registry import ToolRegistry


class AgentLoop:
    def __init__(self, tool_registry: ToolRegistry, planner: Optional[Planner] = None, verifier: Optional[Verifier] = None):
        self.tool_registry = tool_registry
        self.planner = planner or Planner()
        self.verifier = verifier or Verifier()

    def run(self, ctx: TaskContext, trace: ExecutionTrace) -> Dict[str, Any]:
        plan = self.planner.create_plan(ctx)
        trace.status = ExecutionStatus.PLANNING

        if not plan.steps:
            trace.status = ExecutionStatus.FAILED
            trace.errors.append("Planner returned empty plan.")
            return {
                "answer": "Я не смогла составить план для этой задачи.",
                "plan": plan.to_dict(),
                "verification": None,
            }

        trace.status = ExecutionStatus.RUNNING

        for step in plan.steps:
            if trace.current_step >= trace.max_steps:
                trace.errors.append("Max steps exceeded.")
                break

            # Временная защита от placeholder-шагов
            if step.tool == "files.read" and step.input_data.get("path") == "TODO":
                observation = {
                    "success": True,
                    "data": {"note": "Skipped placeholder read step until smarter file selection is implemented."},
                    "error": None,
                }
                trace_step = trace.add_step(action=step.action, tool=step.tool, input_data=step.input_data)
                trace.complete_step(trace_step, observation=observation)
                trace.current_step += 1
                continue

            tool = self.tool_registry.get(step.tool) if step.tool else None
            if not tool:
                trace_step = trace.add_step(action=step.action, tool=step.tool, input_data=step.input_data)
                trace.complete_step(trace_step, error=f"Tool not found: {step.tool}")
                trace.current_step += 1
                continue

            trace_step = trace.add_step(action=step.action, tool=step.tool, input_data=step.input_data)
            result = self.tool_registry.run(step.tool, **step.input_data)
            observation = {
                "success": result.success,
                "data": result.data,
                "error": result.error,
            }
            trace.complete_step(trace_step, observation=observation, error=result.error)
            trace.current_step += 1

        verification = self.verifier.verify_plan_execution(plan, trace)

        if verification["success"]:
            trace.status = ExecutionStatus.COMPLETED
            answer = self._build_success_answer(plan, trace)
        else:
            trace.status = ExecutionStatus.FAILED
            answer = self._build_failure_answer(plan, trace, verification)

        trace.final_answer = answer

        return {
            "answer": answer,
            "plan": plan.to_dict(),
            "verification": verification,
        }

    def _build_success_answer(self, plan: Plan, trace: ExecutionTrace) -> str:
        if len(trace.steps) == 1:
            step = trace.steps[0]
            if step.tool == "system.open_app":
                return f"Я выполнила задачу: открыть {step.input_data.get('app_name', 'приложение')}."
            if step.tool == "browser.open":
                return "Я выполнила задачу: открыла нужную страницу в браузере."
        return "Я выполнила задачу по плану."

    def _build_failure_answer(self, plan: Plan, trace: ExecutionTrace, verification: Dict[str, Any]) -> str:
        if trace.errors:
            return "Я начала выполнять задачу, но возникли ошибки: " + "; ".join(trace.errors)
        return "Я начала выполнять задачу, но не смогла уверенно завершить все шаги."