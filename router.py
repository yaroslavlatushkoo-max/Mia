# -*- coding: utf-8 -*-
"""Deterministic first-pass Router for Mia.

The Router does NOT replace the LLM. It decides how much machinery a request needs.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import re

@dataclass
class Route:
    mode: str
    intent: str
    complexity: int
    tool: str | None = None
    use_memory: bool = False
    reasoning_budget: int = 64
    max_steps: int = 1
    reasons: list[str] = field(default_factory=list)

TOOL_PATTERNS = {
    "browser": (r"\bбраузер\b", r"\bedge\b", r"\bchrome\b"),
    "files": (r"\bфайл\b", r"\bпапк", r"\bпереимен", r"\bудал"),
    "system": (r"\bзапусти\b", r"\bоткрой\b", r"\bвыключ", r"\bтерминал\b"),
    "web": (r"\bнайди\b", r"\bпоищи\b", r"\bинтернет\b", r"\bсайт\b"),
    "weather": (r"\bпогод",),
}

def _find_tool(text: str) -> str | None:
    s = text.lower()
    for name, patterns in TOOL_PATTERNS.items():
        if any(re.search(p, s) for p in patterns):
            return name
    return None

def route_request(text: str) -> Route:
    s = text.lower().strip()
    tool = _find_tool(s)
    memory = any(x in s for x in ("помнишь", "памят", "вспомни", "как раньше", "мы обсуждали"))
    technical = any(x in s for x in ("код", "python", "c#", "unity", "ошиб", "скрипт", "программ"))
    multi_step = any(x in s for x in ("сделай всё", "разберись", "настрой", "исправь", "создай", "проверь"))

    if multi_step and (tool or technical):
        return Route("AGENT", "TASK_EXECUTION", 4, tool, memory, 384, 8, ["multi_step"])

    if tool:
        return Route("AGENT", "TOOL_CALL", 3, tool, memory, 192, 4, ["tool_detected"])

    if technical:
        return Route("TECHNICAL", "TECHNICAL_HELP", 2, None, memory, 192, 1, ["technical"])

    if memory:
        return Route("MIXED", "MEMORY_QUERY", 2, None, True, 128, 1, ["memory"])

    if any(x in s for x in ("привет", "пока", "спасибо", "как дела", "поговор")):
        return Route("COMPANION", "CONVERSATION", 0, None, False, 64, 1, ["simple_conversation"])

    return Route("MIXED", "CONVERSATION", 1, None, False, 96, 1, ["default"])

if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) or "Привет!"
    print(route_request(text))
