from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
import time


@dataclass
class WorkingMemory:
    """Краткосрочная память текущей сессии."""
    
    session_id: str = "default"
    messages: List[Dict[str, Any]] = field(default_factory=list)
    current_context: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    
    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """Добавить сообщение в историю."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {}
        })
        # Храним последние 20 сообщений
        if len(self.messages) > 20:
            self.messages = self.messages[-20:]
    
    def get_recent(self, n: int = 5) -> List[Dict[str, Any]]:
        """Получить последние n сообщений."""
        return self.messages[-n:]
    
    def set_context(self, key: str, value: Any):
        """Установить контекст текущей задачи."""
        self.current_context[key] = value
    
    def get_context(self, key: str, default: Any = None) -> Any:
        return self.current_context.get(key, default)
    
    def clear(self):
        """Очистить память сессии."""
        self.messages.clear()
        self.current_context.clear()