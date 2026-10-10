"""Тесты единого изолируемого хранилища памяти (этап: memory config).

Покрывает:
  * выбор каталога памяти и приоритеты (явный arg > env > .env > default);
  * независимость default от CWD запуска;
  * отсутствие записи вне заданного каталога;
  * одновременную работу двух экземпляров с разными хранилищами;
  * сохранение/загрузку данных (форматы profile.json / episodes.jsonl не меняются);
  * отсутствующие файлы, повреждённый JSON, ошибки записи, отсутствие дубликатов.

Реальные пользовательские файлы НЕ затрагиваются: каждый тест работает со
своим временным каталогом, а MIA_MEMORY_DIR подчищается после модуля.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from mia.config import (
    MiaSettings,
    MEMORY_DIR_ENV,
    PROFILE_FILENAME,
    EPISODES_FILENAME,
    default_memory_dir,
    resolve_memory_dir,
)
from mia.memory.memory_retriever import MemoryRetriever
from mia.memory.profile_memory import ProfileMemory, UserProfile
from mia.memory.episodic_memory import EpisodicMemory


class TempMemoryCase(unittest.TestCase):
    """Базовый кейс: свой tmp-каталог + очистка MIA_MEMORY_DIR."""

    def setUp(self):
        self._saved_env = os.environ.get(MEMORY_DIR_ENV)
        os.environ.pop(MEMORY_DIR_ENV, None)
        self.tmp = Path(tempfile.mkdtemp(prefix="mia_mem_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self._saved_env is None:
            os.environ.pop(MEMORY_DIR_ENV, None)
        else:
            os.environ[MEMORY_DIR_ENV] = self._saved_env


class TestMemoryDirSelection(TempMemoryCase):
    def test_explicit_argument_wins_over_env(self):
        os.environ[MEMORY_DIR_ENV] = str(self.tmp / "from_env")
        resolved = resolve_memory_dir(explicit=str(self.tmp / "explicit"))
        self.assertEqual(resolved, self.tmp / "explicit")

    def test_env_beats_dotenv_and_default(self):
        os.environ[MEMORY_DIR_ENV] = str(self.tmp / "from_env")
        self.assertEqual(resolve_memory_dir(), self.tmp / "from_env")

    def test_settings_memory_dir_field_propagates(self):
        s = MiaSettings(memory_dir=self.tmp / "via_settings")
        m = s.build_memory()
        self.assertEqual(m.memory_dir, self.tmp / "via_settings")
        self.assertEqual(m.profile.storage_path, self.tmp / "via_settings" / PROFILE_FILENAME)
        self.assertEqual(m.episodic.storage_path, self.tmp / "via_settings" / EPISODES_FILENAME)

    def test_from_env_picks_up_memory_dir(self):
        os.environ[MEMORY_DIR_ENV] = str(self.tmp / "env_only")
        s = MiaSettings.from_env(dotenv_path=self.tmp / "nonexistent.env")
        self.assertEqual(s.resolved_memory_dir(), self.tmp / "env_only")

    def test_dotenv_used_when_no_env_var(self):
        dotenv = self.tmp / ".env"
        dotenv.write_text(
            f"{MEMORY_DIR_ENV}={self.tmp / 'from_dotenv'}\n", encoding="utf-8"
        )
        s = MiaSettings.from_env(dotenv_path=dotenv)
        self.assertEqual(s.resolved_memory_dir(), self.tmp / "from_dotenv")

    def test_empty_values_fall_back_to_default(self):
        os.environ[MEMORY_DIR_ENV] = "   "
        self.assertEqual(resolve_memory_dir(), default_memory_dir())

    def test_default_is_cwd_independent(self):
        """Ключевой дефект прошлого этапа: относительный путь зависел от CWD."""
        other = self.tmp / "elsewhere"
        other.mkdir()
        cwd = os.getcwd()
        try:
            os.chdir(other)
            self.assertEqual(default_memory_dir(), Path(cwd) / "mia_memory")
        finally:
            os.chdir(cwd)


class TestIsolation(TempMemoryCase):
    def test_no_writes_outside_selected_dir(self):
        store = self.tmp / "store"
        orch_store = self.tmp / "outside_check"
        orch_store.mkdir()
        mem = MemoryRetriever(memory_dir=store)
        mem.extract_and_remember("Меня зовут Тестовый Пользователь, я люблю Python", "ok")
        mem.episodic.add_episode("task", "content", importance=3)

        self.assertTrue((store / PROFILE_FILENAME).exists())
        self.assertTrue((store / EPISODES_FILENAME).exists())
        # нигде вне store нет артефактов памяти
        leaked = [p for p in self.tmp.rglob("*") if p.is_file() and store not in p.parents]
        self.assertEqual([str(p) for p in leaked], [str(self.tmp / ".keep")] if False else [],
                         f"запись вне выбранного каталога: {leaked}")

    def test_two_instances_two_storages(self):
        a_dir, b_dir = self.tmp / "a", self.tmp / "b"
        a = MemoryRetriever(memory_dir=a_dir)
        b = MemoryRetriever(memory_dir=b_dir)
        a.extract_and_remember("Меня зовут Алиса Петровна", "ok")
        b.extract_and_remember("Меня зовут Борис", "ok")

        self.assertEqual(a.profile.get_profile().facts["name"], "Алиса Петровна")
        self.assertEqual(b.profile.get_profile().facts["name"], "Борис")
        # перечитывание с диска подтверждает физическую изоляцию
        a2 = MemoryRetriever(memory_dir=a_dir)
        b2 = MemoryRetriever(memory_dir=b_dir)
        self.assertEqual(a2.profile.get_profile().facts["name"], "Алиса Петровна")
        self.assertEqual(b2.profile.get_profile().facts["name"], "Борис")
        self.assertNotIn("Борис", a2.profile.get_summary())
        self.assertNotIn("Алиса", b2.profile.get_summary())

    def test_orchestrator_respects_injected_memory_dir(self):
        from mia.core.orchestrator import Orchestrator
        store = self.tmp / "orch_store"
        settings = MiaSettings(memory_dir=store)
        orch = Orchestrator(model_router=None, memory=settings.build_memory())
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = orch.handle("Меня зовут Кирилл Тестовский, я работаю с Python")
        self.assertEqual(result["type"], "direct")
        self.assertTrue((store / PROFILE_FILENAME).exists())
        data = json.loads((store / PROFILE_FILENAME).read_text(encoding="utf-8"))
        self.assertIn("Кирилл Тестовский", data["facts"]["name"])


class TestPersistenceAndErrors(TempMemoryCase):
    def test_missing_files_are_ok(self):
        store = self.tmp / "fresh"  # каталога нет вообще
        mem = MemoryRetriever(memory_dir=store)
        self.assertEqual(mem.episodic.get_recent(5), [])
        summary = mem.profile.get_summary()
        self.assertIn("мало знаю", summary)

    def test_save_and_reload_roundtrip(self):
        store = self.tmp / "roundtrip"
        mem = MemoryRetriever(memory_dir=store)
        mem.profile.update_fact("role", "developer")
        mem.profile.add_interest("Unity")
        mem.episodic.add_episode("conversation", "hello", importance=2)

        mem2 = MemoryRetriever(memory_dir=store)
        self.assertEqual(mem2.profile.get_profile().facts["role"], "developer")
        self.assertIn("Unity", mem2.profile.get_profile().interests)
        recent = mem2.episodic.get_recent(5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["content"], "hello")

    def test_format_compatibility(self):
        """Форматы файлов не изменились: profile.json — обычный JSON с полями
        UserProfile; episodes — JSONL с timestamp/event_type/content."""
        store = self.tmp / "fmt"
        p = ProfileMemory(memory_dir=store)
        p.update_fact("k", "v")
        data = json.loads((store / PROFILE_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(
            set(data.keys()),
            {"user_id", "name", "preferences", "facts", "interests", "projects"},
        )
        e = EpisodicMemory(memory_dir=store)
        e.add_episode("task", "x")
        line = (store / EPISODES_FILENAME).read_text(encoding="utf-8").strip()
        rec = json.loads(line)
        self.assertEqual(
            set(rec.keys()),
            {"timestamp", "event_type", "content", "importance", "metadata"},
        )

    def test_corrupted_profile_json_not_silently_overwritten(self):
        store = self.tmp / "corrupt"
        store.mkdir()
        bad = store / PROFILE_FILENAME
        bad.write_text("{ это не json !!!", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            pm = ProfileMemory(memory_dir=store)
        self.assertIn("не удалось прочитать профиль", buf.getvalue())
        self.assertIsNotNone(pm._load_error)
        # инициализация НЕ перезаписала файл
        self.assertEqual(bad.read_text(encoding="utf-8"), "{ это не json !!!")

    def test_corrupted_episodes_lines_skipped_with_warning(self):
        store = self.tmp / "corrupt_ep"
        store.mkdir()
        f = store / EPISODES_FILENAME
        good = json.dumps({"timestamp": 1.0, "event_type": "t", "content": "ok",
                           "importance": 1, "metadata": {}}, ensure_ascii=False)
        f.write_text(good + "\n" + "@@@битая строка@@@\n" + good + "\n", encoding="utf-8")
        ep = EpisodicMemory(memory_dir=store)
        buf = io.StringIO()
        with redirect_stdout(buf):
            items = ep.get_recent(10)
        self.assertEqual(len(items), 2)
        self.assertIn("повреждённых строк", buf.getvalue())
        # второй вызов не дублирует предупреждение и не пишет файл
        before = f.read_text(encoding="utf-8")
        buf2 = io.StringIO()
        with redirect_stdout(buf2):
            ep.get_recent(10)
        self.assertEqual(buf2.getvalue(), "")
        self.assertEqual(f.read_text(encoding="utf-8"), before)

    def test_read_errors_do_not_duplicate_episodes(self):
        store = self.tmp / "nodup"
        ep = EpisodicMemory(memory_dir=store)
        ep.add_episode("conversation", "same", importance=1)
        # многократное чтение не создаёт новых записей
        for _ in range(5):
            ep.get_recent(10)
        lines = (store / EPISODES_FILENAME).read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)

    def test_write_errors_are_raised_not_swallowed(self):
        # blocked path: episodes-«каталог» мешает создать файл
        store = self.tmp / "blocked"
        store.mkdir()
        (store / EPISODES_FILENAME).mkdir()  # на месте файла — директория
        ep = EpisodicMemory(memory_dir=store)
        with self.assertRaises(OSError):
            ep.add_episode("task", "boom")

    def test_backward_compatible_storage_path_arg(self):
        """Старый публичный API storage_path продолжает работать."""
        custom = self.tmp / "legacy" / "myprofile.json"
        pm = ProfileMemory(storage_path=str(custom))
        pm.update_fact("legacy", True)
        self.assertTrue(custom.exists())
        reloaded = ProfileMemory(storage_path=str(custom))
        self.assertTrue(reloaded.get_profile().facts["legacy"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
