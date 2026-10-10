"""Демо-прогон ядра (знакомство с памятью).

Изоляция от пользовательских данных: процесс работает во временном каталоге и
явно задаёт MIA_MEMORY_DIR (наследники Orchestrator/MemoryRetriever берут его
через mia.config), поэтому реальные mia_memory/profile.json и episodes.jsonl
не изменяются.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="mia_test_core_")
os.environ["MIA_MEMORY_DIR"] = os.path.join(_TMP, "memory")

from mia.core.orchestrator import Orchestrator

orch = Orchestrator()

print("=== Знакомство ===")
result = orch.handle("Меня зовут Сергей, я работаю с Unity")
print("Тип:", result["type"])
print("Intent:", result["context"]["intent"])
print("Ответ:", result["answer"])

print("\n=== Проверка памяти ===")
result = orch.handle("Что ты помнишь обо мне?")
print("Ответ:", result["answer"])

print("\n=== Ещё факт ===")
result = orch.handle("Я люблю программировать на Python")
print("Ответ:", result["answer"])

print("\n=== Проверка памяти снова ===")
result = orch.handle("Что ты знаешь обо мне?")
print("Ответ:", result["answer"])

print("\n(хранилище этого прогона: %s — временное, пользовательские данные не тронуты)"
      % os.environ["MIA_MEMORY_DIR"])

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
