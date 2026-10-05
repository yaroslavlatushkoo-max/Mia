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