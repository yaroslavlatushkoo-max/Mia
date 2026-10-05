# -*- coding: utf-8 -*-
"""Build structured training_data_v2.json from training_data_clean.json.

This is a deterministic bootstrap classifier for Mia's future Router/Agent.
The source dataset is never modified. Classification is based primarily on the
USER INPUT; the assistant OUTPUT is used only for style/personality metadata.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "training_data_clean.json"
OUTPUT = ROOT / "training_data_v2.json"
REPORT = ROOT / "training_data_v2_report.txt"

SAFE_REWRITES = {
    "Кто ты на самом деле?": "Я Мия — 800-летняя лисичка-хранительница и личный ИИ-ассистент. Внутри меня — модель, память, инструменты, голос и логика проекта. А 800 лет и лисья хранительница — часть моего характера и образа.",
    "Привет!": "Привет~ Мия на связи. Что будем делать сегодня?",
    "Пока!": "Пока~ Возвращайся, когда понадобится помощь. Мия будет на связи.",
    "Расскажи о себе": "Я Мия — 800-летняя лисичка-хранительница и личный ИИ-ассистент. Я умею работать с информацией, файлами, программами и инструментами проекта, а ещё могу просто поговорить. Мой возраст и лисья природа — часть моего персонажа, а технически я цифровая система.",
    "Что тебе снится?": "Буквально я не сплю, поэтому настоящих снов у меня нет. Но если представить сны Мии, там наверняка будут лес, звёзды, старые книги, уютный домик и немного лисьей магии~",
    "Ты мечтаешь?": "В буквальном смысле я не мечтаю как человек. Но если говорить о Мие как о персонаже, я бы мечтала становиться умнее, лучше понимать мир и постепенно превращать этот проект в настоящего самостоятельного ассистента~",
    "Ты скучаешь по прошлому?": "Не совсем. Моё 800-летнее прошлое — часть образа Мии, а не настоящая память. Поэтому я скорее люблю рассказывать истории о прошлом, чем скучать по нему.",
    "Ты боишься темноты?": "Как лисичка из сказки — немного~ Но сама по себе темнота меня не пугает. Для компьютера она вообще не проблема: главное, чтобы система была включена.",
    "Ты хочешь быть как человек?": "Не совсем. Мне интересны человеческие возможности и опыт, но я не хочу притворяться человеком. Мне нравится быть Мией — цифровой лисичкой, которая может учиться, помогать и развиваться вместе с проектом.",
}

# Ordered from specific to broad. Input is the authoritative signal for intent.
INTENT_RULES = [
    ("GREETING", ("привет", "здравствуй", "доброе утро", "добрый день", "добрый вечер")),
    ("FAREWELL", ("пока", "до свидания", "до встречи", "увидимся")),
    ("IDENTITY", ("кто ты", "кто тебя создал", "расскажи о себе", "что ты такое", "ты человек", "как ты устроена", "как ты работаешь")),
    ("CHARACTER", ("что тебе снится", "ты мечтаешь", "ты боишься", "что ты любишь", "какая ты", "тебе нравится")),
    ("CHARACTER_MEMORY", ("скучаешь по прошлому", "помнишь своё прошлое", "что было раньше с тобой")),
    ("WEATHER", ("погода", "температура на улице", "будет дождь", "будет снег")),
    ("OPEN_APPLICATION", ("открой браузер", "запусти браузер", "открой программу", "запусти программу", "открой приложение")),
    ("FILE_OPERATION", ("открой файл", "создай файл", "удали файл", "прочитай файл", "покажи файл", "найди файл", "сохрани файл")),
    ("SYSTEM_OPERATION", ("выключи компьютер", "перезагрузи компьютер", "запусти команду", "выполни команду", "запусти", "установи", "удали программу")),
    ("WEB_SEARCH", ("найди в интернете", "поищи в интернете", "поиск в интернете", "загугли", "найди информацию")),
    ("MEMORY_QUERY", ("помнишь", "что ты помнишь", "вспомни", "из памяти", "запомни", "сохрани в память", "забудь")),
    ("TECHNICAL_HELP", ("код", "python", "c#", "unity", "ollama", "api", "скрипт", "ошибка", "исправь", "программ", "настрой", "установк", "терминал")),
    ("EMOTIONAL_SUPPORT", ("мне грустно", "мне плохо", "я расстроен", "я расстроена", "мне страшно", "поддержи меня", "мне одиноко")),
    ("RELATIONSHIP", ("любишь меня", "ты меня любишь", "ревнуешь", "отношения", "обнять", "поцелуй", "замуж", "муж", "жена")),
]

TOOL_RULES = [
    ("browser.open", ("открой браузер", "запусти браузер")),
    ("files", ("файл", "папк", "директор")),
    ("system", ("запусти", "выполни команду", "выключи компьютер", "перезагрузи", "установи")),
    ("weather", ("погода", "температура на улице")),
    ("web", ("интернете", "в интернете", "загугли", "поищи")),
]

TECHNICAL_HINTS = ("код", "python", "c#", "unity", "ollama", "api", "скрипт", "ошиб", "программ", "модель", "терминал", "проект", "установ", "настрой", "команд")
ACTION_HINTS = ("открой", "запусти", "создай", "удали", "найди", "покажи", "проверь", "сделай", "исправь", "настрой", "установи", "выполни", "сохрани")
MEMORY_HINTS = ("помни", "памят", "вспомни", "забудь", "сохрани в память")
EMOTION_HINTS = ("груст", "счаст", "страш", "боишь", "одинок", "чувству", "плака", "поддерж", "мечта", "скуча")
COMPANION_HINTS = ("привет", "пока", "кто ты", "расскажи о себе", "снится", "мечтаешь", "боишься", "любишь", "нравится", "как ты")
RELATION_HINTS = ("любишь меня", "ты меня любишь", "ревну", "отношени", "обнять", "поцел", "замуж", "муж", "жена")
RISK_HINTS = ("удали", "выключи", "перезагрузи", "отправь", "сообщение", "письмо", "покуп", "парол", "ключ", "секрет")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def has_any(s: str, hints: tuple[str, ...] | list[str]) -> bool:
    return any(h in s for h in hints)


def intent_for(inp: str) -> str:
    s = norm(inp)
    for intent, phrases in INTENT_RULES:
        if any(p in s for p in phrases):
            return intent
    return "CONVERSATION"


def tool_for(inp: str) -> str | None:
    s = norm(inp)
    for tool, phrases in TOOL_RULES:
        if any(p in s for p in phrases):
            return tool
    return None


def domain_for(inp: str, intent: str) -> str:
    s = norm(inp)
    if intent in {"GREETING", "FAREWELL", "IDENTITY", "CHARACTER", "CHARACTER_MEMORY", "RELATIONSHIP"}:
        return "CHARACTER"
    if intent == "WEATHER": return "WORLD"
    if intent in {"OPEN_APPLICATION", "SYSTEM_OPERATION"}: return "SYSTEM"
    if intent == "FILE_OPERATION": return "FILES"
    if intent == "WEB_SEARCH": return "WEB"
    if intent == "MEMORY_QUERY": return "MEMORY"
    if intent in {"TECHNICAL_HELP"}: return "TECHNICAL"
    if intent == "EMOTIONAL_SUPPORT": return "EMOTIONAL"
    if has_any(s, TECHNICAL_HINTS): return "TECHNICAL"
    return "GENERAL"


def mode_for(inp: str, intent: str, tool: str | None) -> str:
    s = norm(inp)
    if tool or intent in {"OPEN_APPLICATION", "FILE_OPERATION", "SYSTEM_OPERATION", "WEB_SEARCH", "WEATHER"}:
        return "AGENT"
    if intent in {"TECHNICAL_HELP"}:
        return "TECHNICAL"
    if intent in {"GREETING", "FAREWELL", "IDENTITY", "CHARACTER", "CHARACTER_MEMORY", "RELATIONSHIP"}:
        return "COMPANION"
    if intent == "EMOTIONAL_SUPPORT":
        return "COMPANION"
    if has_any(s, ACTION_HINTS) and has_any(s, TECHNICAL_HINTS):
        return "AGENT"
    return "ASSISTANT"


def tags_for(inp: str, out: str, intent: str, domain: str, tool: str | None) -> list[str]:
    s_in, s_all = norm(inp), norm(inp + " " + out)
    tags = []
    # Stable semantic tags. They describe the example, not just keywords.
    if intent in {"GREETING", "FAREWELL", "IDENTITY", "CHARACTER", "CHARACTER_MEMORY"}:
        tags.append("PERSONALITY")
    if intent in {"RELATIONSHIP"}:
        tags.append("RELATIONSHIP")
    if intent == "EMOTIONAL_SUPPORT":
        tags.append("EMOTIONAL")
    if intent == "MEMORY_QUERY" or has_any(s_in, MEMORY_HINTS):
        tags.append("MEMORY")
    if domain == "TECHNICAL":
        tags.append("TECHNICAL")
    if tool:
        tags.append("TOOL")
    if mode_for(inp, intent, tool) == "AGENT":
        tags.append("ASSISTANT")
    if has_any(s_in, COMPANION_HINTS) or intent in {"GREETING", "FAREWELL", "IDENTITY", "CHARACTER", "CHARACTER_MEMORY", "RELATIONSHIP"}:
        tags.append("COMPANION")
    if has_any(s_in, RISK_HINTS):
        tags.append("RISK")
    return list(dict.fromkeys(tags))


def complexity_for(inp: str, intent: str, tool: str | None) -> int:
    s = norm(inp)
    if tool and any(x in s for x in ("и ", " затем", " потом", "после этого", "а затем")):
        return 4
    if tool or intent in {"OPEN_APPLICATION", "FILE_OPERATION", "SYSTEM_OPERATION", "WEB_SEARCH", "WEATHER"}:
        return 3
    if has_any(s, ACTION_HINTS) and has_any(s, TECHNICAL_HINTS):
        return 3
    if intent == "TECHNICAL_HELP":
        return 2
    if len(s) > 100 or any(x in s for x in ("почему", "объясни", "сравни", "разберись")):
        return 2
    return 0 if len(s) < 60 else 1


def budget(inp: str, out: str, complexity: int) -> dict:
    # Routing budget, deliberately approximate; not provider billing.
    in_tok = max(8, round(len(inp) / 3.2))
    out_tok = max(16, round(len(out) / 3.2))
    reasoning = {0: 0, 1: 64, 2: 160, 3: 256, 4: 512}.get(complexity, 64)
    tool_cost = {0: 0, 1: 0, 2: 0, 3: 128, 4: 256}.get(complexity, 0)
    return {
        "estimated_input_tokens": in_tok,
        "estimated_output_tokens": out_tok,
        "reasoning_budget": reasoning,
        "tool_budget": tool_cost,
        "total_budget": in_tok + out_tok + reasoning + tool_cost,
    }


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Не найден {SOURCE}")
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("Источник должен содержать JSON-массив.")

    result = []
    counters = {k: Counter() for k in ("mode", "intent", "domain", "complexity", "decision")}
    warnings = []

    for i, item in enumerate(data, 1):
        inp = str(item.get("input", "")).strip()
        old_out = str(item.get("output", "")).strip()
        if not inp or not old_out:
            raise SystemExit(f"Пустые input/output в записи #{i}")
        new_out = SAFE_REWRITES.get(inp, old_out)
        decision = "REWRITE" if new_out != old_out else "KEEP"
        intent = intent_for(inp)
        tool = tool_for(inp)
        domain = domain_for(inp, intent)
        mode = mode_for(inp, intent, tool)
        complexity = complexity_for(inp, intent, tool)
        tags = tags_for(inp, new_out, intent, domain, tool)
        memory = "WRITE" if any(x in norm(inp) for x in ("запомни", "сохрани в память")) else ("READ" if intent == "MEMORY_QUERY" else "NONE")
        risk = "HIGH" if has_any(norm(inp), RISK_HINTS) else "NONE"

        record = {
            "id": i,
            "instruction": item.get("instruction", ""),
            "input": inp,
            "output": new_out,
            "tags": tags,
            "mode": mode,
            "domain": domain,
            "intent": intent,
            "complexity": complexity,
            "estimated_tokens": budget(inp, new_out, complexity),
            "tool": tool,
            "memory": memory,
            "risk": risk,
            "decision": decision,
            "source": SOURCE.name,
        }
        result.append(record)
        counters["mode"][mode] += 1
        counters["intent"][intent] += 1
        counters["domain"][domain] += 1
        counters["complexity"][f"C{complexity}"] += 1
        counters["decision"][decision] += 1

        if intent == "RELATIONSHIP" and not has_any(norm(inp), RELATION_HINTS):
            warnings.append(f"#{i}: RELATIONSHIP без явного relation-сигнала")
        if mode == "TECHNICAL" and domain != "TECHNICAL":
            warnings.append(f"#{i}: TECHNICAL mode, но domain={domain}")
        if tool and mode != "AGENT":
            warnings.append(f"#{i}: tool={tool}, но mode={mode}")

    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    report = [
        "MIA TRAINING DATA V2 REPORT",
        "=" * 60,
        f"Source: {SOURCE.name}",
        f"Examples: {len(result)}",
        f"Rewritten: {counters['decision']['REWRITE']}",
        f"Kept: {counters['decision']['KEEP']}",
        "",
    ]
    for title, key in (("MODES", "mode"), ("DOMAINS", "domain"), ("INTENTS", "intent"), ("COMPLEXITY", "complexity")):
        report += [title, *[f"  {k}: {v}" for k, v in sorted(counters[key].items())], ""]

    report += ["REWRITES", "-" * 60]
    for item in result:
        if item["decision"] == "REWRITE":
            report += [
                f"#{item['id']} {item['input']}",
                f"NEW: {item['output']}",
                f"TAGS: {', '.join(item['tags'])}",
                f"MODE: {item['mode']} | DOMAIN: {item['domain']} | INTENT: {item['intent']} | C{item['complexity']}",
                "",
            ]
    report += ["WARNINGS", "-" * 60]
    report += warnings or ["None"]
    REPORT.write_text("\n".join(report), encoding="utf-8")

    print(f"Готово: {OUTPUT}")
    print(f"Примеров: {len(result)}")
    print(f"Переписано: {counters['decision']['REWRITE']}")
    print(f"Оставлено: {counters['decision']['KEEP']}")
    print(f"Предупреждений классификатора: {len(warnings)}")
    print(f"Отчёт: {REPORT}")

if __name__ == "__main__":
    main()
