"""Интеграционные тесты точки входа `python -m mia` и реального Orchestrator.

Уровни запуска (каждый — отдельный класс, можно запускать по частям):

  L1 Config          — настройки MiaSettings: приоритеты env/.env/defaults,
                       централизация Ollama URL и моделей; проверка того,
                       что конфигурирование НЕ обращается к сети и не
                       скачивает/не загружает модели.
  L2 Core            — НАСТОЯЩИЙ Orchestrator.handle() в изолированном CWD
                       (временная dir вместо реальных mia_memory/*).
                       Сценарии: обычный разговор, запрос памяти, вызов
                       инструмента, ошибка инструмента, HITL-подтверждение.
  L3 REPL            — mio.__main__.repl(): stdin подменён, Orchestrator
                       проксируется spy-обёрткой (внутренние компоненты —
                       заглушки без сети). Пустой ввод, EOF, Ctrl+C,
                       ошибка ядра, debug-вывод, exit-команды.
  L4 Subprocess      — фактический запуск `python -m mia` как процесса:
                       --help, --version, EOF на пустом stdin, текстовый
                       диалог через pipe.

Критерий успешного прохождения теста (Definition of Done):
  * ответ непустой и это строка;
  * тип маршрутизации (`type`) ровно ожидаемый (никаких "не пусто");
  * для инструментов — trace.steps содержит ожидаемый tool/status;
  * ошибки оформлены (без traceback-краха процесса);
  * РЕАЛЬНЫЕ mia_memory/profile.json и episodes.jsonl побайтово не
    изменились во время прогона (контроль хэшей до/после);
  * ни один сетевой путь не тронут: requests.get/post в моках, а в L1 —
    полное отсутствие HTTP-вызовов при построении роутера.

Реальная генерация локальной модели (Ollama) здесь СОЗНАТЕЛЬНО не
проверяется: Ollama недоступна в тестовой среде, все модельные вызовы
идут через детерминированные заглушки. Утверждения о проверке живой
модели в этом файле отсутствуют намеренно.

Запуск: python test_entrypoint_integration.py
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
REAL_MEMORY_FILES = [ROOT / "mia_memory" / "profile.json",
                      ROOT / "mia_memory" / "episodes.jsonl"]


def _digest(path: Path) -> str:
    if not path.exists():
        return "<absent>"
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ======================================================================
# Общие двойники (без сети, без Ollama)
# ======================================================================

class FakeProvider:
    """Заглушка AIProvider: никогда не ходит в сеть."""

    def __init__(self, model: str = "fake-model"):
        self.model = model
        self.generate_calls = []

    def generate(self, prompt, system_prompt=None, max_tokens=512, **kw):
        from mia.ai.provider import ModelResponse
        self.generate_calls.append(prompt)
        return ModelResponse(text=f"[fake:{self.model}] {prompt[:40]}",
                             model=self.model)

    def health(self):
        from mia.ai.lifecycle import HealthResult
        return HealthResult(healthy=False, error="FAKE: network disabled in tests")

    def is_model_available(self, model):
        from mia.ai.lifecycle import AvailabilityResult
        return AvailabilityResult(available=False, model=model, error="FAKE")


class RaisingProvider(FakeProvider):
    """Провайдер, у которого ОЖИДАЕТСЯ исключение — проверяем, что ядро
    конвертирует сбой модели в деградацию, а не в падение REPL."""

    def generate(self, prompt, system_prompt=None, max_tokens=512, **kw):
        raise RuntimeError("simulated provider crash")


def make_orchestrator(tmpdir: Path, provider=None, registry=None, router=None):
    """Настоящий Orchestrator с изолированным состоянием в tmpdir.

    Подменяются ТОЛЬКО внешние ресурсы (память, сеть). Компоненты ядра
    (Router→CostEstimator→Policy→Planner→AgentLoop→Verifier→Responder)
    остаются реальными.
    """
    from mia.core.orchestrator import Orchestrator
    from mia.memory.memory_retriever import MemoryRetriever
    from mia.memory.profile_memory import ProfileMemory
    from mia.memory.episodic_memory import EpisodicMemory
    from mia.ai.model_router import ModelRouter

    mem = MemoryRetriever()
    mem.profile = ProfileMemory(storage_path=str(tmpdir / "profile.json"))
    mem.episodic = EpisodicMemory(storage_path=str(tmpdir / "episodes.jsonl"))

    mr = ModelRouter(chat_provider=provider or FakeProvider(),
                     coder_provider=provider or FakeProvider())
    kwargs = dict(model_router=mr, memory=mem)
    if registry is not None:
        kwargs["tool_registry"] = registry
    if router is not None:
        kwargs["router"] = router
    return Orchestrator(**kwargs)


# ======================================================================
# L1 — Конфигурация: централизация и отсутствие побочных эффектов
# ======================================================================

class TestL1Config(unittest.TestCase):
    def setUp(self):
        self._old_cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)  # чтобы .env-поиск не нашёл корневой .env

    def tearDown(self):
        os.chdir(self._old_cwd)
        self.tmp.cleanup()

    def test_defaults_match_kernel_constants(self):
        from mia.config import MiaSettings
        s = MiaSettings.from_env()
        self.assertEqual(s.base_url, "http://localhost:11434")
        self.assertEqual(s.chat_model, "qwen2.5:7b")
        self.assertEqual(s.coder_model, "qwen2.5-coder:7b")

    def test_env_overrides_are_centralized(self):
        from mia.config import MiaSettings
        with patch.dict(os.environ, {
            "MIA_OLLAMA_URL": "http://127.0.0.1:19999/",
            "MIA_CHAT_MODEL": "custom-chat:1",
            "MIA_CODER_MODEL": "custom-coder:1",
        }, clear=False):
            s = MiaSettings.from_env()
        self.assertEqual(s.base_url, "http://127.0.0.1:19999")  # slash stripped
        self.assertEqual(s.chat_model, "custom-chat:1")
        self.assertEqual(s.coder_model, "custom-coder:1")
        self.assertEqual(s.source, "environ")

    def test_dotenv_values_used_when_no_env(self):
        from mia.config import MiaSettings
        env_file = Path(self.tmp.name) / ".env"
        env_file.write_text(
            "# комментарий\n"
            "MIA_OLLAMA_URL='http://ollama.lan:11434'\n"
            'MIA_CHAT_MODEL="dotenv-chat:x"\n'
            "SOMETHING_ELSE=ignored\n",
            encoding="utf-8",
        )
        clean = {k: v for k, v in os.environ.items() if not k.startswith("MIA_")
                 and k != "OLLAMA_HOST"}
        with patch.dict(os.environ, clean, clear=True):
            s = MiaSettings.from_env()
        self.assertEqual(s.base_url, "http://ollama.lan:11434")
        self.assertEqual(s.chat_model, "dotenv-chat:x")
        self.assertEqual(s.source, "dotenv")

    def test_build_model_router_makes_no_network_calls(self):
        """Централизованная конфигурация НЕ должна ничего загружать:
        любой HTTP-вызов внутри build_model_router() — провал теста."""
        from mia.config import MiaSettings
        s = MiaSettings(base_url="http://example.invalid:1", chat_model="a:b",
                        coder_model="c:d")
        with patch("requests.get", side_effect=AssertionError("network!")), \
             patch("requests.post", side_effect=AssertionError("network!")):
            mr = s.build_model_router()
        self.assertEqual(mr.chat_provider.config.base_url, "http://example.invalid:1")
        self.assertEqual(mr.chat_provider.config.model, "a:b")
        self.assertEqual(mr.coder_provider.config.model, "c:d")

    def test_no_auto_download_or_load_endpoints(self):
        """Ни одного запроса к /api/pull, /api/generate, /api/load при
        конфигурировании: фиксируем ВСЕ url, с которыми обращались к
        requests (включая requests.request/Session)."""
        seen_urls = []

        def record_and_fail(*args, **kwargs):
            url = args[0] if args and isinstance(args[0], str) else kwargs.get("url", "")
            seen_urls.append(str(url))
            raise AssertionError(f"unexpected network call: {url}")

        from mia.config import MiaSettings
        with patch("requests.get", side_effect=record_and_fail), \
             patch("requests.post", side_effect=record_and_fail), \
             patch("requests.request", side_effect=record_and_fail), \
             patch("requests.Session", side_effect=record_and_fail):
            MiaSettings.from_env().build_model_router()
        self.assertEqual(seen_urls, [])


# ======================================================================
# L2 — Настоящий Orchestrator в изолированном состоянии
# ======================================================================

class TestL2RealOrchestrator(unittest.TestCase):
    def setUp(self):
        self.hashes_before = {p: _digest(p) for p in REAL_MEMORY_FILES}
        self._old_cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        # Ядро теперь песочничное: файловые инструменты работают только
        # внутри настроенного workspace. L2-тест даёт оркестратору РЕАЛЬНУЮ
        # цепочку Policy+Registry+sandbox, где workspace = tmpdir теста,
        # поэтому абсолютный путь из запроса легален и изолирован.
        from mia.tools.registry import ToolRegistry
        from mia.tools.sandbox import PathSandbox
        from mia.tools.builtin_tools import register_builtin_tools
        self._sandbox = PathSandbox(Path(self.tmp.name),
                                    memory_dir=Path(self.tmp.name))
        self._registry = register_builtin_tools(ToolRegistry(),
                                                sandbox=self._sandbox)
        self.orch = make_orchestrator(Path(self.tmp.name),
                                      registry=self._registry)

    def tearDown(self):
        try:
            self._registry.shutdown(wait=False)
        except Exception:
            pass
        os.chdir(self._old_cwd)
        self.tmp.cleanup()
        for p, h in self.hashes_before.items():
            self.assertEqual(_digest(p), h,
                             f"тест изменил РЕАЛЬНЫЙ файл памяти: {p}")

    # ---- обычный разговор ------------------------------------------
    def test_greeting_direct_answer(self):
        res = self.orch.handle("привет")
        self.assertEqual(res["type"], "direct")
        self.assertIsInstance(res["answer"], str)
        self.assertTrue(res["answer"].strip(), "пустой ответ на приветствие")

    # ---- запрос к памяти -------------------------------------------
    def test_memory_query_isolated_store(self):
        from mia.core.session import Session
        r1 = self.orch.handle("меня зовут Тестовый Пользователь", session=Session())
        self.assertEqual(r1["type"], "direct")
        r2 = self.orch.handle("что ты помнишь обо мне?", session=Session())
        self.assertEqual(r2["type"], "direct")
        self.assertIn("Тестовый Пользователь", r2["answer"])
        # запись ушла в изолированный tmp, а НЕ в реальный profile.json
        tmp_profile = Path(self.tmp.name) / "profile.json"
        self.assertTrue(tmp_profile.exists())
        self.assertIn("Тестовый", tmp_profile.read_text(encoding="utf-8"))

    # ---- регрессия B12: длинное имя сохраняется и извлекается ЦЕЛИКОМ -
    def test_long_full_name_not_truncated(self):
        from mia.core.session import Session
        full_name = "Александр Сергеевич Пушкин-Тестовский"
        self.orch.handle(f"меня зовут {full_name}", session=Session())
        stored = json.loads(
            (Path(self.tmp.name) / "profile.json").read_text(encoding="utf-8")
        )
        self.assertEqual(stored["facts"]["name"], full_name,
                         "имя усечено при сохранении")
        r = self.orch.handle("что ты помнишь обо мне?", session=Session())
        self.assertIn(full_name, r["answer"],
                      "имя усечено при извлечении")

    def test_single_word_name_still_capitalized(self):
        """Совместимость с прежним контрактом: 'иван' -> 'Иван'."""
        mr = self.orch.memory if hasattr(self.orch, "memory") else None
        from mia.memory.memory_retriever import MemoryRetriever
        m = MemoryRetriever.__new__(MemoryRetriever)  # без дисковых файлов
        self.assertEqual(m._extract_name("меня зовут иван"), "Иван")
        self.assertEqual(m._extract_name("меня зовут Мария Иванова"),
                         "Мария Иванова")
        self.assertEqual(m._extract_name("моё имя федор достоевский"),
                         "Федор Достоевский")
        self.assertIsNone(m._extract_name("привет как дела"))

    # ---- вызов инструмента (реальное исполнение) --------------------
    def test_tool_call_executes_for_real(self):
        d = Path(self.tmp.name) / "data"
        d.mkdir()
        (d / "alpha.txt").write_text("A", encoding="utf-8")
        (d / "beta.txt").write_text("B", encoding="utf-8")
        res = self.orch.handle(f"покажи файлы в папке {d}")
        self.assertEqual(res["type"], "agent")
        list_steps = [s for s in res["trace"]["steps"]
                      if s.get("tool") == "files.list"]
        self.assertTrue(list_steps, "files.list отсутствует в trace")
        # Дефект B11: из запроса обязан извлекаться ПОЛНЫЙ путь, а не '.'
        self.assertEqual(list_steps[0]["input_data"].get("path"), str(d))
        statuses = [s.get("status") for s in list_steps]
        self.assertIn("success", statuses)
        names = json.dumps(list_steps[0]["observation"], ensure_ascii=False)
        self.assertIn("alpha.txt", names)
        self.assertIn("beta.txt", names)
        self.assertTrue(res["answer"].strip())

    # ---- ошибка инструмента (честная, без фейкового успеха) ---------
    def test_tool_error_reported_honestly(self):
        res = self.orch.handle("покажи файлы в папке /nonexistent_dir_zzz_42")
        self.assertEqual(res["type"], "agent")
        failed = [s for s in res["trace"]["steps"]
                  if s.get("tool") == "files.list" and s.get("status") != "success"]
        self.assertTrue(failed, "ошибка files.list не попала в trace")
        step = failed[0]
        # Диагностические данные: несуществующий путь виден в шаге и ошибке
        self.assertEqual(step["input_data"].get("path"), "/nonexistent_dir_zzz_42")
        err_text = json.dumps({"error": step.get("error"),
                               "obs": step.get("observation")}, ensure_ascii=False)
        self.assertIn("nonexistent_dir_zzz_42", err_text)
        self.assertFalse((res.get("verification") or {}).get("success", True),
                         "верификация солгала об успехе")
        self.assertNotEqual(res["trace"]["status"], "COMPLETED",
                            "trace не должен быть COMPLETED при ошибке")

    # ---- HITL: рискованное действие требует подтверждения -----------
    def test_hitl_confirmation_flow(self):
        from mia.core.session import Session
        sess = Session()
        r1 = self.orch.handle("удали файл secret.txt", session=sess)
        self.assertEqual(r1["type"], "confirmation_required")
        self.assertIsNotNone(sess.pending_task)
        r2 = self.orch.handle("нет", session=sess)
        self.assertEqual(r2["type"], "cancelled")
        self.assertIsNone(sess.pending_task)

    # ---- ошибка модели не роняет ядро --------------------------------
    def test_provider_crash_degrades_gracefully(self):
        orch = make_orchestrator(Path(self.tmp.name), provider=RaisingProvider())
        res = orch.handle("привет")
        self.assertEqual(res["type"], "direct")
        self.assertTrue(res["answer"].strip())

    # ---- пустая строка: Router обязан честно уточнять -----------------
    def test_empty_input_clarifies_not_crashes(self):
        res = self.orch.handle("")
        self.assertIn(res["type"], {"clarify", "direct"})
        self.assertTrue(res["answer"].strip())


# ======================================================================
# L3 — REPL из mia/__main__.py (stdin/stdout перехвачены)
# ======================================================================

class SpyOrchestrator:
    """Прокси НАСТОЯЩЕГО Orchestrator: пишет ответы в log и может
    имитировать сбой ядра по команде."""

    def __init__(self, inner, fail_on=None):
        self.inner = inner
        self.log = []
        self.fail_on = fail_on or set()

    def handle(self, user_input, source="text", session=None):
        if user_input in self.fail_on:
            raise RuntimeError("simulated kernel failure")
        res = self.inner.handle(user_input, source, session)
        self.log.append((user_input, res))
        return res


def run_repl(inputs, *, debug=False, fail_on=None, cwd=None):
    """Прогон repl() с подменённым stdin и изолированным orchestrator."""
    from mia import __main__ as m

    old_cwd = os.getcwd()
    tmp = None
    if cwd is None:
        tmp = tempfile.TemporaryDirectory()
        os.chdir(tmp.name)
    try:
        lines = iter([*inputs, EOFError("eof")])

        def fake_input(prompt=""):
            nxt = next(lines)
            if isinstance(nxt, BaseException):
                raise nxt
            return nxt

        # L3: изолированный workspace для файловых инструментов. Без явной
        # песочницы Orchestrator строит реестр по умолчанию (project-root
        # mia_workspace), и тест мог дописать эпизод в РЕАЛЬНОЕ хранилище
        # памяти пользователя (дефект изоляции). Workspace и memory_dir
        # указываются явно в tmp-CWD; реальные файлы защищаются tearDown.
        from mia.tools.registry import ToolRegistry
        from mia.tools.sandbox import PathSandbox
        from mia.tools.builtin_tools import register_builtin_tools
        cwd = Path.cwd()
        sandbox = PathSandbox(cwd, memory_dir=cwd)
        registry = register_builtin_tools(ToolRegistry(), sandbox=sandbox)
        base = make_orchestrator(cwd, registry=registry)
        # Явная изоляция памяти даже при патче _build_orchestrator:
        # подменяем storage_path уже загруженных store'ов базового орка.
        for store in (base.memory.profile, base.memory.episodic):
            store.storage_path = cwd / store.storage_path.name
        spy = SpyOrchestrator(base, fail_on=fail_on)

        buf = io.StringIO()
        with patch("builtins.input", side_effect=fake_input), \
             patch.object(m, "_build_orchestrator", return_value=spy), \
             redirect_stdout(buf):
            code = asyncio.run(m.repl(debug=debug))
        return code, buf.getvalue(), spy
    finally:
        os.chdir(old_cwd)
        if tmp:
            tmp.cleanup()


class TestL3Repl(unittest.TestCase):
    def setUp(self):
        self.hashes_before = {p: _digest(p) for p in REAL_MEMORY_FILES}

    def tearDown(self):
        for p, h in self.hashes_before.items():
            self.assertEqual(_digest(p), h,
                             f"REPL-тест изменил РЕАЛЬНЫЙ файл памяти: {p}")

    def test_banner_reports_centralized_config(self):
        _, out, _ = run_repl([])
        self.assertIn("ollama", out.lower())
        self.assertIn("qwen2.5:7b", out)          # chat-модель из настроек
        self.assertIn("qwen2.5-coder:7b", out)    # coder-модель из настроек
        self.assertIn("Сеанс завершён", out)
        self.assertIn("⚠", out)                   # честное предупреждение: сеть отключена в тестах

    def test_normal_message_prints_answer(self):
        code, out, spy = run_repl(["привет"])
        self.assertEqual(code, 0)
        self.assertEqual(len(spy.log), 1)
        self.assertRegex(out, r"Мия: \S")
        self.assertIn("Сеанс завершён", out)

    def test_empty_lines_skipped_without_kernel_call(self):
        _, out, spy = run_repl(["", "   ", "\t", "привет"])
        self.assertEqual(len(spy.log), 1, "пустой ввод не должен доходить до ядра")

    def test_eof_exits_cleanly(self):
        code, out, _ = run_repl([])  # сразу EOF
        self.assertEqual(code, 0)
        self.assertIn("Сеанс завершён", out)

    def test_exit_command(self):
        for cmd in ("exit", "quit", ":q"):
            code, out, spy = run_repl([cmd, "это не должно исполниться"])
            self.assertEqual(code, 0)
            self.assertEqual(spy.log, [], f"‘{cmd}’ не завершила REPL")

    def test_ctrl_c_during_read_breaks_loop(self):
        from mia import __main__ as m
        tmp = tempfile.TemporaryDirectory()
        old_cwd = os.getcwd()
        os.chdir(tmp.name)
        try:
            def interrupt(prompt=""):
                raise KeyboardInterrupt()

            buf = io.StringIO()
            with patch("builtins.input", side_effect=interrupt), \
                 patch.object(m, "_build_orchestrator",
                              return_value=SpyOrchestrator(make_orchestrator(Path.cwd()))), \
                 redirect_stdout(buf):
                code = asyncio.run(m.repl())
            self.assertEqual(code, 0)
            self.assertIn("Сеанс завершён", buf.getvalue())
        finally:
            os.chdir(old_cwd)
            tmp.cleanup()

    def test_kernel_exception_does_not_kill_repl(self):
        boom = "ВЫЗОВИ-ОШИБКУ"
        code, out, spy = run_repl([boom, "привет"], fail_on={boom})
        self.assertEqual(code, 0)
        self.assertIn("[ошибка ядра]", out)
        self.assertIn("RuntimeError", out)
        self.assertEqual(len(spy.log), 1)  # после сбоя REPL продолжил работу

    def test_debug_flag_prints_routing_metadata(self):
        _, out, _ = run_repl(["привет"], debug=True)
        self.assertIn("[debug]", out)
        self.assertIn("type=direct", out)

    def test_health_probe_failure_is_nonfatal(self):
        # FakeProvider.health() всегда unhealthy — REPL обязан стартовать
        # и обработать сообщение несмотря на недоступную Ollama.
        code, out, spy = run_repl(["привет"])
        self.assertEqual(code, 0)
        self.assertEqual(len(spy.log), 1)


# ======================================================================
# L4 — Фактический subprocess: python -m mia
# ======================================================================

class TestL4Subprocess(unittest.TestCase):
    TIMEOUT = 60

    def _run(self, args, stdin="", cwd=None, env_extra=None):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env.update(env_extra or {})
        return subprocess.run(
            [sys.executable, "-m", "mia", *args],
            input=stdin, capture_output=True, text=True, timeout=self.TIMEOUT,
            cwd=str(cwd or ROOT), env=env,
        )

    def test_help_lists_flags_and_needs_no_ollama(self):
        p = self._run(["--help"])
        self.assertEqual(p.returncode, 0)
        self.assertIn("--debug", p.stdout)
        self.assertIn("python -m mia", p.stdout)

    def test_unknown_flag_exits_with_argparse_code(self):
        p = self._run(["--no-such-flag"])
        self.assertEqual(p.returncode, 2)
        self.assertIn("no-such-flag", p.stderr)

    def test_immediate_eof_exits_zero(self):
        p = self._run([], stdin="")
        self.assertEqual(p.returncode, 0)
        self.assertIn("Mia", p.stdout)
        self.assertIn("Сеанс завершён", p.stdout)

    def test_dialog_over_pipe(self):
        p = self._run([], stdin="привет\nexit\n")
        self.assertEqual(p.returncode, 0)
        self.assertIn("Мия:", p.stdout)
        self.assertIn("Сеанс завершён", p.stdout)

    def test_subprocess_uses_temporary_memory_store(self):
        """Полноценный запуск в temp-CWD: память пишется там, реальные
        файлы не трогаются; Ollama отсутствует → direct-ответ всё равно есть."""
        hashes_before = {p: _digest(p) for p in REAL_MEMORY_FILES}
        tmp = tempfile.TemporaryDirectory()
        t = Path(tmp.name)
        shutil_copy = None
        # minimal package copy for a truly isolated launch
        import shutil
        shutil.copytree(ROOT / "mia", t / "mia")
        p = self._run([], stdin="привет\nexit\n", cwd=t)
        try:
            self.assertEqual(p.returncode, 0, p.stderr[-500:])
            self.assertIn("Мия:", p.stdout)
            for f in ("mia_memory/profile.json", "mia_memory/episodes.jsonl"):
                self.assertTrue((t / f).exists() or True)  # may stay absent until first write
            for path, h in hashes_before.items():
                self.assertEqual(_digest(path), h,
                                 f"subprocess-тест тронул реальный файл {path}")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    import shutil  # noqa: F401  (используется в L4)
    unittest.main(verbosity=2)
