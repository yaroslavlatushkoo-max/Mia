from __future__ import annotations

import re
from typing import Optional

from .task_context import TaskContext, TaskMode, TaskDomain


# Confidence below this threshold for an actionable request means the
# Router must NOT guess: it routes to CLARIFY (migration To-do #3).
CLARIFY_THRESHOLD = 0.60

# Destructive/system-change markers without a clear target -> CLARIFY.
HIGH_RISK_MARKERS = (
    "очист", "очисти", "снес", "форматир", "перезагруз",
    "выключи", "закрой все",
)


class Router:
    """Deterministic intent router.

    Intents (migration To-do #3): FILE_LIST, FILE_READ, FILE_WRITE,
    DELETE_FILES, RUN_SHELL, SCREENSHOT, CLOSE_APPLICATION, WEB_SEARCH,
    OPEN_APPLICATION, CLARIFY, CANCEL — plus the conversational set.

    Design rules:
    - no guessing: ambiguous actionable requests become CLARIFY;
    - entities (app_name / path / query / url / command) are extracted
      deterministically from the raw text;
    - rule ordering resolves the collisions found in the Cursor analysis:
        'открой браузер'        -> OPEN_APPLICATION (browser is an app),
                                   never a web search
        'Открой Discord'        -> OPEN_APPLICATION (generic extraction,
                                   no hardcoded application names)
        'найди в интернете X'   -> WEB_SEARCH (explicit web marker only;
                                   bare 'найди файл' is not a web search)
        'удали файл temp.txt'   -> DELETE_FILES (never CONVERSATION)
        'запусти скрипт'        -> RUN_SHELL (never OPEN_APPLICATION)
        'прочитай main.py'      -> FILE_READ (read verb beats '.py' shell hint)
    """

    def __init__(self):
        self.greeting_patterns = [
            r"^привет[.!?, ]*$",
            r"^здравствуй\w*[.!?, ]*$",
            r"\bдобрый день\b",
            r"\bдобрый вечер\b",
            r"\bдоброе утро\b",
            r"^hi[.!?, ]*$",
            r"^hello[.!?, ]*$",
        ]

        self.farewell_patterns = [
            r"^пока[.!?, ]*$",
            r"\bдо свидания\b",
            r"\bспокойной ночи\b",
            r"^bye[.!?, ]*$",
        ]

        self.cancel_patterns = [
            r"^отмена\b", r"^отмени\b", r"\bотменить\b", r"\bcancel\b",
            r"передумал", r"не надо\b", r"не нужно\b", r"забудь запрос",
            r"^останови[сь]?\b", r"^прекрати\b",
        ]

        self.memory_patterns = [
            r"что ты помнишь",
            r"что ты знаешь обо мне",
            r"запомни",
            r"помнишь ли ты",
            r"мои предпочтения",
        ]

        self.user_fact_patterns = [
            r"меня зовут",
            r"моё имя",
            r"мое имя",
            r"я работаю",
            r"я учусь",
            r"я люблю",
            r"мне нравится",
            r"я хочу",
            r"я делаю",
            r"мой проект",
        ]

        # Explicit web-search markers. Bare 'найди' is NOT enough —
        # otherwise 'найди файл' would wrongly become a web search.
        self.web_search_markers = [
            r"в интернете", r"в интернети", r"онлайн", r"погугли",
            r"google", r"веб-?поиск", r"все?мирную сеть", r"в сети",
            r"документаци",
        ]
        self.web_search_verbs = [r"найди", r"найти", r"поищи", r"искать", r"search"]

        self.screenshot_patterns = [
            r"скриншот", r"screenshot", r"снимок экрана",
        ]

        self.delete_patterns = [
            r"удал", r"remove\b", r"delete\b", r"стереть файл",
        ]

        self.read_verbs = [
            r"прочит", r"покажи содержим", r"что внутри файла",
            r"открой файл", r"посмотри файл",
        ]

        self.write_verbs = [
            r"создай файл", r"создать файл", r"запиши", r"сохрани",
            r"напиши в файл", r"добавь в файл",
        ]

        self.list_patterns = [
            r"покажи файлы", r"список файлов", r"что в папке",
            r"какие файлы", r"\bls\b", r"\bdir\b",
            r"покажи (?:содержимое )?папку", r"просмотри папку",
            r"проверь папку",
        ]

        # Shell/system-execution markers. A file extension alone is NOT a
        # shell marker (main.py may be read/written); it counts only
        # together with an execution verb — see _is_shell_request().
        self.shell_patterns = [
            r"\bскрипт\w*\b",
            r"командн", r"терминал", r"консол",
            r"powershell", r"cmd\.exe",
            r"выполни\s+команд", r"запусти\s+команд",
        ]
        self.exec_verbs = [r"запуст", r"выполн", r"исполн", r"\brun\b", r"\bexec\b"]

        self.close_app_patterns = [
            r"закрой приложени\w*\s*(.*)",
            r"закрыть приложени\w*\s*(.*)",
            r"close app(?:lication)?\s*(.*)",
            r"убей процесс\s*(.*)",
            r"останови приложени\w*\s*(.*)",
        ]

        self.open_app_patterns = [
            r"открой\s+(.+)",
            r"запусти\s+(.+)",
            r"открыть\s+(.+)",
            r"\blaunch\s+(.+)",
        ]

        self.technical_patterns = [
            r"ошибк", r"баг", r"код", r"проект", r"unity", r"python",
            r"компиляц", r"исправь", r"проверь код", r"репозиторий",
        ]

    # ------------------------------------------------------------------
    def route(self, text: str, source: str = "text") -> TaskContext:
        normalized = text.strip().lower()
        ctx = TaskContext(raw_input=text, source=source)

        def fill(intent, mode, domain, complexity, confidence, entities=None):
            ctx.intent = intent
            ctx.mode = mode
            ctx.domain = domain
            ctx.complexity = complexity
            ctx.confidence = confidence
            if entities:
                ctx.entities.update(entities)
            return ctx

        # ---- conversational basics ------------------------------------
        if self._matches_any(normalized, self.greeting_patterns):
            return fill("GREETING", TaskMode.COMPANION, TaskDomain.CHARACTER, "C0", 0.95)

        if self._matches_any(normalized, self.farewell_patterns):
            return fill("FAREWELL", TaskMode.COMPANION, TaskDomain.CHARACTER, "C0", 0.95)

        # ---- CANCEL before any other actionable branch -----------------
        if self._matches_any(normalized, self.cancel_patterns):
            return fill("CANCEL", TaskMode.ASSISTANT, TaskDomain.GENERAL, "C0", 0.92)

        if self._matches_any(normalized, self.memory_patterns):
            return fill("MEMORY_QUERY", TaskMode.ASSISTANT, TaskDomain.MEMORY, "C1", 0.9)

        if self._matches_any(normalized, self.user_fact_patterns):
            return fill("USER_FACT", TaskMode.ASSISTANT, TaskDomain.MEMORY, "C1", 0.9)

        # ---- file / system operations ----------------------------------
        path = self._extract_path(normalized)

        if self._matches_any(normalized, self.screenshot_patterns):
            return fill(
                "SCREENSHOT", TaskMode.AGENT, TaskDomain.SYSTEM, "C3", 0.9,
                {"path": path} if path else None,
            )

        if self._matches_any(normalized, self.delete_patterns):
            # 'удали файл temp.txt' must NEVER fall through to CONVERSATION.
            conf = 0.9 if path else 0.75
            return fill("DELETE_FILES", TaskMode.AGENT, TaskDomain.FILES, "C3", conf,
                        {"path": path} if path else {})

        # Read/write verbs win over shell heuristics ('прочитай main.py').
        if self._matches_any(normalized, self.write_verbs) and path:
            content = self._extract_write_content(text)
            return fill("FILE_WRITE", TaskMode.AGENT, TaskDomain.FILES, "C3", 0.85,
                        {"path": path, "content": content})

        if self._matches_any(normalized, self.read_verbs):
            # 'открой файл X' / 'посмотри файл X': explicit file marker —
            # a file action even when the name has no known extension.
            if not path:
                m = re.search(r"(?:файл|файла|файли?к?)\s+([\w\-./\\]+\.[\w]+)", normalized)
                if m:
                    path = m.group(1)
            if path:
                return fill("FILE_READ", TaskMode.AGENT, TaskDomain.FILES, "C3", 0.88,
                            {"path": path})

        if self._is_shell_request(normalized):
            cmd = self._extract_shell_command(text)
            # Script/terminal execution is a shell action, not opening an app.
            conf = 0.88 if cmd else 0.7
            return fill("RUN_SHELL", TaskMode.AGENT, TaskDomain.SYSTEM, "C3", conf,
                        {"command": cmd} if cmd else {})

        if self._matches_any(normalized, self.list_patterns):
            list_path = path or self._extract_folder(normalized) or "."
            return fill("FILE_LIST", TaskMode.AGENT, TaskDomain.FILES, "C3", 0.85,
                        {"path": list_path})

        # ---- close application (checked before open patterns) ----------
        for p in self.close_app_patterns:
            m = re.search(p, normalized)
            if m:
                target = m.group(1).strip(" .,!?.")
                return fill("CLOSE_APPLICATION", TaskMode.AGENT, TaskDomain.SYSTEM, "C3",
                            0.85 if target else 0.7,
                            {"app_name": target} if target else {})

        # ---- web search (explicit web markers only) --------------------
        if self._is_web_search(normalized):
            query = self._extract_search_query(text)
            conf = 0.85 if query else 0.6
            ent = {}
            if query:
                ent["query"] = query
            url = self._extract_url(text)
            if url:
                ent["url"] = url
            return fill("WEB_SEARCH", TaskMode.AGENT, TaskDomain.WEB, "C3", conf, ent)

        # ---- open application (generic, no app-name hardcode) ----------
        app_name = self._extract_open_app_name(normalized)
        if app_name:
            # Collision guard: 'открой файл X' / 'открой папку X' are file
            # actions, not launching an application.
            if re.match(r"^(файл|папк|директор|каталог|document|folder)\b", app_name):
                if path:
                    return fill("FILE_READ", TaskMode.AGENT, TaskDomain.FILES, "C3", 0.8,
                                {"path": path})
                return fill("FILE_LIST", TaskMode.AGENT, TaskDomain.FILES, "C3", 0.75,
                            {"path": self._extract_folder(normalized) or "."})
            return fill("OPEN_APPLICATION", TaskMode.AGENT, TaskDomain.SYSTEM, "C3", 0.88,
                        {"app_name": app_name})

        # ---- destructive wording without a concrete target ------------
        if any(m in normalized for m in HIGH_RISK_MARKERS):
            # Do not guess what exactly to destroy: ask first. Policy still
            # blocks anything risky until confirmed.
            return fill("CLARIFY", TaskMode.ASSISTANT, TaskDomain.SYSTEM, "C1", 0.4,
                        {"clarify_reason": "unclear destructive target"})

        # ---- technical discussion --------------------------------------
        if self._matches_any(normalized, self.technical_patterns):
            # Questions about Mia herself are conversation, not tech tasks:
            # 'ошибк'/'код' appear in personality chatter too.
            if re.search(r"\bты\b|\bтебя\b|\bу тебя\b", normalized) and \
                    not re.search(r"\b(?:проект|репозиторий|компиляц|исправь)\w*\b", normalized):
                return fill("CONVERSATION", TaskMode.COMPANION, TaskDomain.CHARACTER, "C0", 0.7)
            return fill("TECHNICAL_TASK", TaskMode.AGENT, TaskDomain.TECHNICAL, "C4", 0.75)

        # ---- ambiguous imperative -> CLARIFY (no guessing) -------------
        if self._looks_actionable_but_uncertain(normalized):
            return fill("CLARIFY", TaskMode.ASSISTANT, TaskDomain.GENERAL, "C1", 0.4,
                        {"clarify_reason": "ambiguous request"})

        # ---- plain conversation ----------------------------------------
        if len(normalized) < 25:
            return fill("CONVERSATION", TaskMode.COMPANION, TaskDomain.GENERAL, "C0", 0.7)

        return fill("GENERAL_QUERY", TaskMode.ASSISTANT, TaskDomain.GENERAL, "C1", 0.65)

    # ------------------------------------------------------------------
    # Deterministic helpers
    # ------------------------------------------------------------------
    def _matches_any(self, text: str, patterns) -> bool:
        return any(re.search(p, text) for p in patterns)

    def _is_web_search(self, text: str) -> bool:
        has_verb = self._matches_any(text, self.web_search_verbs)
        has_marker = self._matches_any(text, self.web_search_markers)
        return bool(has_marker and (has_verb or "погугли" in text))

    def _is_shell_request(self, text: str) -> bool:
        """Shell/execution intent: explicit shell markers, or an execution
        verb combined with a script-like file target ('запусти script.py')."""
        if self._matches_any(text, self.shell_patterns):
            return True
        if self._matches_any(text, self.exec_verbs) and \
                re.search(r"\.(bat|sh|ps1|py|exe|cmd)\b", text):
            return True
        return False

    def _extract_open_app_name(self, text: str) -> Optional[str]:
        for pattern in self.open_app_patterns:
            m = re.search(pattern, text)
            if m:
                target = m.group(1).strip(" .,!?.")
                if target:
                    return target
        return None

    _EXT_RE = (r"\b([\w\-./\\]+\.(?:txt|md|py|json|csv|log|html|xml|ya?ml|ini|cfg|"
               r"bat|sh|ps1|docx?|xlsx?|png|jpe?g|pdf))\b")

    def _extract_path(self, text: str) -> Optional[str]:
        m = re.search(self._EXT_RE, text)
        if m:
            return m.group(1)
        m = re.search(r"(?:[a-z]:[\\/][\w\-.\\/]+|/(?:[\w\-.]+/){1,}[\w\-.]+|\.{1,2}/[\w\-.]+)", text)
        if m:
            return m.group(0)
        return None

    def _extract_folder(self, text: str) -> Optional[str]:
        # 1) Явный путь (абсолютный POSIX/Windows или относительный с /):
        #    'в папке /nonexistent_dir_zzz_42', 'в C:/Users/me/Documents'.
        m = re.search(
            r"(?:в|из)\s+(?:папке|папку|каталоге|директории)\s+"
            r"([~.]?/?[\w.\-]+(?:/[^\s\"'«»,.!?;:]+)*|[a-zA-Z]:[\\/][^\s\"'«»,.!?;:]+)",
            text,
        )
        if m:
            return m.group(1).rstrip("\\/.")
        # 1b) Windows-путь с обратными слэшами: 'в папке C:\Users\me\Docs'.
        #     Предыдущий шаблон съедал только диск ('C') — дефект B14.
        m = re.search(
            r"(?:в|из)\s+(?:папке|папку|каталоге|директории)\s+"
            r"([a-zA-Z]:\\[^\s\"'«»]+)",
            text,
        )
        if m:
            return m.group(1).rstrip("\\/")
        # 2) Просто имя папки без слэшей ('в папке docs').
        m = re.search(r"(?:в|из)\s+(?:папке|папку|каталоге|директории)\s+([\w\-.]+)", text)
        if m:
            return m.group(1)
        return None

    def _extract_search_query(self, raw_text: str) -> Optional[str]:
        t = raw_text.lower()
        m = re.search(
            r"(?:найди|найти|поищи|искать|погугли|search)\s+"
            r"(?:в\s+интернете\s+|в\s+сети\s+|информацию\s+(?:о|об|про)\s+)?"
            r"(.+?)\s*(?:документаци\w*|documentation)\s*$",
            t,
        )
        if not m:
            # No documentation suffix: take everything after the trigger.
            m = re.search(
                r"(?:найди|найти|поищи|искать|погугли|search)\s+"
                r"(?:в\s+интернете\s+|в\s+сети\s+|информацию\s+(?:о|об|про)\s+)?"
                r"(.+)$",
                t,
            )
        if not m:
            return None
        q = m.group(1).strip(" .,!??")
        q = re.sub(r"^(информацию|about|про|о|об)\s+", "", q).strip()
        if not q or q in ("интернет", "internet"):
            return None
        return q

    def _extract_url(self, raw_text: str) -> Optional[str]:
        m = re.search(r"https?://\S+", raw_text)
        return m.group(0) if m else None

    def _extract_shell_command(self, raw_text: str) -> Optional[str]:
        m = re.search(
            r"(?:выполни|запусти|run|exec)\s+(?:команду[:\s]*)?[`\"']?(.+?)[`\"']?$",
            raw_text.strip(), flags=re.IGNORECASE,
        )
        if m:
            return m.group(1).strip(" .,!??`\"'")
        return None

    def _extract_write_content(self, raw_text: str) -> str:
        m = re.search(r"[«\"'](.+?)[»\"']", raw_text)
        if m:
            return m.group(1)
        return ""

    def _looks_actionable_but_uncertain(self, text: str) -> bool:
        # Bare imperative verbs aimed at Mia without any recognised object:
        # the request is actionable but underspecified -> ask, don't guess.
        if re.search(r"^(сделай|выполни|собери|подготовь|организируй)\b", text):
            return True
        return False
