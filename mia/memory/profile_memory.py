from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List
import json
from pathlib import Path


@dataclass
class UserProfile:
    """Долгосрочный профиль пользователя."""
    
    user_id: str = "local_user"
    name: str = ""
    preferences: Dict[str, Any] = field(default_factory=dict)
    facts: Dict[str, Any] = field(default_factory=dict)
    interests: List[str] = field(default_factory=list)
    projects: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        return cls(**data)


class ProfileMemory:
    """Хранение профиля на диске."""
    
    def __init__(self, storage_path: str = "mia_memory/profile.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile = self._load()
    
    def _load(self) -> UserProfile:
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                return UserProfile.from_dict(data)
            except:
                pass
        return UserProfile()
    
    def _save(self):
        self.storage_path.write_text(
            json.dumps(self.profile.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def get_profile(self) -> UserProfile:
        return self.profile
    
    def update_fact(self, key: str, value: Any):
        """Обновить факт о пользователе."""
        self.profile.facts[key] = value
        self._save()
    
    def add_preference(self, key: str, value: Any):
        """Добавить предпочтение."""
        self.profile.preferences[key] = value
        self._save()
    
    def add_interest(self, interest: str):
        if interest not in self.profile.interests:
            self.profile.interests.append(interest)
            self._save()
    
    def add_project(self, project: str):
        if project not in self.profile.projects:
            self.profile.projects.append(project)
            self._save()
    
    def get_summary(self) -> str:
        """Получить краткое описание для ответа."""
        parts = []
        
        if self.profile.name:
            parts.append(f"имя: {self.profile.name}")
        
        if self.profile.interests:
            parts.append(f"интересы: {', '.join(self.profile.interests)}")
        
        if self.profile.projects:
            parts.append(f"проекты: {', '.join(self.profile.projects)}")
        
        if self.profile.facts:
            facts_str = ", ".join([f"{k}={v}" for k, v in self.profile.facts.items()])
            parts.append(f"факты: {facts_str}")
        
        if not parts:
            return "Я пока мало знаю о тебе, но готова учиться."
        
        return "Я помню: " + "; ".join(parts)