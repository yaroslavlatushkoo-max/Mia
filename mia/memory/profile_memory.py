from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
import json
from pathlib import Path

from ..config import PROFILE_FILENAME, default_memory_dir


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
    """Хранение профиля на диске.

    storage_path — полный путь к profile.json (обратная совместимость), либо
    memory_dir — каталог хранилища (предпочтительно; путь строится из
    PROFILE_FILENAME). Явный storage_path всегда имеет приоритет.
    """

    def __init__(self, storage_path: Optional[str] = None, memory_dir: Optional[Path] = None):
        if storage_path is not None:
            self.storage_path = Path(storage_path)
        else:
            base = Path(memory_dir) if memory_dir is not None else default_memory_dir()
            self.storage_path = base / PROFILE_FILENAME
        self._load_error: Optional[str] = None
        self.profile = self._load()

    def _load(self) -> UserProfile:
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                return UserProfile.from_dict(data)
            except Exception as e:
                # Не молчим: повреждённый JSON фиксируется в диагностике,
                # но НЕ приводит к перезаписи файла при инициализации
                # (_save вызывается только из mutating-методов).
                self._load_error = f"{type(e).__name__}: {e}"
                print(f"[Memory] Предупреждение: не удалось прочитать профиль "
                      f"{self.storage_path}: {self._load_error}. Работаю с пустым профилем "
                      f"(файл не перезаписан).")
        return UserProfile()

    def _save(self):
        # Ошибки записи НЕ скрываются: OSError поднимается вызывающему коду.
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
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