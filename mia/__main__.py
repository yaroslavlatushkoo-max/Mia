"""Точка входа ядра Mia: ``python -m mia``.

Текстовый REPL поверх НАСТОЯЩЕГО Orchestrator (mia.core.orchestrator.Orchestrator).

Принципы:
    * ядро синхронное — не переписывается; вызов через asyncio.to_thread(),
      чтобы event loop REPL оставался отзывчивым и единым для всех источников
      ввода (текст сейчас, речь/голос — позже);
    * Session создаётся один на процесс → HITL (подтверждение рискованных
      действий) корректно продолжается между строками ввода;
    * конфигурация модели — из mia.config.MiaSettings (env/.env/defaults),
      модели автоматически НЕ загружаются;
    * Ctrl+D / EOF и Ctrl+C завершают сеанс аккуратно.

Запуск:
    python -m mia            # обычный режим
    python -m mia --debug    # дополнительно печатать type/intent/mode/trace-статус
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from .config import MiaSettings
from .core.orchestrator import Orchestrator
from .core.session import Session
from .tools.registry import ToolRegistry
from .tools.builtin_tools import register_builtin_tools


def _build_orchestrator(settings: MiaSettings) -> Orchestrator:
    """Один общий ModelRouter на обе роли — централизованная конфигурация.

    Память передаётся ЯВНО (MiaSettings.memory_dir / MIA_MEMORY_DIR), чтобы
    экземпляр Mia никогда не зависел от случайного CWD запуска."""
    model_router = settings.build_model_router()
    memory = settings.build_memory()
    sandbox = settings.build_sandbox()
    registry = register_builtin_tools(ToolRegistry(), sandbox=sandbox)
    return Orchestrator(model_router=model_router, memory=memory,
                        tool_registry=registry)


def _print_answer(result: dict, debug: bool) -> None:
    answer = result.get("answer") or "(пустой ответ ядра)"
    print(f"Мия: {answer}")
    if debug:
        ctx = result.get("context") or {}
        trace = result.get("trace") or {}
        pending = result.get("pending")
        extras = []
        if result.get("type"):
            extras.append(f"type={result['type']}")
        if ctx.get("intent"):
            extras.append(f"intent={ctx['intent']}")
        if ctx.get("mode"):
            extras.append(f"mode={ctx['mode']}")
        if ctx.get("complexity"):
            extras.append(f"complexity={ctx['complexity']}")
        if trace.get("status"):
            extras.append(f"trace={trace['status']}")
        if pending:
            extras.append(f"pending={pending.get('state')}")
        if extras:
            print("  [debug] " + " ".join(extras))


async def _read_line(prompt: str) -> Optional[str]:
    """Читает строку в отдельном потоке: input() блокирует, а loop должен
    оставаться свободным. Возвращает None при EOF (Ctrl+D)."""
    try:
        return await asyncio.to_thread(input, prompt)
    except EOFError:
        return None


async def repl(debug: bool = False, memory_dir: Optional[str] = None,
               workspace_dir: Optional[str] = None) -> int:
    settings = MiaSettings.from_env()
    if memory_dir:  # CLI-аргумент имеет высший приоритет
        settings.memory_dir = Path(memory_dir).expanduser()
    if workspace_dir:  # CLI > MIA_WORKSPACE_DIR (env/.env) > default
        settings.workspace_dir = Path(workspace_dir).expanduser().resolve()
    mem_dir = settings.resolved_memory_dir()
    print("Mia — локальный ассистент (новое ядро)")
    print(
        f"  модель chat : {settings.chat_model}\n"
        f"  модель coder: {settings.coder_model}\n"
        f"  ollama      : {settings.base_url} (конфигурация: {settings.source})\n"
        f"  память      : {mem_dir}\n"
        f"  выход       : exit / quit, Ctrl+D или Ctrl+C"
    )

    orchestrator = _build_orchestrator(settings)
    session = Session()

    # Проба доступности Ollama — только informational, ядро работает и без неё
    # (детерминированные пути: память, инструменты, direct-ответы).
    try:
        health = await asyncio.to_thread(
            orchestrator.model_router.chat_provider.health
        )
        if not health.healthy:
            print(f"  ⚠ Ollama недоступна ({health.error}) — ответы локальной модели будут отключены.")
    except Exception as e:  # никогда не роняем REPL из-за пробы
        print(f"  ⚠ Не удалось проверить Ollama: {e}")

    while True:
        try:
            line = await _read_line("\nВы: ")
        except KeyboardInterrupt:
            print()
            break
        if line is None:  # EOF (Ctrl+D)
            print()
            break

        text = line.strip()
        if not text:
            continue
        if text.lower() in {"exit", "quit", ":q", "пока-сеанс"}:
            break

        try:
            result = await asyncio.to_thread(
                orchestrator.handle, text, "text", session
            )
        except KeyboardInterrupt:
            print("\n  (текущая обработка прервана, сеанс продолжен)")
            continue
        except Exception as e:
            # Ошибка ядра не должна убивать REPL: показываем и продолжаем.
            print(f"  [ошибка ядра] {type(e).__name__}: {e}")
            continue

        _print_answer(result, debug)

    print("Сеанс завершён.")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mia",
        description="Mia — локальный AI-ассистент (текстовый REPL нового ядра).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="печатать метаданные маршрутизации (type/intent/mode/trace)",
    )
    parser.add_argument(
        "--memory-dir",
        default=None,
        metavar="PATH",
        help=(
            "каталог памяти Mia (profile.json/episodes.jsonl); по умолчанию — "
            "MIA_MEMORY_DIR из окружения/.env или безопасный default рядом с проектом"
        ),
    )
    parser.add_argument(
        "--workspace-dir",
        default=None,
        metavar="PATH",
        help=(
            "рабочий каталог (песочница) файловых инструментов и shell.safe_run; "
            "по умолчанию — MIA_WORKSPACE_DIR из окружения/.env или mia_workspace/ "
            "рядом с проектом"
        ),
    )
    args = parser.parse_args(argv)

    try:
        return asyncio.run(repl(debug=args.debug, memory_dir=args.memory_dir,
                                workspace_dir=args.workspace_dir))
    except KeyboardInterrupt:
        # Ctrl+C вне цикла чтения
        print("\nСеанс завершён.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
