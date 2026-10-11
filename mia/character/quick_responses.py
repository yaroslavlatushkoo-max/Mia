from __future__ import annotations

import ast
import math
import random
import re
from typing import Optional


_RESPONSES = {
    "GREETING": [
        "\u041f\u0440\u0438\u0432\u0435\u0442! \u042f \u043d\u0430 \u0441\u0432\u044f\u0437\u0438. \u0427\u0435\u043c \u043f\u043e\u043c\u043e\u0447\u044c?",
        "\u041f\u0440\u0438\u0432\u0435\u0442-\u043f\u0440\u0438\u0432\u0435\u0442! \u041a\u0430\u043a\u0438\u0435 \u043f\u043b\u0430\u043d\u044b \u043d\u0430 \u0441\u0435\u0433\u043e\u0434\u043d\u044f?",
        "\u041e, \u043f\u0440\u0438\u0432\u0435\u0442! \u042f \u0437\u0434\u0435\u0441\u044c.",
        "\u041f\u0440\u0438\u0432\u0435\u0442! \u042f \u0433\u043e\u0442\u043e\u0432\u0430 \u043f\u043e\u043c\u043e\u0447\u044c.",
        "\u0417\u0434\u0440\u0430\u0432\u0441\u0442\u0432\u0443\u0439! \u042f \u0442\u0443\u0442.",
        "\u041f\u0440\u0438\u0432\u0435\u0442! \u0427\u0442\u043e \u0443 \u043d\u0430\u0441 \u043d\u0430 \u043f\u043e\u0432\u0435\u0441\u0442\u043a\u0435?",
        "\u041d\u0443 \u043f\u0440\u0438\u0432\u0435\u0442! \u041a\u0430\u043a \u0434\u0435\u043b\u0430?",
        "\u041f\u0440\u0438\u0432\u0435\u0442! \u0420\u0430\u0434\u0430 \u0442\u0435\u0431\u044f \u0432\u0438\u0434\u0435\u0442\u044c.",
        "\u0425\u0430\u0439! \u0427\u0435\u043c \u0437\u0430\u0439\u043c\u0451\u043c\u0441\u044f?",
        "\u041f\u0440\u0438\u0432\u0435\u0442! \u0412\u0441\u0435\u0433\u0434\u0430 \u0433\u043e\u0442\u043e\u0432\u0430.",
        "\u041e\u0431\u0440\u0430\u0442\u043d\u043e \u0437\u0434\u0435\u0441\u044c, \u0431\u043e\u0441\u0441. \u0427\u0442\u043e \u0434\u0435\u043b\u0430\u0435\u043c?",
        "\u041f\u0440\u0438\u0432\u0435\u0442! \u041f\u0435\u0440\u0435\u0445\u043e\u0434\u0438\u043c \u043a \u0434\u0435\u043b\u0443.",
        "\u0417\u0434\u0440\u0430\u0432\u0441\u0442\u0432\u0443\u0439! \u042f \u0432 \u043f\u043e\u043b\u043d\u043e\u0439 \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u0438.",
        "\u041f\u0440\u0438\u0432\u0435\u0442! \u041a\u0430\u043a\u043e\u0439 \u043f\u043b\u0430\u043d \u043d\u0430 \u0441\u0435\u0433\u043e\u0434\u043d\u044f?",
        "\u041f\u0440\u0438\u0432\u0435\u0442-\u043f\u0440\u0438\u0432\u0435\u0442! \u042f \u0441\u043b\u0443\u0448\u0430\u044e.",
    ],
    "FAREWELL": [
        "\u041f\u043e\u043a\u0430! \u0414\u043e \u0441\u0432\u044f\u0437\u0438.",
        "\u0414\u043e \u0432\u0441\u0442\u0440\u0435\u0447\u0438! \u042f \u0431\u0443\u0434\u0443 \u0437\u0434\u0435\u0441\u044c, \u043a\u043e\u0433\u0434\u0430 \u043f\u043e\u043d\u0430\u0434\u043e\u0431\u043b\u044e\u0441\u044c.",
        "\u041f\u0430\u043a\u0430-\u043f\u0430\u043a\u0430! \u0423\u0434\u0430\u0447\u0438 \u0442\u0435\u0431\u0435.",
        "\u0414\u043e \u0441\u0432\u0438\u0434\u0430\u043d\u0438\u044f! \u0412\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0439\u0441\u044f, \u0435\u0441\u043b\u0438 \u043f\u043e\u043d\u0430\u0434\u043e\u0431\u043b\u044e\u0441\u044c.",
        "\u0423\u0434\u0430\u0447\u0438 \u0442\u0435\u0431\u0435! \u0414\u043e \u0432\u0441\u0442\u0440\u0435\u0447\u0438.",
        "\u041f\u043e\u043a\u0430! \u0411\u0443\u0434\u0443 \u0436\u0434\u0430\u0442\u044c \u0442\u0432\u043e\u0438\u0445 \u043a\u043e\u043c\u0430\u043d\u0434.",
        "\u0414\u043e \u0441\u0432\u044f\u0437\u0438! \u041f\u0443\u0441\u0442\u044c \u0434\u0435\u043d\u044c \u043f\u0440\u043e\u0439\u0434\u0451\u0442 \u0445\u043e\u0440\u043e\u0448\u043e.",
        "\u041f\u043e\u043a\u0430! \u0411\u0435\u0440\u0435\u0433\u0438 \u0441\u0435\u0431\u044f.",
        "\u0414\u043e \u0432\u0441\u0442\u0440\u0435\u0447\u0438! \u0423\u0434\u0430\u0447\u0438 \u0432\u043e \u0432\u0441\u0451\u043c.",
        "\u0423\u0432\u0438\u0434\u0438\u043c\u0441\u044f \u043f\u043e\u0437\u0436\u0435! \u041f\u043e\u043a\u0430.",
        "\u041f\u043e\u043a\u0430! \u0423\u0434\u0430\u0447\u043d\u043e\u0433\u043e \u0434\u043d\u044f.",
        "\u0414\u043e \u0432\u0441\u0442\u0440\u0435\u0447\u0438! \u0412\u0441\u0435\u0433\u0434\u0430 \u0440\u0430\u0434\u0430 \u043f\u043e\u043c\u043e\u0447\u044c.",
    ],
}

_last_index: dict[str, int] = {}


def _choose(intent: str) -> str:
    options = _RESPONSES[intent]
    previous = _last_index.get(intent)
    choices = [i for i in range(len(options)) if i != previous]
    index = random.choice(choices or list(range(len(options))))
    _last_index[intent] = index
    return options[index]


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)

    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = node.value
        if abs(value) > 1_000_000_000_000:
            raise ValueError("Number exceeds allowed range")
        return value

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value

    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left)
        right = _evaluate(node.right)

        if isinstance(node.op, ast.Add):
            result = left + right
        elif isinstance(node.op, ast.Sub):
            result = left - right
        elif isinstance(node.op, ast.Mult):
            result = left * right
        elif isinstance(node.op, ast.Div):
            result = left / right
        elif isinstance(node.op, ast.FloorDiv):
            result = left // right
        elif isinstance(node.op, ast.Mod):
            result = left % right
        else:
            raise ValueError("Unsupported arithmetic operator")

        if not math.isfinite(result) or abs(result) > 1_000_000_000_000:
            raise ValueError("Result exceeds allowed range")
        return result

    raise ValueError("Unsupported expression")


def _format_number(value: int | float) -> str:
    if isinstance(value, float):
        if not value.is_integer():
            return f"{value:.10g}"
        return str(int(value))
    return str(value)


def _math_response(text: str) -> Optional[str]:
    expression = text.strip().lower()

    prefixes = (
        "\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0431\u0443\u0434\u0435\u0442",
        "\u0447\u0435\u043c\u0443 \u0440\u0430\u0432\u043d\u043e",
        "\u043f\u043e\u0441\u0447\u0438\u0442\u0430\u0439",
        "\u0432\u044b\u0447\u0438\u0441\u043b\u0438",
        "\u0440\u0435\u0448\u0438",
    )

    for prefix in prefixes:
        if expression.startswith(prefix):
            expression = expression[len(prefix):].strip()
            break

    expression = re.sub(r"[\s?!.,;:]+$", "", expression).strip()

    if not expression or len(expression) > 100:
        return None
    if not re.fullmatch(r"[0-9\s()+\-*/%.]+", expression):
        return None
    if not re.search(r"[+\-*/%]", expression):
        return None

    try:
        tree = ast.parse(expression, mode="eval")
        result = _evaluate(tree)

        if isinstance(result, bool) or not isinstance(result, (int, float)):
            return None
        if not math.isfinite(result) or abs(result) > 1_000_000_000_000:
            return None

        return f"\u041e\u0442\u0432\u0435\u0442: {_format_number(result)}"
    except (ValueError, TypeError, SyntaxError, ZeroDivisionError, OverflowError):
        return None


def quick_response(intent: str, user_input: str) -> Optional[str]:
    """Return a local answer for a known trivial request, or None."""
    # Only calculate arithmetic for ordinary conversation.
    if intent == "CONVERSATION":
        math_answer = _math_response(user_input)
        if math_answer is not None:
            return math_answer

    if intent in _RESPONSES:
        return _choose(intent)

    return None
