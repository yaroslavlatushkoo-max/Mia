"""Централизованная конфигурация ядра Mia (без новых зависимостей).

Порядок приоритетов (первый непустой выигрывает):
    1. явные аргументы MiaSettings(...) / CLI (--memory-dir);
    2. переменные окружения MIA_OLLAMA_URL / MIA_CHAT_MODEL / MIA_CODER_MODEL
       / MIA_MEMORY_DIR;
    3. локальный файл .env в корне проекта (MIA_* ключи, без python-dotenv);
    4. безопасные значения по умолчанию:
       http://localhost:11434, qwen2.5:7b (chat), qwen2.5-coder:7b (coder),
       каталог памяти — рядом с пакетом mia/ (см. resolve_memory_dir).

Модуль НИКОГДА не загружает и не скачивает модели — он только описывает,
как к ним обращаться. Конкретные transport/lifecycle остаются исключительной
компетенцией OllamaProvider (mia/ai/ollama_provider.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

# Значения по умолчанию совпадают с фактическими константами ядра:
# OllamaConfig.base_url = "http://localhost:11434" (mia/ai/ollama_provider.py),
# ModelRouter defaults chat="qwen2.5:7b", coder="qwen2.5-coder:7b".
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_CHAT_MODEL = "qwen2.5:7b"
DEFAULT_CODER_MODEL = "qwen2.5-coder:7b"
DEFAULT_TIMEOUT = 120
DEFAULT_HEALTH_TIMEOUT = 1.0

ENV_PREFIX = "MIA_"

# --- Каталог инструментов (workspace/pesochница) ------------------------
# Единый настроенный рабочий каталог для файловых инструментов и shell.safe_run.
WORKSPACE_DIR_ENV = "MIA_WORKSPACE_DIR"


def default_workspace_dir() -> Path:
    """Безопасный workspace по умолчанию: <корень проекта>/mia_workspace."""
    project_root = Path(__file__).resolve().parent.parent
    if (project_root / "mia").is_dir():
        return project_root / "mia_workspace"
    return Path.cwd() / "mia_workspace"


def resolve_workspace_dir(explicit: Optional[str] = None,
                          dotenv_values: Optional[Dict[str, str]] = None) -> Path:
    """Приоритеты: явный аргумент > MIA_WORKSPACE_DIR (env) > .env > default."""
    file_values = dotenv_values if dotenv_values is not None else load_dotenv_values()
    candidate = (
        explicit
        or os.environ.get(WORKSPACE_DIR_ENV)
        or file_values.get(WORKSPACE_DIR_ENV)
    )
    if candidate and candidate.strip():
        return Path(candidate.strip()).expanduser().resolve()
    return default_workspace_dir()

# --- Каталог памяти -----------------------------------------------------
# Безопасное значение по умолчанию: НЕ зависит от текущего каталога запуска
# (старый относительный путь "mia_memory/" создавал хранилище там, откуда
# запустили процесс, — тесты и временные экземпляры незаметно писали в
# пользовательские данные). По умолчанию это mia_memory/ рядом с корнем
# проекта (на уровень выше пакета mia/), т.е. фактическое пользовательское
# хранилище существующей установки; при переносе/установке пакета используется
# <cwd>/mia_memory. Форматы profile.json / episodes.jsonl не меняются.
MEMORY_DIR_ENV = "MIA_MEMORY_DIR"
PROFILE_FILENAME = "profile.json"
EPISODES_FILENAME = "episodes.jsonl"


def default_memory_dir() -> Path:
    """Каталог памяти по умолчанию (стабильный, независимый от CWD)."""
    project_root = Path(__file__).resolve().parent.parent
    if (project_root / "mia").is_dir():
        return project_root / "mia_memory"
    return Path.cwd() / "mia_memory"


def resolve_memory_dir(explicit: Optional[str] = None) -> Path:
    """Каталог памяти с приоритетами: явный аргумент > MIA_MEMORY_DIR (env)
    > .env (MIA_MEMORY_DIR) > безопасный default. Пустые значения пропускаются."""
    candidate = (
        explicit
        or os.environ.get(MEMORY_DIR_ENV)
        or load_dotenv_values().get(MEMORY_DIR_ENV)
    )
    if candidate and candidate.strip():
        return Path(candidate.strip()).expanduser()
    return default_memory_dir()


def _find_dotenv(start: Optional[Path] = None) -> Optional[Path]:
    """Ищет .env от текущей директории вверх (до 6 уровней)."""
    cur = (start or Path.cwd()).resolve()
    for _ in range(7):
        candidate = cur / ".env"
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def load_dotenv_values(path: Optional[Path] = None) -> Dict[str, str]:
    """Минимальный парсер KEY=VALUE для MIA_* ключей. Без сторонних библиотек.

    Поддерживает комментарии (#), пустые строки, кавычки значений.
    НЕ устанавливает переменные окружения — только возвращает словарь.
    """
    values: Dict[str, str] = {}
    env_path = path or _find_dotenv()
    if env_path is None:
        return values
    try:
        text = env_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        if not key.startswith(ENV_PREFIX.rstrip("_")) and key != "OLLAMA_HOST":
            # из .env берём только MIA_* (и общий OLLAMA_HOST как base_url)
            if key != "OLLAMA_HOST":
                continue
        raw = raw.strip().strip('"').strip("'")
        if raw:
            values[key] = raw
    return values


@dataclass
class MiaSettings:
    """Единая точка настройки подключения к локальной модели."""

    base_url: str = DEFAULT_BASE_URL
    chat_model: str = DEFAULT_CHAT_MODEL
    coder_model: str = DEFAULT_CODER_MODEL
    timeout: int = DEFAULT_TIMEOUT
    health_timeout: float = DEFAULT_HEALTH_TIMEOUT
    memory_dir: Optional[Path] = None  # None -> resolve_memory_dir() при использовании
    workspace_dir: Optional[Path] = None  # None -> resolve_workspace_dir() при использовании
    source: str = field(default="defaults")  # diagnostics: где взяты значения

    @classmethod
    def from_env(cls, dotenv_path: Optional[Path] = None) -> "MiaSettings":
        """Собирает настройки: os.environ > .env(MIA_*) > значения по умолчанию."""
        file_values = load_dotenv_values(dotenv_path)

        def pick(env_key: str, default: str) -> str:
            return (
                os.environ.get(env_key)
                or file_values.get(env_key)
                or default
            )

        base = (
            os.environ.get("MIA_OLLAMA_URL")
            or file_values.get("MIA_OLLAMA_URL")
            or os.environ.get("OLLAMA_HOST")
            or file_values.get("OLLAMA_HOST")
            or DEFAULT_BASE_URL
        )
        mem_raw = (
            os.environ.get(MEMORY_DIR_ENV)
            or file_values.get(MEMORY_DIR_ENV)
            or ""
        ).strip()
        ws_raw = (
            os.environ.get(WORKSPACE_DIR_ENV)
            or file_values.get(WORKSPACE_DIR_ENV)
            or ""
        ).strip()
        settings = cls(
            base_url=base.rstrip("/"),
            chat_model=pick("MIA_CHAT_MODEL", DEFAULT_CHAT_MODEL),
            coder_model=pick("MIA_CODER_MODEL", DEFAULT_CODER_MODEL),
            timeout=int(pick("MIA_MODEL_TIMEOUT", str(DEFAULT_TIMEOUT))),
            health_timeout=float(
                pick("MIA_HEALTH_TIMEOUT", str(DEFAULT_HEALTH_TIMEOUT))
            ),
            memory_dir=Path(mem_raw).expanduser() if mem_raw else None,
            workspace_dir=Path(ws_raw).expanduser().resolve() if ws_raw else None,
            source=(
                "environ"
                if any(k.startswith(ENV_PREFIX) or k == "OLLAMA_HOST" for k in os.environ)
                else ("dotenv" if file_values else "defaults")
            ),
        )
        return settings

    def model_names(self) -> Dict[str, str]:
        """Роль → модель, совместимо с ModelRouter(models=...)."""
        return {"chat": self.chat_model, "coder": self.coder_model}

    def resolved_memory_dir(self) -> Path:
        """Каталог памяти для этого экземпляра настроек.

        Явно заданный memory_dir > MIA_MEMORY_DIR (env/.env) > безопасный
        default. Возвращается абсолютный путь — запись вне него невозможна.
        """
        if self.memory_dir is not None:
            return Path(self.memory_dir).expanduser()
        return resolve_memory_dir()

    def build_memory(self):
        """Строит MemoryRetriever, явно привязанный к настроенному каталогу."""
        from .memory.memory_retriever import MemoryRetriever

        return MemoryRetriever(memory_dir=self.resolved_memory_dir())

    def resolved_workspace_dir(self) -> Path:
        """Рабочий каталог инструментов для этого экземпляра настроек.

        Явно заданный workspace_dir > MIA_WORKSPACE_DIR (env/.env) > default.
        Каталог создаётся при первом обращении — пустая песочница безопасна.
        """
        wd = self.workspace_dir if self.workspace_dir is not None \
            else resolve_workspace_dir()
        wd = Path(wd).expanduser().resolve()
        try:
            wd.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # честная ошибка проявится при первой операции с путём
        return wd

    def build_sandbox(self):
        """Единый PathSandbox для всех файловых/shell-инструментов."""
        from .tools.sandbox import PathSandbox

        return PathSandbox(
            workspace_root=self.resolved_workspace_dir(),
            memory_dir=self.resolved_memory_dir(),
        )

    def build_model_router(self):
        """Строит ModelRouter на существующих классах ядра (ничего не переписывая).

        Лень импортирует OllamaProvider; модели НЕ загружаются и НЕ скачиваются —
        это только описание endpoints.
        """
        from .ai.model_router import ModelRouter
        from .ai.ollama_provider import OllamaConfig, OllamaProvider

        common = dict(
            base_url=self.base_url,
            timeout=self.timeout,
            health_timeout=self.health_timeout,
        )
        chat_provider = OllamaProvider(OllamaConfig(model=self.chat_model, **common))
        coder_provider = OllamaProvider(OllamaConfig(model=self.coder_model, **common))
        return ModelRouter(chat_provider=chat_provider, coder_provider=coder_provider)
