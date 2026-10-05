from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Dict, Any
import json
import time
from pathlib import Path


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
    """История событий."""
    
    def __init__(self, storage_path: str = "mia_memory/episodes.jsonl"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    def add_episode(self, event_type: str, content: str, importance: int = 1, metadata: Dict[str, Any] = None):
        """Записать событие."""
        episode = Episode(
            timestamp=time.time(),
            event_type=event_type,
            content=content,
            importance=importance,
            metadata=metadata
        )
        
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(episode.to_dict(), ensure_ascii=False) + "\n")
    
    def get_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """Получить последние n событий."""
        if not self.storage_path.exists():
            return []
        
        lines = self.storage_path.read_text(encoding="utf-8").strip().split("\n")
        episodes = []
        
        for line in lines[-n:]:
            try:
                episodes.append(json.loads(line))
            except:
                pass
        
        return episodes
    
    def get_by_type(self, event_type: str, n: int = 5) -> List[Dict[str, Any]]:
        """Получить события определённого типа."""
        all_episodes = self.get_recent(100)
        filtered = [e for e in all_episodes if e.get("event_type") == event_type]
        return filtered[-n:]