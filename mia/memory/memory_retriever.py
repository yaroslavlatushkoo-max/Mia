from __future__ import annotations

from typing import List, Dict, Any, Optional
import re

from .working_memory import WorkingMemory
from .profile_memory import ProfileMemory
from .episodic_memory import EpisodicMemory


class MemoryRetriever:
    """Единая точка доступа к памяти."""

    def __init__(self):
        self.working = WorkingMemory()
        self.profile = ProfileMemory()
        self.episodic = EpisodicMemory()

    def get_context_for_query(self, query: str, max_items: int = 5) -> Dict[str, Any]:
        context = {
            "profile_summary": self.profile.get_summary(),
            "recent_episodes": self.episodic.get_recent(max_items),
            "working_context": self.working.current_context
        }
        return context

    def answer_memory_query(self, query: str) -> str:
        q = query.lower()

        if "что ты помнишь" in q or "что ты знаешь" in q:
            return self.profile.get_summary()

        if "недавно" in q or "сегодня" in q:
            recent = self.episodic.get_recent(5)
            if not recent:
                return "Сегодня у нас ещё не было важных событий."

            parts = []
            for ep in recent:
                parts.append(f"- {ep.get('content', '')}")

            return "Вот что произошло недавно:\n" + "\n".join(parts)

        return self.profile.get_summary()

    def should_remember(self, user_input: str, ai_response: str) -> bool:
        important_keywords = [
            "мой проект", "я работаю", "я учусь", "я люблю",
            "мне нравится", "я хочу", "моё имя", "меня зовут",
            "я делаю игру", "unity", "python", "программирование"
        ]

        text = (user_input + " " + ai_response).lower()

        for kw in important_keywords:
            if kw in text:
                return True

        return False

    def extract_and_remember(self, user_input: str, ai_response: str):
        if not self.should_remember(user_input, ai_response):
            return

        text = user_input.lower()

        name = self._extract_name(user_input)
        if name:
            self.profile.update_fact("name", name)
            print(f"[Memory] Запомнила имя: {name}")

        if "unity" in text:
            self.profile.add_interest("Unity")
            self.profile.add_project("Unity-разработка")

        if "python" in text:
            self.profile.add_interest("Python")

        if "программир" in text or "код" in text:
            self.profile.add_interest("Программирование")

        if "игр" in text:
            self.profile.add_interest("Разработка игр")

        self.episodic.add_episode(
            event_type="conversation",
            content=user_input[:200],
            importance=2
        )

    def _extract_name(self, text: str) -> Optional[str]:
        patterns = [
            r"меня зовут\s+([А-ЯЁ][а-яё]+)",
            r"моё имя\s+([А-ЯЁ][а-яё]+)",
            r"мое имя\s+([А-ЯЁ][а-яё]+)",
            r"я\s+([А-ЯЁ][а-яё]+)\s*$",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).capitalize()

        return None