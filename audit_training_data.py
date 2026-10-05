import json
import re
from pathlib import Path
from collections import Counter


INPUT = Path("training_data_clean.json")
OUTPUT = Path("training_data_audit.txt")


def normalize(text):
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def contains_any(text, patterns):
    text = normalize(text)
    return [p for p in patterns if p in text]


ROMANTIC = [
    "люблю",
    "любовь",
    "любить",
    "любим",
    "муж",
    "мужем",
    "мужчина",
    "жена",
    "замуж",
    "свадьб",
    "выйти за",
    "будущий муж",
    "единственн",
    "навсегда",
    "потерять тебя",
    "хочу быть рядом",
    "хочу быть твоей",
    "хочу детей",
    "моя любовь",
    "обнима",
    "поцелу",
    "дорогой",
    "милый",
]

PERSONALITY = [
    "мия",
    "лисич",
    "800",
    "создател",
    "характер",
    "мечта",
    "страх",
    "счаст",
    "груст",
    "добр",
    "шут",
]

ASSISTANT = [
    "команд",
    "браузер",
    "открой",
    "откры",
    "файл",
    "папк",
    "компьютер",
    "программ",
    "запусти",
    "выключ",
    "систем",
    "интернет",
    "поиск",
    "погода",
    "время",
]

EMOTIONAL = [
    "грустно",
    "одиноко",
    "страшно",
    "боишься",
    "бояться",
    "счастлив",
    "счастье",
    "печаль",
    "поддерж",
    "тревог",
]

TECHNICAL = [
    "код",
    "python",
    "программ",
    "unity",
    "игр",
    "компьютер",
    "linux",
    "windows",
    "ошибк",
    "функци",
    "скрипт",
    "модель",
    "нейросет",
    "ии",
]


def main():
    with INPUT.open("r", encoding="utf-8") as f:
        data = json.load(f)

    lines = []

    lines.append("=" * 80)
    lines.append("MIA TRAINING DATA AUDIT")
    lines.append("=" * 80)
    lines.append("")

    lines.append(f"Всего примеров: {len(data)}")
    lines.append("")

    # ---------------------------------------------------------
    # Категории
    # ---------------------------------------------------------

    categories = {
        "ROMANTIC": ROMANTIC,
        "PERSONALITY": PERSONALITY,
        "ASSISTANT": ASSISTANT,
        "EMOTIONAL": EMOTIONAL,
        "TECHNICAL": TECHNICAL,
    }

    category_hits = Counter()

    example_categories = {}

    for i, item in enumerate(data, 1):
        text = (
            item.get("input", "") + " " +
            item.get("output", "")
        )

        found = []

        for category, patterns in categories.items():
            hits = contains_any(text, patterns)

            if hits:
                category_hits[category] += 1
                found.append((category, hits))

        example_categories[i] = found

    lines.append("=" * 80)
    lines.append("КАТЕГОРИИ")
    lines.append("=" * 80)

    for category, count in category_hits.most_common():
        percent = count / len(data) * 100
        lines.append(
            f"{category:12} {count:3} / {len(data)} "
            f"({percent:5.1f}%)"
        )

    lines.append("")

    # ---------------------------------------------------------
    # Романтические примеры
    # ---------------------------------------------------------

    lines.append("=" * 80)
    lines.append("РОМАНТИЧЕСКИЕ / ОТНОШЕНЧЕСКИЕ ПРИМЕРЫ")
    lines.append("=" * 80)

    romantic_count = 0

    for i, item in enumerate(data, 1):
        hits = contains_any(
            item.get("input", "") + " " + item.get("output", ""),
            ROMANTIC
        )

        if hits:
            romantic_count += 1

            lines.append("")
            lines.append(f"[{i}] Паттерны: {', '.join(hits)}")
            lines.append(f"INPUT : {item['input']}")
            lines.append(f"OUTPUT: {item['output']}")

    lines.append("")
    lines.append(f"Всего романтических примеров: {romantic_count}")

    # ---------------------------------------------------------
    # Ассистентские примеры
    # ---------------------------------------------------------

    lines.append("")
    lines.append("=" * 80)
    lines.append("АССИСТЕНТСКИЕ / СИСТЕМНЫЕ ПРИМЕРЫ")
    lines.append("=" * 80)

    assistant_count = 0

    for i, item in enumerate(data, 1):
        hits = contains_any(
            item.get("input", "") + " " + item.get("output", ""),
            ASSISTANT
        )

        if hits:
            assistant_count += 1

            lines.append("")
            lines.append(f"[{i}] Паттерны: {', '.join(hits)}")
            lines.append(f"INPUT : {item['input']}")
            lines.append(f"OUTPUT: {item['output']}")

    lines.append("")
    lines.append(f"Всего ассистентских примеров: {assistant_count}")

    # ---------------------------------------------------------
    # Технические
    # ---------------------------------------------------------

    lines.append("")
    lines.append("=" * 80)
    lines.append("ТЕХНИЧЕСКИЕ ПРИМЕРЫ")
    lines.append("=" * 80)

    technical_count = 0

    for i, item in enumerate(data, 1):
        hits = contains_any(
            item.get("input", "") + " " + item.get("output", ""),
            TECHNICAL
        )

        if hits:
            technical_count += 1

            lines.append("")
            lines.append(f"[{i}] Паттерны: {', '.join(hits)}")
            lines.append(f"INPUT : {item['input']}")
            lines.append(f"OUTPUT: {item['output']}")

    lines.append("")
    lines.append(f"Всего технических примеров: {technical_count}")

    # ---------------------------------------------------------
    # Длина ответов
    # ---------------------------------------------------------

    lengths = [
        len(item.get("output", ""))
        for item in data
    ]

    lines.append("")
    lines.append("=" * 80)
    lines.append("СТАТИСТИКА ДЛИНЫ OUTPUT")
    lines.append("=" * 80)

    lines.append(f"Минимум: {min(lengths)}")
    lines.append(f"Максимум: {max(lengths)}")
    lines.append(f"Среднее: {sum(lengths) / len(lengths):.1f}")

    # ---------------------------------------------------------
    # Повторяющиеся OUTPUT
    # ---------------------------------------------------------

    output_counter = Counter(
        normalize(item.get("output", ""))
        for item in data
    )

    repeated_outputs = [
        (text, count)
        for text, count in output_counter.items()
        if count > 1
    ]

    lines.append("")
    lines.append("=" * 80)
    lines.append("ПОВТОРЯЮЩИЕСЯ OUTPUT")
    lines.append("=" * 80)

    if not repeated_outputs:
        lines.append("Повторов нет.")
    else:
        for text, count in sorted(
            repeated_outputs,
            key=lambda x: x[1],
            reverse=True
        ):
            lines.append("")
            lines.append(f"Повторений: {count}")
            lines.append(text)

    # ---------------------------------------------------------
    # Все примеры кратко
    # ---------------------------------------------------------

    lines.append("")
    lines.append("=" * 80)
    lines.append("ПОЛНЫЙ СПИСОК")
    lines.append("=" * 80)

    for i, item in enumerate(data, 1):
        cats = ", ".join(
            category
            for category, _ in example_categories[i]
        )

        if not cats:
            cats = "UNCLASSIFIED"

        lines.append("")
        lines.append(f"[{i}] {cats}")
        lines.append(f"INPUT : {item['input']}")
        lines.append(f"OUTPUT: {item['output']}")

    OUTPUT.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print("=" * 60)
    print("АУДИТ ЗАВЕРШЁН")
    print("=" * 60)
    print(f"Примеров: {len(data)}")
    print(f"Романтических: {romantic_count}")
    print(f"Ассистентских: {assistant_count}")
    print(f"Технических: {technical_count}")
    print()
    print(f"Отчёт: {OUTPUT.resolve()}")


if __name__ == "__main__":
    main()