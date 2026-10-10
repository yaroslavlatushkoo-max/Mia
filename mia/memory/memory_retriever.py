from __future__ import annotations

from typing import List, Dict, Any, Optional
from pathlib import Path
import re

from ..config import default_memory_dir
from .working_memory import WorkingMemory
from .profile_memory import ProfileMemory
from .episodic_memory import EpisodicMemory


class MemoryRetriever:
    """Единая точка доступа к памяти.

    memory_dir — явный каталог хранилища (из MiaSettings/конфигурации).
    Если не задан, используется безопасный default из mia.config
    (независимый от CWD запускателя). Обратная совместимость: старый вызов
    MemoryRetriever() без аргументов сохраняет поведение.
    """

    def __init__(self, memory_dir: Optional[Path] = None):
        self.memory_dir = Path(memory_dir) if memory_dir is not None else default_memory_dir()
        self.working = WorkingMemory()
        self.profile = ProfileMemory(memory_dir=self.memory_dir)
        self.episodic = EpisodicMemory(memory_dir=self.memory_dir)

    def set_storage(self, memory_dir: Path | str) -> None:
        """Явно перенаправить хранилище (конфигурация/тесты).

        Подхватывает уже загруженные profile/episodic-объекты — иначе
        внешний код (например, Orchestrator), держащий ссылку на память,
        продолжил бы писать в старое (пользовательское) хранилище.
        Формат файлов не меняется; запись возможна только внутри нового
        каталога.
        """
        self.memory_dir = Path(memory_dir)
        for store in (self.profile, self.episodic):
            store.storage_path = self.memory_dir / store.storage_path.name
            store._load() if hasattr(store, "_load") else None

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
        # Многосоставные имена сохраняются ЦЕЛИКОМ — усечение до первого
        # слова теряло фамилию/отчество. Части имени: слово с заглавной
        # буквы, опционально составное через дефис ('Пушкин-Тестовский').
        part = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)*"
        patterns = [
            rf"меня зовут\s+({part}(?:\s+{part})*)",
            rf"моё имя\s+({part}(?:\s+{part})*)",
            rf"мое имя\s+({part}(?:\s+{part})*)",
            rf"я\s+({part}(?:\s+{part})*)\s*$",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = " ".join(match.group(1).split())
                return self._normalize_name(name)

        return None

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Каждое слово с заглавной буквы, составные части через дефис
        ('иванов-петров' -> 'Иванов-Петров'). Не capitalize(): он бы
        превращал 'Тестовый Пользователь' в 'Тестовый пользователь'."""
        parts = []
        for word in name.split():
            hyphenated = "-".join(
                p[:1].upper() + p[1:].lower() if p else ""
                for p in word.split("-")
            )
            parts.append(hyphenated)
        return " ".join(parts)