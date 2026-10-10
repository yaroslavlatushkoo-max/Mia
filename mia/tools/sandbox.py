from __future__ import annotations

"""Path sandbox — единая граница файловой безопасности Mia (Task: safe tools).

Все файловые инструменты работают только внутри настроенного рабочего
каталога (workspace_root). Выход наружу запрещён на всех известных векторах:

  * ``..``-traversal        — нормализация пути ДО проверки containment;
  * абсолютные пути         — приводятся к относительным от root, поэтому
                              "/etc/passwd" читается как "<root>/etc/passwd";
  * символьные ссылки       — проверяются и разрешённый путь (resolve), и
                              сам объект (readlink): ссылка наружу или на
                              несуществующую цель блокируется;
  * обход через rename/создание ссылки в песочнице — проверка выполняется
                              непосредственно перед каждой операцией, а не
                              один раз при валидации плана.

Исключение для чтения: файлы самого хранилища памяти (memory_dir) доступны
только для чтения (files.read / files.list) — это легитимный запрос
«что ты помнишь обо мне», но запись/удаление туда запрещены.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _strip_dotparts(rel: Path) -> tuple:
    """Нормализация ``..`` ДО containment-проверки.

    После os.path.normpath '..' может остаться только спереди — такие
    компоненты отбрасываются (clamp): "../secret" -> "secret", остаётся
    внутри песочницы, выход наружу невозможен.
    """
    norm = os.path.normpath(str(rel))
    parts = [x for x in norm.split(os.sep) if x not in (".", "")]
    while parts and parts[0] == "..":
        parts.pop(0)
    return tuple(parts)


@dataclass
class SandboxDecision:
    allowed: bool
    path: Optional[Path] = None      # финальный операционный путь (resolved)
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


class PathSandbox:
    READ = "read"
    WRITE = "write"
    DELETE = "delete"

    #: подпапки memory_dir, которые можно читать (кроме самого корня)
    _MEMORY_READABLE_SUBDIRS = ("logs",)

    def __init__(self, workspace_root: Path | str,
                 memory_dir: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.memory_root = (
            Path(memory_dir).expanduser().resolve() if memory_dir else None
        )

    # ------------------------------------------------------------------
    def _inside(self, candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False

    def _memory_rel(self, resolved: Path):
        """Относительный путь внутри memory-хранилища или None.

        Чтение файлов хранилища памяти разрешено (profile.json,
        episodes.jsonl и др.); запись туда — никогда. Служебные подкаталоги
        (logs/, __pycache__/) закрыты даже на чтение.
        """
        if self.memory_root is None:
            return None
        if not self._inside(resolved, self.memory_root):
            return None
        rel = resolved.relative_to(self.memory_root)
        first = rel.parts[0].lower() if rel.parts else ""
        if first in ("logs", "__pycache__"):
            return None
        return rel

    def _memory_parent_ok(self, candidate: Path) -> bool:
        """Родитель ещё не существующего пути может лежать в памяти —
        проверяем РЕАЛЬНЫЙ ближайший существующий предок (symlink-safe)."""
        if self.memory_root is None:
            return False
        cur = candidate
        while cur != cur.parent and not cur.exists():
            cur = cur.parent
        real = Path(os.path.realpath(str(cur)))
        rel = self._memory_rel(real)
        return rel is not None

    # ------------------------------------------------------------------
    def resolve_for(self, user_path: str, operation: str = READ) -> SandboxDecision:
        """Проверить путь НЕПОСРЕДСТВЕННО перед операцией.

        Возвращает либо разрешённый операционный Path, либо причину отказа.
        Никаких исключений наружу — ошибки безопасности это данные.
        """
        if user_path is None or not str(user_path).strip():
            return SandboxDecision(False, None, "Empty path.")

        raw = str(user_path).strip()

        # Обработка абсолютных путей (POSIX и Windows):
        #   * если абсолютный путь РЕАЛЬНО лежит внутри настроенного
        #     workspace (или memory-хранилища) — он принимается как есть;
        #   * иначе корень лишается ("C:/Windows/x" -> "<root>/C:/..."),
        #     такого файла нет -> честная ошибка «does not exist», без утечки.
        # Прежняя безусловная подрезка корня ломала легитимные вызовы с
        # полным путём внутри workspace (дефект B13).
        p = Path(raw)
        drive, tail = os.path.splitdrive(raw)
        is_abs = p.is_absolute() or bool(drive) or raw.startswith(("/", "\\"))
        if is_abs:
            abs_candidate = Path(os.path.normpath(raw))
            try:
                abs_resolved = abs_candidate.resolve()
            except OSError:
                abs_resolved = None
            if (
                abs_resolved is not None
                and (
                    self._inside(abs_resolved, self.workspace_root)
                    or (
                        operation == self.READ
                        and self.memory_root is not None
                        and self._memory_rel(abs_resolved) is not None
                    )
                )
            ):
                target_rel_parts = None  # сигнал: работать с abs_candidate
            else:
                target_rel_parts = list(_strip_dotparts(Path(tail.lstrip("/\\").replace("\\", "/"))))
        else:
            target_rel_parts = list(_strip_dotparts(Path(raw.replace("\\", "/"))))

        if target_rel_parts is None:
            candidate = abs_candidate
        elif not target_rel_parts:
            candidate = self.workspace_root
        else:
            candidate = self.workspace_root / Path(*target_rel_parts)
        resolved = candidate.resolve()

        # Финальная containment-проверка уже РЕЗОЛВНУТОГО пути.
        inside_ws = self._inside(resolved, self.workspace_root)
        memory_read = (
            operation == self.READ and self._memory_rel(resolved) is not None
        )
        if not inside_ws and not memory_read:
            return SandboxDecision(
                False, None,
                f"Path escapes the sandbox: '{raw}' resolves outside the "
                f"configured workspace ({self.workspace_root}).",
            )

        # Запись/удаление в хранилище памяти запрещены всегда.
        if operation in (self.WRITE, self.DELETE) and self.memory_root is not None:
            if self._inside(resolved, self.memory_root):
                return SandboxDecision(
                    False, None,
                    "The memory storage directory is read-only for file tools.",
                )

        # Символьные ссылки: проверяем и разрешение, и сам объект.
        lexists = os.path.lexists(str(candidate))
        if lexists:
            if candidate.is_symlink():
                if not resolved.exists():
                    return SandboxDecision(
                        False, None,
                        f"Symlink with missing/broken target is refused: '{raw}'.",
                    )
                link_ok = self._inside(resolved, self.workspace_root) or memory_read
                if not link_ok:
                    return SandboxDecision(
                        False, None,
                        f"Symlink points outside the sandbox: '{raw}'.",
                    )
            # промежуточные компоненты тоже не должны вести наружу —
            # это уже учтено containment-проверкой resolved-пути.
        else:
            # Объекта ещё нет (запись/чтение несуществующего). Проверяем
            # реальный (symlink-safe) ближайший существующий предок: он обязан
            # лежать внутри песочницы; для чтения допустим предок из памяти.
            real_parent = Path(os.path.realpath(str(candidate.parent)))
            parent_in_ws = self._inside(real_parent, self.workspace_root)
            read_into_memory_tree = (
                operation == self.READ and self._memory_parent_ok(candidate)
            )
            if not parent_in_ws and not read_into_memory_tree:
                return SandboxDecision(
                    False, None,
                    f"Parent directory of '{raw}' escapes the sandbox.",
                )

        return SandboxDecision(True, resolved, "")
