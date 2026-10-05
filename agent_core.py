# -*- coding: utf-8 -*-
"""Minimal Agent Core skeleton.

LLM and real tools are injected. This keeps the architecture testable and local-first.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Any
from router import route_request, Route

class LLM(Protocol):
    def generate(self, messages: list[dict[str, str]], **kwargs) -> str: ...

class Tool(Protocol):
    name: str
    def run(self, **kwargs) -> Any: ...

@dataclass
class AgentResult:
    text: str
    route: Route
    steps: int

class AgentCore:
    def __init__(self, llm: LLM, tools: dict[str, Tool] | None = None):
        self.llm = llm
        self.tools = tools or {}

    def run(self, user_text: str) -> AgentResult:
        route = route_request(user_text)

        if route.mode != "AGENT":
            answer = self.llm.generate(
                [{"role": "user", "content": user_text}],
                reasoning_budget=route.reasoning_budget,
                mode=route.mode,
            )
            return AgentResult(answer, route, 1)

        observation = None
        messages = [{"role": "user", "content": user_text}]

        for step in range(route.max_steps):
            if route.tool and route.tool in self.tools and observation is None:
                # First implementation deliberately keeps tool arguments simple.
                # A later ToolRegistry/LLM planner will produce structured arguments.
                try:
                    observation = self.tools[route.tool].run(text=user_text)
                except Exception as exc:
                    observation = {"error": str(exc)}

                messages.append({
                    "role": "tool",
                    "content": str(observation),
                })

            answer = self.llm.generate(
                messages,
                reasoning_budget=route.reasoning_budget,
                mode="AGENT",
                step=step + 1,
            )

            # Verification/planning becomes the next layer.
            return AgentResult(answer, route, step + 1)

        return AgentResult("Не удалось завершить задачу.", route, route.max_steps)
