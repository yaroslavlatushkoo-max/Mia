from __future__ import annotations

import re
from typing import Dict, Any

from .task_context import TaskContext, TaskMode, TaskDomain


class Router:
    def __init__(self):
        self.greeting_patterns = [
            r"\bпривет\b",
            r"\bздравствуй\b",
            r"\bдобрый день\b",
            r"\bдобрый вечер\b",
            r"\bдоброе утро\b",
            r"\bhi\b",
            r"\bhello\b",
        ]

        self.farewell_patterns = [
            r"\bпока\b",
            r"\bдо свидания\b",
            r"\bспокойной ночи\b",
            r"\bbye\b",
        ]

        self.memory_patterns = [
            r"что ты помнишь",
            r"что ты знаешь обо мне",
            r"запомни",
            r"помнишь ли ты",
            r"мои предпочтения",
        ]

        self.user_fact_patterns = [
            r"меня зовут",
            r"моё имя",
            r"мое имя",
            r"я работаю",
            r"я учусь",
            r"я люблю",
            r"мне нравится",
            r"я хочу",
            r"я делаю",
            r"мой проект",
        ]

        self.open_app_patterns = [
            r"открой\s+(.+)",
            r"запусти\s+(.+)",
            r"открыть\s+(.+)",
        ]

        self.web_search_patterns = [
            r"найди в интернете",
            r"поищи в интернете",
            r"найди документацию",
            r"погугли",
            r"найди информацию",
        ]

        self.technical_patterns = [
            r"ошибк",
            r"баг",
            r"код",
            r"проект",
            r"unity",
            r"python",
            r"компиляц",
            r"исправь",
            r"проверь код",
            r"репозиторий",
        ]

    def route(self, text: str, source: str = "text") -> TaskContext:
        normalized = text.strip().lower()
        ctx = TaskContext(raw_input=text, source=source)

        if self._matches_any(normalized, self.greeting_patterns):
            ctx.intent = "GREETING"
            ctx.mode = TaskMode.COMPANION
            ctx.domain = TaskDomain.CHARACTER
            ctx.complexity = "C0"
            ctx.confidence = 0.95
            return ctx

        if self._matches_any(normalized, self.farewell_patterns):
            ctx.intent = "FAREWELL"
            ctx.mode = TaskMode.COMPANION
            ctx.domain = TaskDomain.CHARACTER
            ctx.complexity = "C0"
            ctx.confidence = 0.95
            return ctx

        if self._matches_any(normalized, self.memory_patterns):
            ctx.intent = "MEMORY_QUERY"
            ctx.mode = TaskMode.ASSISTANT
            ctx.domain = TaskDomain.MEMORY
            ctx.complexity = "C1"
            ctx.confidence = 0.9
            return ctx

        if self._matches_any(normalized, self.user_fact_patterns):
            ctx.intent = "USER_FACT"
            ctx.mode = TaskMode.ASSISTANT
            ctx.domain = TaskDomain.MEMORY
            ctx.complexity = "C1"
            ctx.confidence = 0.9
            return ctx

        app_name = self._extract_open_app_name(normalized)
        if app_name:
            ctx.intent = "OPEN_APPLICATION"
            ctx.mode = TaskMode.AGENT
            ctx.domain = TaskDomain.SYSTEM
            ctx.complexity = "C3"
            ctx.entities["app_name"] = app_name
            ctx.confidence = 0.88
            return ctx

        if self._matches_any(normalized, self.web_search_patterns):
            ctx.intent = "WEB_SEARCH"
            ctx.mode = TaskMode.AGENT
            ctx.domain = TaskDomain.WEB
            ctx.complexity = "C3"
            ctx.confidence = 0.82
            return ctx

        if self._matches_any(normalized, self.technical_patterns):
            ctx.intent = "TECHNICAL_TASK"
            ctx.mode = TaskMode.AGENT
            ctx.domain = TaskDomain.TECHNICAL
            ctx.complexity = "C4"
            ctx.confidence = 0.75
            return ctx

        if len(normalized) < 25:
            ctx.intent = "CONVERSATION"
            ctx.mode = TaskMode.COMPANION
            ctx.domain = TaskDomain.GENERAL
            ctx.complexity = "C0"
            ctx.confidence = 0.7
            return ctx

        ctx.intent = "GENERAL_QUERY"
        ctx.mode = TaskMode.ASSISTANT
        ctx.domain = TaskDomain.GENERAL
        ctx.complexity = "C1"
        ctx.confidence = 0.65
        return ctx

    def _matches_any(self, text: str, patterns) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)

    def _extract_open_app_name(self, text: str):
        for pattern in self.open_app_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None