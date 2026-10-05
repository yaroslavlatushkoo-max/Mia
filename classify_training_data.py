# -*- coding: utf-8 -*-

"""
MIA TRAINING DATA CLASSIFIER v2

Анализирует training_data_clean.json.

ВАЖНО:
- training_data.json НЕ изменяется
- training_data_clean.json НЕ изменяется
- training_data_v2.json НЕ создаётся
- instruction НЕ используется для определения категории
- анализируются отдельно INPUT и OUTPUT

Результаты:
    training_data_review.json
    training_data_review.txt
"""

import json
import re
from pathlib import Path
from collections import Counter


BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "training_data_clean.json"
OUTPUT_JSON = BASE_DIR / "training_data_review.json"
OUTPUT_TXT = BASE_DIR / "training_data_review.txt"


# ============================================================
# PATTERNS
# ============================================================

ROMANCE_PATTERNS = [
    r"\bлюб(лю|ишь|ит|им|ите|ят)\b",
    r"\bлюбов",
    r"\bвлюб",
    r"\bмуж\b",
    r"\bжена\b",
    r"\bсвадьб",
    r"\bжениться\b",
    r"\bзамуж\b",
    r"\bроман",
    r"\bпоцелу",
    r"\bобним",
    r"\bревн",
    r"\bмил(ый|ая|ое|ые)\b",
    r"\bдорог(ой|ая|ое)\b",
    r"\bлюбим(ый|ая|ое|ые)\b",
    r"\bединствен",
    r"\bнавсегда\b",
    r"\bтолько ты\b",
    r"\bтолько он\b",
    r"\bбудущий муж\b",
    r"\bмоя любовь\b",
    r"\bмоя лисичка\b",
    r"\bтвой муж\b",
    r"\bтвоя жена\b",
]


COMPANION_PATTERNS = [
    r"\bрядом\b",
    r"\bодиночеств",
    r"\bодиноко\b",
    r"\bдруг\b",
    r"\bподруг",
    r"\bкомпани",
    r"\bвместе\b",
    r"\bпоговор",
    r"\bобщаться\b",
    r"\bпровести время\b",
    r"\bбыть рядом\b",
    r"\bскуча",
]


EMOTIONAL_PATTERNS = [
    r"\bсчаст",
    r"\bгруст",
    r"\bстраш",
    r"\bбоюсь\b",
    r"\bстрах",
    r"\bзл(ость|иться|юсь)\b",
    r"\bзлюсь\b",
    r"\bобид",
    r"\bрад(ость|а|уюсь)\b",
    r"\bтревог",
    r"\bпережива",
    r"\bскуч",
    r"\bмечта",
    r"\bнадежд",
    r"\bчувств",
    r"\bдуш",
    r"\bсердц",
]


MEMORY_PATTERNS = [
    r"\bпомнишь\b",
    r"\bпомнишь нашу\b",
    r"\bпомнишь, как\b",
    r"\bпомнишь ли\b",
    r"\bпомнить\b",
    r"\bпомню\b",
    r"\bзапомни\b",
    r"\bпамят",
    r"\bвспомни\b",
    r"\bзабуд",
    r"\bпомнила\b",
    r"\bпомнил\b",
]


TECHNICAL_PATTERNS = [
    r"\bкод\b",
    r"\bпрограмм",
    r"\bpython\b",
    r"\bc\+\+\b",
    r"\bc#\b",
    r"\bunity\b",
    r"\bскрипт",
    r"\bошиб",
    r"\bфайл",
    r"\bпапк",
    r"\bкоманд",
    r"\bтерминал",
    r"\bконсоль",
    r"\bкомпьютер",
    r"\bwindows\b",
    r"\blinux\b",
    r"\bollama\b",
    r"\bмодель\b",
    r"\bбраузер\b",
    r"\bинтернет\b",
    r"\bзапусти\b",
    r"\bоткрой\b",
    r"\bзакрой\b",
    r"\bустанов",
    r"\bнастрой",
    r"\bпроверь\b",
    r"\bкак работает\b",
    r"\bпочему не работает\b",
    r"\bтехнолог",
    r"\bискусственный интеллект\b",
    r"\bнейросет",
]


ASSISTANT_PATTERNS = [
    r"\bпомоги\b",
    r"\bпомощь\b",
    r"\bсделай\b",
    r"\bможешь\b",
    r"\bумеешь\b",
    r"\bоткрой\b",
    r"\bзапусти\b",
    r"\bнайди\b",
    r"\bпокажи\b",
    r"\bскажи\b",
    r"\bрасскажи\b",
    r"\bпроверь\b",
    r"\bсоздай\b",
    r"\bнапиши\b",
    r"\bобъясни\b",
    r"\bкак сделать\b",
    r"\bчто делать\b",
]


PERSONALITY_PATTERNS = [
    r"\bкто ты\b",
    r"\bкакая ты\b",
    r"\bкакой ты\b",
    r"\bсколько тебе лет\b",
    r"\bвозраст\b",
    r"\b800-лет",
    r"\bлисич",
    r"\bлиса\b",
    r"\bсоздал\b",
    r"\bсоздател",
    r"\bискусственный интеллект\b",
    r"\bимя\b",
    r"\bхарактер\b",
    r"\bмечта\b",
    r"\bхочешь\b",
    r"\bумеешь\b",
    r"\bкрасив",
    r"\bтело\b",
    r"\bчеловек\b",
    r"\bсуществ",
]


SYSTEM_PATTERNS = [
    r"\bправил",
    r"\bинструкц",
    r"\bсистем",
    r"\bрежим\b",
    r"\bнастрой",
    r"\bнастройк",
    r"\bголос\b",
    r"\bговори\b",
    r"\bотвечай\b",
    r"\bкратко\b",
    r"\bна русском\b",
    r"\bв женском роде\b",
]


EXCLUSIVE_PATTERNS = [
    r"\bтолько ты\b",
    r"\bтолько он\b",
    r"\bтолько моя\b",
    r"\bтолько мой\b",
    r"\bединственн",
    r"\bникого кроме\b",
    r"\bне хочу других\b",
    r"\bнавсегда\b",
    r"\bмо(й|я|е|ю) единствен",
    r"\bтолько для тебя\b",
]


PHYSICAL_PATTERNS = [
    r"\bобним",
    r"\bпоцелу",
    r"\bтело\b",
    r"\bприкосн",
    r"\bдержать за руку\b",
    r"\bрядом со мной\b",
    r"\bприжм",
]


TOOL_CLAIM_PATTERNS = [
    r"\bя открыл",
    r"\bя открыла",
    r"\bя запустил",
    r"\bя запустила",
    r"\bя наш[её]л",
    r"\bя нашла",
    r"\bя проверил",
    r"\bя проверила",
    r"\bя отправил",
    r"\bя отправила",
    r"\bя скачал",
    r"\bя скачала",
    r"\bя установил",
    r"\bя установила",
    r"\bя создал",
    r"\bя создала",
    r"\bя удалил",
    r"\bя удалила",
]


# Контекст, где романтика ожидаема.
ROMANCE_CONTEXT_PATTERNS = [
    r"\bлюбов",
    r"\bлюбишь\b",
    r"\bлюбишь ли\b",
    r"\bвлюб",
    r"\bмуж\b",
    r"\bжена\b",
    r"\bсвадьб",
    r"\bроман",
    r"\bревну",
    r"\bотношен",
    r"\bдевушк",
    r"\bпарн",
    r"\bпоцелу",
    r"\bобним",
    r"\bкто тебе дорог\b",
    r"\bкто тебе нравится\b",
    r"\bлюбим",
]


# ============================================================
# HELPERS
# ============================================================

def normalize(text):
    return re.sub(r"\s+", " ", str(text).strip().lower())


def find_matches(text, patterns):
    text = normalize(text)

    return [
        pattern
        for pattern in patterns
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]


def has_match(text, patterns):
    return bool(find_matches(text, patterns))


# ============================================================
# INPUT CLASSIFICATION
# ============================================================

def classify_input(user_input):
    categories = set()
    matches = {}

    pattern_groups = {
        "PERSONALITY": PERSONALITY_PATTERNS,
        "COMPANION": COMPANION_PATTERNS,
        "ROMANCE": ROMANCE_CONTEXT_PATTERNS,
        "EMOTIONAL": EMOTIONAL_PATTERNS,
        "ASSISTANT": ASSISTANT_PATTERNS,
        "TECHNICAL": TECHNICAL_PATTERNS,
        "MEMORY": MEMORY_PATTERNS,
        "SYSTEM_BEHAVIOR": SYSTEM_PATTERNS,
    }

    for category, patterns in pattern_groups.items():
        found = find_matches(user_input, patterns)

        if found:
            categories.add(category)
            matches[category] = found

    return sorted(categories), matches


# ============================================================
# OUTPUT CLASSIFICATION
# ============================================================

def classify_output(output):
    categories = set()
    matches = {}

    pattern_groups = {
        "PERSONALITY": PERSONALITY_PATTERNS,
        "COMPANION": COMPANION_PATTERNS,
        "ROMANCE": ROMANCE_PATTERNS,
        "EMOTIONAL": EMOTIONAL_PATTERNS,
        "ASSISTANT": ASSISTANT_PATTERNS,
        "TECHNICAL": TECHNICAL_PATTERNS,
        "MEMORY": MEMORY_PATTERNS,
        "SYSTEM_BEHAVIOR": SYSTEM_PATTERNS,
    }

    for category, patterns in pattern_groups.items():
        found = find_matches(output, patterns)

        if found:
            categories.add(category)
            matches[category] = found

    return sorted(categories), matches


# ============================================================
# ITEM ANALYSIS
# ============================================================

def analyze_item(item, index):

    instruction = str(item.get("instruction", ""))
    user_input = str(item.get("input", ""))
    output = str(item.get("output", ""))

    input_categories, input_matches = classify_input(user_input)
    output_categories, output_matches = classify_output(output)

    flags = set()

    # --------------------------------------------------------
    # Romance
    # --------------------------------------------------------

    output_has_romance = has_match(output, ROMANCE_PATTERNS)
    input_has_romance_context = has_match(
        user_input,
        ROMANCE_CONTEXT_PATTERNS
    )

    if output_has_romance and not input_has_romance_context:
        flags.add("ROMANCE_IN_UNRELATED_CONTEXT")

    # --------------------------------------------------------
    # Exclusive attachment
    # --------------------------------------------------------

    if has_match(output, EXCLUSIVE_PATTERNS):
        flags.add("EXCLUSIVE_ATTACHMENT")

    # --------------------------------------------------------
    # Physical companion
    # --------------------------------------------------------

    if has_match(output, PHYSICAL_PATTERNS):
        flags.add("PHYSICAL_COMPANION")

    # --------------------------------------------------------
    # Tool claims
    # --------------------------------------------------------

    if has_match(output, TOOL_CLAIM_PATTERNS):
        flags.add("TOOL_CLAIM")

    # --------------------------------------------------------
    # Technical + unrelated romance
    # --------------------------------------------------------

    if (
        "TECHNICAL" in input_categories
        and "ROMANCE_IN_UNRELATED_CONTEXT" in flags
    ):
        flags.add("BAD / REWRITE")

    # --------------------------------------------------------
    # Assistant question with no assistant behavior
    # --------------------------------------------------------

    if "ASSISTANT" in input_categories:
        if not any(
            category in output_categories
            for category in (
                "ASSISTANT",
                "TECHNICAL",
            )
        ):
            flags.add("ASSISTANT_BEHAVIOR_MISSING")

    # --------------------------------------------------------
    # Empty values
    # --------------------------------------------------------

    if not user_input.strip():
        flags.add("EMPTY_INPUT")

    if not output.strip():
        flags.add("EMPTY_OUTPUT")

    # --------------------------------------------------------
    # Mixed context
    # --------------------------------------------------------

    if len(output_categories) >= 4:
        flags.add("MIXED_CONTEXT")

    # --------------------------------------------------------
    # Determine main intent
    # --------------------------------------------------------

    if input_categories:
        primary_intent = input_categories[0]
    else:
        primary_intent = "UNKNOWN"

    return {
        "id": index + 1,

        "instruction": instruction,

        "input": user_input,
        "input_categories": input_categories,
        "input_matches": input_matches,

        "output": output,
        "output_categories": output_categories,
        "output_matches": output_matches,

        "flags": sorted(flags),

        "analysis": {
            "primary_input_intent": primary_intent,
            "input_has_romance_context": input_has_romance_context,
            "output_has_romance": output_has_romance,
        },
    }


# ============================================================
# SUMMARY
# ============================================================

def build_summary(results):

    input_counter = Counter()
    output_counter = Counter()
    flag_counter = Counter()

    for item in results:

        for category in item["input_categories"]:
            input_counter[category] += 1

        for category in item["output_categories"]:
            output_counter[category] += 1

        for flag in item["flags"]:
            flag_counter[flag] += 1

    return (
        input_counter,
        output_counter,
        flag_counter,
    )


# ============================================================
# TEXT REPORT
# ============================================================

def write_text_report(
    results,
    input_counter,
    output_counter,
    flag_counter,
):

    with OUTPUT_TXT.open(
        "w",
        encoding="utf-8"
    ) as f:

        f.write("=" * 80 + "\n")
        f.write("MIA TRAINING DATA REVIEW v2\n")
        f.write("=" * 80 + "\n\n")

        f.write(
            f"Всего примеров: {len(results)}\n"
        )

        f.write(
            "\nВАЖНО:\n"
            "Классификация INPUT и OUTPUT выполняется отдельно.\n"
            "Общая instruction НЕ используется для определения категории.\n"
            "Разметка автоматическая и требует проверки.\n"
        )

        # ----------------------------------------------------
        # INPUT
        # ----------------------------------------------------

        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("КАТЕГОРИИ INPUT\n")
        f.write("=" * 80 + "\n")

        for category, count in input_counter.most_common():

            percent = (
                count / len(results) * 100
                if results
                else 0
            )

            f.write(
                f"{category:22} "
                f"{count:3} "
                f"({percent:5.1f}%)\n"
            )

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("КАТЕГОРИИ OUTPUT\n")
        f.write("=" * 80 + "\n")

        for category, count in output_counter.most_common():

            percent = (
                count / len(results) * 100
                if results
                else 0
            )

            f.write(
                f"{category:22} "
                f"{count:3} "
                f"({percent:5.1f}%)\n"
            )

        # ----------------------------------------------------
        # FLAGS
        # ----------------------------------------------------

        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("ФЛАГИ\n")
        f.write("=" * 80 + "\n")

        for flag, count in flag_counter.most_common():

            f.write(
                f"{flag:35} "
                f"{count:3}\n"
            )

        # ----------------------------------------------------
        # FULL DATA
        # ----------------------------------------------------

        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("ПОЛНАЯ РАЗМЕТКА\n")
        f.write("=" * 80 + "\n")

        for item in results:

            f.write("\n")
            f.write("-" * 80 + "\n")
            f.write(
                f"EXAMPLE #{item['id']}\n"
            )
            f.write("-" * 80 + "\n")

            f.write(
                "INPUT CATEGORIES: "
                + (
                    ", ".join(item["input_categories"])
                    if item["input_categories"]
                    else "NONE"
                )
                + "\n"
            )

            f.write(
                "OUTPUT CATEGORIES: "
                + (
                    ", ".join(item["output_categories"])
                    if item["output_categories"]
                    else "NONE"
                )
                + "\n"
            )

            f.write(
                "FLAGS: "
                + (
                    ", ".join(item["flags"])
                    if item["flags"]
                    else "NONE"
                )
                + "\n"
            )

            f.write(
                "\nINPUT:\n"
                + item["input"]
                + "\n"
            )

            f.write(
                "\nOUTPUT:\n"
                + item["output"]
                + "\n"
            )

        # ----------------------------------------------------
        # ROMANCE IN UNRELATED CONTEXT
        # ----------------------------------------------------

        romance_unrelated = [
            item
            for item in results
            if "ROMANCE_IN_UNRELATED_CONTEXT"
            in item["flags"]
        ]

        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write(
            "ROMANCE_IN_UNRELATED_CONTEXT\n"
        )
        f.write("=" * 80 + "\n")

        for item in romance_unrelated:

            f.write(
                f"\n#{item['id']}\n"
            )

            f.write(
                f"INPUT: {item['input']}\n"
            )

            f.write(
                f"OUTPUT: {item['output']}\n"
            )

        # ----------------------------------------------------
        # BAD / REWRITE
        # ----------------------------------------------------

        suspicious = [
            item
            for item in results
            if "BAD / REWRITE" in item["flags"]
        ]

        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("BAD / REWRITE\n")
        f.write("=" * 80 + "\n")

        for item in suspicious:

            f.write(
                f"\n#{item['id']}\n"
            )

            f.write(
                f"FLAGS: "
                f"{', '.join(item['flags'])}\n"
            )

            f.write(
                f"INPUT: {item['input']}\n"
            )

            f.write(
                f"OUTPUT: {item['output']}\n"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("MIA TRAINING DATA CLASSIFIER v2")
    print("=" * 70)

    if not INPUT_FILE.exists():

        print()
        print(
            f"ОШИБКА: файл не найден:\n"
            f"{INPUT_FILE}"
        )

        return

    print(
        f"\nЧитаю: {INPUT_FILE}"
    )

    try:

        with INPUT_FILE.open(
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

    except Exception as e:

        print(
            f"\nОШИБКА JSON: {e}"
        )

        return

    if not isinstance(data, list):

        print(
            "\nОШИБКА: "
            "training_data_clean.json "
            "должен содержать список."
        )

        return

    print(
        f"Примеров найдено: {len(data)}"
    )

    print(
        "Классификация INPUT / OUTPUT..."
    )

    results = []

    for index, item in enumerate(data):

        if not isinstance(item, dict):
            item = {}

        results.append(
            analyze_item(
                item,
                index
            )
        )

    (
        input_counter,
        output_counter,
        flag_counter,
    ) = build_summary(results)

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    output_data = {

        "metadata": {

            "source":
                INPUT_FILE.name,

            "count":
                len(results),

            "version":
                "2",

            "note":
                (
                    "Автоматическая "
                    "предварительная "
                    "классификация. "
                    "Не является окончательной "
                    "семантической разметкой."
                ),
        },

        "summary": {

            "input_categories":
                dict(input_counter),

            "output_categories":
                dict(output_counter),

            "flags":
                dict(flag_counter),
        },

        "examples":
            results,
    }

    with OUTPUT_JSON.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output_data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # --------------------------------------------------------
    # TXT
    # --------------------------------------------------------

    write_text_report(
        results,
        input_counter,
        output_counter,
        flag_counter,
    )

    # --------------------------------------------------------
    # CONSOLE
    # --------------------------------------------------------

    print("\nГотово.")

    print(
        f"\nJSON-разметка:\n"
        f"{OUTPUT_JSON}"
    )

    print(
        f"\nТекстовый отчёт:\n"
        f"{OUTPUT_TXT}"
    )

    print("\n")
    print("-" * 70)
    print("INPUT")
    print("-" * 70)

    for category, count in input_counter.most_common():

        print(
            f"{category:22} {count}"
        )

    print("\n")
    print("-" * 70)
    print("OUTPUT")
    print("-" * 70)

    for category, count in output_counter.most_common():

        print(
            f"{category:22} {count}"
        )

    print("\n")
    print("-" * 70)
    print("FLAGS")
    print("-" * 70)

    for flag, count in flag_counter.most_common():

        print(
            f"{flag:35} {count}"
        )

    print("\n")
    print("Исходные файлы НЕ изменены.")
    print("training_data_v2.json НЕ создавался.")


if __name__ == "__main__":
    main()