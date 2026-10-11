from types import SimpleNamespace

import pytest

from mia.character.quick_responses import quick_response
from mia.core.orchestrator import Orchestrator


@pytest.mark.parametrize(
    ("intent", "text"),
    [
        ("GREETING", "Привет!"),
        ("GREETING", "здравствуй"),
        ("FAREWELL", "пока"),
    ],
)
def test_quick_social_responses(intent, text):
    answer = quick_response(intent, text)
    assert isinstance(answer, str)
    assert answer.strip()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
            ("\u0421\u043a\u043e\u043b\u044c\u043a\u043e \u0431\u0443\u0434\u0435\u0442 2 + 2?", "4"),
        ("2 * (3 + 4)", "14"),
            ("\u0421\u043a\u043e\u043b\u044c\u043a\u043e \u0431\u0443\u0434\u0435\u0442 10 / 2", "5"),
        ("-3 + 8", "5"),
    ],
)
def test_local_arithmetic(text, expected):
    answer = quick_response("CONVERSATION", text)
    assert answer is not None
    assert expected in answer


def test_math_does_not_execute_code():
    assert quick_response("CONVERSATION", "__import__('os').system('whoami')") is None


def test_math_division_by_zero_falls_back():
    assert quick_response("CONVERSATION", "1 / 0") is None


def test_greeting_bypasses_model_generation(monkeypatch):
    orchestrator = Orchestrator()
    monkeypatch.setattr(
        orchestrator,
        "_try_local_answer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("??? ??????????? ?????? ???????? ??????")
        ),
    )
    ctx = SimpleNamespace(intent="GREETING", raw_input="??????!", mode=SimpleNamespace(value="COMPANION"))
    answer = orchestrator._direct_response(ctx)
    assert isinstance(answer, str)
    assert answer.strip()


def test_arithmetic_bypasses_model_generation(monkeypatch):
    orchestrator = Orchestrator()
    monkeypatch.setattr(
        orchestrator,
        "_try_local_answer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("??? ?????????? ?????? ???????? ??????")
        ),
    )
    ctx = SimpleNamespace(
        intent="CONVERSATION",
        raw_input="\u0421\u043a\u043e\u043b\u044c\u043a\u043e \u0431\u0443\u0434\u0435\u0442 2 + 2?",
        mode=SimpleNamespace(value="ASSISTANT"),
    )
    answer = orchestrator._direct_response(ctx)
    assert "4" in answer



def test_arithmetic_does_not_intercept_tool_intent():
    assert quick_response("TOOL", "2 + 2") is None
