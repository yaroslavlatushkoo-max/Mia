"""Демо-прогон ядра: маршрутизация и планы для типовых запросов.

Изоляция от пользовательских данных: процесс работает во временном каталоге и
явно задаёт MIA_MEMORY_DIR (через mia.config), поэтому реальные
mia_memory/profile.json и episodes.jsonl не изменяются.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="mia_test_agent_")
os.environ["MIA_MEMORY_DIR"] = os.path.join(_TMP, "memory")

from mia.core.orchestrator import Orchestrator

orch = Orchestrator()

tests = [
    "Привет",
    "Открой notepad",
    "Найди документацию Python по asyncio",
    "Проверь папку с проектом",
    "Создай план изучения Unity для начинающего",
]

for text in tests:
    print(f"\n=== {text} ===")
    result = orch.handle(text)
    print("Type:", result["type"])
    print("Intent:", result["context"]["intent"])
    print("Answer:", result.get("answer"))

    if result.get("plan"):
        print("Plan:", result["plan"]["goal"])
        for step in result["plan"]["steps"]:
            print(f"  {step['step_id']}. {step['action']} -> {step['tool']}")

    if result.get("verification"):
        v = result["verification"]
        print("Verification:", v.get("summary"))
        if v.get("semantic_check"):
            print("Semantic:", v["semantic_check"])

    if result.get("replans"):
        print("Replans:", result["replans"])

print("\n(хранилище этого прогона: %s — временное, пользовательские данные не тронуты)"
      % os.environ["MIA_MEMORY_DIR"])

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
