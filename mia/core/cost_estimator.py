from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .task_context import TaskContext


@dataclass
class ExecutionBudget:
    estimated_input_tokens: int
    estimated_output_tokens: int
    reasoning_budget: int
    tool_budget: int
    total_budget: int
    max_steps: int
    estimated_time_sec: int
    # Capability requirements (migration To-do #2). Planner and AgentLoop
    # read these via TaskContext instead of re-deriving them.
    requires_llm: bool = False
    requires_tool: bool = False
    requires_planner: bool = False
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)


class CostEstimator:
    def __init__(self):
        self.table = {
            "C0": ExecutionBudget(
                estimated_input_tokens=128,
                estimated_output_tokens=96,
                reasoning_budget=0,
                tool_budget=0,
                total_budget=224,
                max_steps=1,
                estimated_time_sec=1,
            ),
            "C1": ExecutionBudget(
                estimated_input_tokens=512,
                estimated_output_tokens=256,
                reasoning_budget=128,
                tool_budget=0,
                total_budget=896,
                max_steps=1,
                estimated_time_sec=3,
            ),
            "C2": ExecutionBudget(
                estimated_input_tokens=1024,
                estimated_output_tokens=512,
                reasoning_budget=384,
                tool_budget=256,
                total_budget=2176,
                max_steps=3,
                estimated_time_sec=10,
            ),
            "C3": ExecutionBudget(
                estimated_input_tokens=1536,
                estimated_output_tokens=768,
                reasoning_budget=512,
                tool_budget=768,
                total_budget=3584,
                max_steps=5,
                estimated_time_sec=20,
            ),
            "C4": ExecutionBudget(
                estimated_input_tokens=3072,
                estimated_output_tokens=1024,
                reasoning_budget=768,
                tool_budget=1536,
                total_budget=6400,
                max_steps=8,
                estimated_time_sec=45,
            ),
            "C5": ExecutionBudget(
                estimated_input_tokens=4096,
                estimated_output_tokens=1536,
                reasoning_budget=1024,
                tool_budget=2048,
                total_budget=8704,
                max_steps=12,
                estimated_time_sec=90,
            ),
        }

    def estimate(self, ctx: TaskContext) -> ExecutionBudget:
        base = self.table.get(ctx.complexity, self.table["C1"])
        budget = ExecutionBudget(**base.__dict__)

        # Deterministic capability requirements (To-do #2):
        # - LLM planner is allowed only for C4/C5; C3 and below must use
        #   the deterministic Fast Plan (rule-based) path.
        # - tool/planner requirements follow from mode/complexity.
        if ctx.mode.value == "AGENT" or ctx.complexity in {"C2", "C3", "C4", "C5"}:
            budget.requires_tool = True
            budget.requires_planner = True
        if ctx.complexity in {"C4", "C5"}:
            budget.requires_llm = True
            budget.reasons.append(
                f"{ctx.complexity}: deep plan — LLM planner allowed"
            )
        elif budget.requires_planner:
            budget.reasons.append(
                f"{ctx.complexity}: deterministic fast plan — LLM planner disabled"
            )
        budget.confidence = ctx.confidence

        # Carry the requirements in TaskContext so Planner/AgentLoop read
        # the budget from the context (single flow per CORE_MIGRATION.md).
        ctx.budget_requires_llm = budget.requires_llm
        ctx.budget_requires_tool = budget.requires_tool
        ctx.budget_requires_planner = budget.requires_planner
        ctx.budget_confidence = budget.confidence
        ctx.budget_reasons = list(budget.reasons)

        return budget