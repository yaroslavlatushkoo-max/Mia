from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import json
import time
from pathlib import Path

from ..config import EPISODES_FILENAME, default_memory_dir


@dataclass
class Episode:
    """Одно событие/эпизод."""
    
    timestamp: float
    event_type: str  # conversation, task, error, achievement
    content: str
    importance: int = 1  # 1-5
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["metadata"] = self.metadata or {}
        return data


class EpisodicMemory:
    """История событий.

    storage_path — полный путь к episodes.jsonl (обратная совместимость), либо
    memory_dir — каталог хранилища (предпочтительно). Явный storage_path
    всегда имеет приоритет. Формат файла (JSONL) не меняется.
    """

    def __init__(self, storage_path: Optional[str] = None, memory_dir: Optional[Path] = None):
        if storage_path is not None:
            self.storage_path = Path(storage_path)
        else:
            base = Path(memory_dir) if memory_dir is not None else default_memory_dir()
            self.storage_path = base / EPISODES_FILENAME

    def add_episode(self, event_type: str, content: str, importance: int = 1, metadata: Dict[str, Any] = None):
        """Записать событие."""
        episode = Episode(
            timestamp=time.time(),
            event_type=event_type,
            content=content,
            importance=importance,
            metadata=metadata
        )

        # Ошибки записи НЕ скрываются: OSError поднимается вызывающему коду.
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(episode.to_dict(), ensure_ascii=False) + "\n")

    def get_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """Получить последние n событий.

        Чтение идемпотентно: повторные вызовы и инициализация НЕ создают
        дубликатов и НЕ изменяют файл. Повреждённые строки пропускаются,
        но о них сообщается один раз на путь (не молча).
        """
        if not self.storage_path.exists():
            return []

        lines = self.storage_path.read_text(encoding="utf-8").strip().split("\n")
        episodes = []

        bad = 0
        for line in lines[-max(n, 100):]:
            try:
                episodes.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
        if bad and not getattr(EpisodicMemory, "_warned_" + str(self.storage_path), False):
            print(f"[Memory] Предупреждение: в {self.storage_path} пропущено "
                  f"{bad} повреждённых строк (файл не переписывается).")
            setattr(EpisodicMemory, "_warned_" + str(self.storage_path), True)

        return episodes[-n:]
    
    def get_by_type(self, event_type: str, n: int = 5) -> List[Dict[str, Any]]:
        """Получить события определённого типа."""
        all_episodes = self.get_recent(100)
        filtered = [e for e in all_episodes if e.get("event_type") == event_type]
        return filtered[-n:]