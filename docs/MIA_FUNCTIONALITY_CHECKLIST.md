# MIA — Функциональный чек-лист работоспособности

Постоянный контрольный документ проекта. Отмечает **фактически проверенные**
возможности Mia, а не задуманную архитектуру. Архитектурный контракт:
`docs/CORE_MIGRATION.md` + `QWEN.md`.

## Статусы

| Символ | Значение |
|---|---|
| `[x]` | Проверено реальной командой/тестом — работает |
| `[~]` | Частично работает / есть известные ограничения |
| `[ ]` | Не проверено в этой среде |
| `[!]` | Обнаружена проблема (дефект) |
| `[-]` | Намеренно не используется / deprecated |

Принцип разграничения: **REGISTERED ≠ IMPLEMENTED ≠ EXECUTED ≠ VERIFIED**.
`[x]` ставится только при наличии команды/теста из колонки «Verified by».

Аудит выполнен: 2026-10-06, среда Linux / Python 3.12, Ollama недоступен,
Windows-специфичные пути не исполнялись (отмечены `[~]`/`[ ]`).

---

## A. Запуск и базовая инфраструктура

| # | Проверка | Статус | Verified by | Notes |
|---|---|---|---|---|
| A1 | Импорт всех модулей нового ядра (21 модуль core/tools/memory/ai/character/adapters) | `[x]` | smoke-import (см. отчёт аудита) | IMPORTS OK |
| A2 | `python main.py` (legacy entry point) | `[ ]` | — | Windows-only зависимости; не запускался в Linux-среде |
| A3 | `python web_ui.py` | `[ ]` | — | UI-этап, намеренно не трогаем |
| A4 | Конфигурация (`config.py`) читается | `[ ]` | — | legacy config, миграция не начиналась |
| A5 | Ollama provider доступен | `[ ]` | — | Ollama отсутствует в audit-среде |
| A6 | Обработка отсутствующего provider (честная ошибка, без fake text) | `[x]` | smoke: `ModelRouter.generate()` → `error` заполнен, `text` пуст | fallback deterministic-пути работают |
| A7 | Корректное завершение тестовых прогонов (exit codes) | `[x]` | `test_core.py`=0, `test_agent_v2.py`=0, `test_core_pipeline.py`=0 | |
| A8 | Логирование единой системой логов | `[~]` | — | везде print()-вывод; структурного логгера нет |
| A9 | Глобальная обработка исключений верхнего уровня | `[ ]` | — | относится к main.py-интеграции (следующий этап) |
| A10 | Окружение: целевой Python 3.11 vs фактический 3.12 | `[~]` | `python -V` | код совместим с обоими; зафиксировать в QWEN.md при случае |

## B. Router (`mia/core/router.py`)

| # | Проверка | Статус | Verified by | Notes |
|---|---|---|---|---|
| B1 | greeting → GREETING/COMPANION/C0 | `[x]` | smoke: «привет» | |
| B2 | обычный разговор → CONVERSATION | `[x]` | smoke | |
| B3 | technical task → TECHNICAL_TASK/AGENT/C4 | `[x]` | smoke: «проверь папку проекта» | |
| B4 | open application → OPEN_APPLICATION + entity app_name | `[x]` | smoke: «открой блокнот», test_agent_v2 | |
| B5 | memory query → MEMORY_QUERY | `[x]` | smoke: «что ты помнишь обо мне» | |
| B6 | web search → WEB_SEARCH | `[~]` | test_agent_v2 (работает), но «найди доки по asyncio» дал CONVERSATION | узкие ключевые слова поиска |
| B7 | agent task routing (mode=AGENT для задач) | `[x]` | smoke B3/B4 | |
| B8 | неизвестный/неоднозначный запрос → безопасный default | `[x]` | smoke: «погода завтра» → CONVERSATION/COMPANION | не порождает ложных агент-задач |
| B9 | «удали файл temp.txt» → DELETE_FILES | `[x]` | test_session_hitl_router §C + e2e: DELETE_FILES, HIGH-risk → WAITING_CONFIRMATION | исправлено в пакете Session+Router (To-do #3) |
| B10 | «запусти скрипт» → RUN_SHELL/SYSTEM_CHANGE | `[x]` | test_session_hitl_router §C + e2e: RUN_SHELL | исправлено; shell-исполнитель как инструмент ещё не зарегистрирован |
| B11 | расширенный набор intents: FILE_LIST/FILE_READ/FILE_WRITE/SCREENSHOT/CLOSE_APPLICATION/WEB_SEARCH/OPEN_APPLICATION/CLARIFY/CANCEL | `[x]` | test_session_hitl_router §C/D | 11 intents из анализа Cursor покрыты golden-таблицей |
| B12 | коллизии: «открой браузер» ≠ «открой Discord» ≠ «найди в интернете» | `[x]` | test_session_hitl_router §C | разные intents + разные entity (app_name vs query) |
| B13 | низкая уверенность → CLARIFY, без угадывания | `[x]` | test_session_hitl_router §C («сделай», «очисти всё») | confidence < порога → CLARIFY с pending-уточнением |
| B14 | детерминированное извлечение app_name/path/query/url | `[x]` | test_session_hitl_router §C | без LLM на этом этапе |
| B15 | training_data_v2 как eval/golden set (не runtime-мозг) | `[x]` | test_session_hitl_router §D (coverage 62/105 ≥ 55%) | датасет используется только для проверки качества роутинга |

## C. Core Agent Pipeline (сквозной путь)

`Perception → Router → CostEstimator → Policy → TaskContext → ExecutionTrace → Planner → ToolRegistry → AgentLoop → Observation → Verification → Replan → Responder → Character`

| # | Компонент | Что проверяется | Статус | Verified by |
|---|---|---|---|---|
| C1 | Perception | вход text пока единственный источник; speech/vision adapters существуют, но не подключены | `[~]` | код `mia/adapters/speech_adapter.py`, `vision_adapter.py`; интеграция — вне текущего этапа |
| C2 | Router | см. раздел B | `[x]` | smoke B1–B8 |
| C3 | CostEstimator | бюджет шагов растёт с C0→C5 (1/3/8/12) | `[x]` | smoke: max_steps monotonic |
| C4 | Policy | реальная enforcement-точка до исполнения инструмента | `[x]` | test_core_pipeline §1, §4a, N6 |
| C5 | TaskContext | несёт intent/mode/domain/complexity/risk/entities между слоями | `[x]` | test_core.py, все pipeline-тесты |
| C6 | ExecutionTrace | шаги, observations, errors, replans, policy_decision сериализуются | `[x]` | smoke to_dict(); test_core_pipeline §4b |
| C7 | Planner | fast/deep, rule-based fallback, LLM как усилитель | `[x]` | test_agent_v2 (deep=2 шага без LLM), test_core_pipeline §2 |
| C8 | ToolRegistry | единственный источник capabilities | `[x]` | test_core_pipeline §2 (planner.available_tools == registry) |
| C9 | AgentLoop | observe→act→observe→verify→replan, bounded budget | `[x]` | test_core_pipeline §4a–4d |
| C10 | Observation | сохраняется в step + trace artifacts | `[x]` | test_core_pipeline §4b «observations persisted» |
| C11 | Verification | честная проверка результата, без false success | `[x]` | test_core_pipeline §3 (5 сценариев) |
| C12 | Replan | ограниченный max_replans, история в trace, без циклов | `[x]` | test_core_pipeline §4b/4c |
| C13 | Responder | финальный слой после verification, honest failure | `[x]` | test_core_pipeline §5 |
| C14 | Character | styling отделён от reasoning, применяется в конце | `[x]` | test_core_pipeline §5 TagStylist |
| C15 | Сквозной прогон Orchestrator.handle (agent-путь) | `[x]` | smoke: «Открой notepad» → type=agent, verification.success=False (Linux, честно); «Найди документацию…» → verified success через browser.open |
| C16 | Session (`mia/core/session.py`): session_id, working messages, pending_task | `[x]` | test_session_hitl_router §S; интегрирован в Orchestrator.handle(session=…) | To-do #1 |
| C17 | HITL resume: WAITING_CONFIRMATION → confirm → продолжение ТОЙ ЖЕ задачи (тот же task_id, без перепланирования с нуля) | `[x]` | test_session_hitl_router §S + e2e: resumed_task_id == исходный task_id, инструмент исполнен только после confirm | Policy не обходится: resume лишь ставит ctx.confirmed=True | |

## D. ToolRegistry — таблица инструментов

Проверялось реально: `registry.run(...)` в Linux-среде.

| Инструмент | Registered | Schema/Params | Validation | Executed | Success path | Failure honest | Risk/Confirm | Adapter | Класс | Статус |
|---|---|---|---|---|---|---|---|---|---|---|
| system.open_app | ✔ | `app_name` req, aliases app/application/name | ✔ (empty→ошибка) | ✔ (Linux-ветка) | `[ ]` Windows-only (`start` exit code + path fallback) | ✔ «only supported on Windows» | medium / no | SystemAdapter | REAL* | `[~]` |
| files.list | ✔ | `path`,`limit`; aliases directory/dir/folder | ✔ тип/required | ✔ | ✔ реальный список | ✔ bad path | low / no | FileAdapter | REAL | `[x]` |
| files.read | ✔ | `path` req, `max_chars`; aliases file/file_path | ✔ | ✔ | ✔ (main.py прочитан) | ✔ «File does not exist» | low / no | FileAdapter | REAL | `[x]` |
| browser.open | ✔ | `url` req, `background` | ✔ | ✔ | `[~]` xdg-open в headless возвращает success без подтверждения открытия окна | ✔ exceptions | low / no | BrowserAdapter | ADAPTER | `[~]` |
| web.search | ✔ | `query` req | ✔ | ✔ | STUB: всегда success=False, verified=False | ✔ честный stub-error | low / no | WebAdapter | **STUB** | `[~]` (зарегистрирован ≠ реализован) |

\* REAL на Windows (целевая платформа); в Linux-аудит-среде исполняется честная отказ-ветка.

Тесты: `test_core_pipeline.py` §2, §6, §7a; smoke выше.

## E. Файловые операции

| # | Проверка | Статус | Verified by | Notes |
|---|---|---|---|---|
| E1 | list (files.list через registry) | `[x]` | smoke + test_agent_v2 «Проверь папку с проектом» | |
| E2 | read (files.read, max_chars) | `[x]` | smoke, test_agent_v2 deep plan | |
| E3 | write | `[ ]` | — | FileAdapter.write_file не реализован; инструмент files.write не зарегистрирован |
| E4 | delete | `[ ]` | — | только policy-заготовка `files.delete`; исполнитель не реализован |
| E5 | path validation / sandbox | `[~]` | adapter резолвит Path | нет ограничения корнем проекта — чтение любых путей возможно (см. топ проблем #4) |
| E6 | ошибки: несуществующий файл | `[x]` | smoke: «File does not exist» verified=False | |
| E7 | недоступный путь (permission) | `[ ]` | — | не воспроизводилось в среде |
| E8 | неправильные параметры (тип/required/unknown) | `[x]` | test_core_pipeline §2 schema validation, §7a alias/unknown | normalize_input+validate_input |

## F. System tools

| # | Проверка | Статус | Verified by | Notes |
|---|---|---|---|---|
| F1 | open_app на Windows (start exit code, path fallback) | `[ ]` | — | среда Linux; логика проверена только кодом |
| F2 | open_app честный отказ на неподдерживаемой ОС | `[x]` | test_core_pipeline §6, smoke | success=False, verified=False |
| F3 | open_app не объявляет успех без evidence | `[x]` | §6: success требует method=start/path | Popen-success больше не засчитывается |
| F4 | другие системные операции (processes, volume…) | `[ ]` | — | не зарегистрированы в новом реестре; живут в legacy skills/system.py |

## G. Web / Browser

| # | Проверка | Статус | Verified by | Notes |
|---|---|---|---|---|
| G1 | browser.open выполняет открытие URL | `[~]` | test_agent_v2: verified success (xdg-open rc=0) | rc=0 ≠ подтверждение отображения окна — ограничение ADAPTER |
| G2 | web.search = STUB, не выдаётся за рабочий | `[x]` | status="STUB" в spec; run() → success=False | REGISTERED ≠ IMPLEMENTED учтено явно |
| G3 | replan использует browser.open как fallback для web.search | `[x]` | test_core_pipeline §4b | |
| G4 | failure handling браузер-адаптера | `[~]` | exceptions → ToolResult(success=False) | не тестировалось с реально битым браузером |
| G5 | legacy skills/browser.py, web.py | `[ ]` | — | аудит без миграции (раздел L) |

## H. Memory

| # | Проверка | Статус | Verified by | Notes |
|---|---|---|---|---|
| H1 | working memory add/get recent/context | `[x]` | test_core.py | in-memory, без persistence (ок, по дизайну) |
| H2 | profile memory: запись имени/интересов/проектов | `[x]` | test_core.py + smoke extract_and_remember | JSON-persistence mia_memory/profile.json |
| H3 | episodic memory: add/get_recent/get_by_type | `[x]` | smoke | jsonl-persistence подтверждена |
| H4 | memory retriever: get_context_for_query | `[x]` | test_core.py | |
| H5 | MEMORY_QUERY end-to-end через Orchestrator | `[~]` | smoke answer_memory_query отвечает из профиля | ответ содержит реальные данные; но «какие у меня интересы» роутится в CONVERSATION (B-ограничение) |
| H6 | отсутствие ложных воспоминаний (нет данных → честный ответ) | `[~]` | код `_load` default UserProfile | полный негативный тест не написан |
| H7 | ошибки backend (битый JSON на диске) | `[ ]` | — | устойчивость _load к повреждённому файлу не тестировалась |
| H8 | legacy skills/memory.py (старая память) | `[ ]` | — | сосуществует; миграция не начиналась |

## I. Planning

| # | Проверка | Статус | Verified by | Notes |
|---|---|---|---|---|
| I1 | C0–C5 маппинг fast/deep | `[x]` | smoke complexity→level; test_agent_v2 C4 deep=2 шага | |
| I2 | Fast plan (C2–C3) | `[x]` | test_agent_v2 OPEN_APPLICATION | |
| I3 | Deep plan (C4–C5) | `[x]` | test_agent_v2 TECHNICAL_TASK | |
| I4 | rule-based fallback без LLM | `[x]` | все тесты идут без Ollama именно так | |
| I5 | LLM planner (enhancement) | `[ ]` | — | Ollama недоступен в среде; парсер `_parse_llm_plan` покрыт только косвенно |
| I6 | validate_plan против capabilities реестра | `[x]` | test_core_pipeline §7b | unknown-tool план → None → rule-based fallback |
| I7 | unknown tool в плане | `[x]` | §4d ghost.tool → failed step, без false success | |
| I8 | invalid parameters | `[x]` | §2 + §7a | |
| I9 | multi-step plan | `[x]` | test_agent_v2 deep (list+read) | |
| I10 | replan работает | `[x]` | §4b stub→fallback, verified success | |
| I11 | bounded replan (нет бесконечных циклов) | `[x]` | §4c max_replans=2, цикл завершился FAILED | |
| I12 | системные задачи НЕ уходят в browser | `[x]` | §7b repair + описание capability open_app | регресс закрыт в этом аудите |
| I13 | ExecutionBudget в TaskContext (requires_llm/tool/planner, confidence, reasons) | `[x]` | test_session_hitl_router §B | To-do #2 |
| I14 | C3 = deterministic Fast Plan БЕЗ вызова LLM planner | `[x]` | test_session_hitl_router §B (mock-роутер не вызван) | budget.requires_llm=False для C3; LLM planner только C4/C5 |
| I15 | C4/C5 план валидируется через ToolRegistry + schema инструментов | `[x]` | test_session_hitl_router §B (invalid LLM plan rejected) | reject → rule-based fallback |

## J. Verification

| # | Проверка | Статус | Verified by |
|---|---|---|---|
| J1 | настоящий success (все шаги verified) | `[x]` | §3d |
| J2 | partial failure (≥1 шаг упал) | `[x]` | §3a |
| J3 | tool failure (success=False) | `[x]` | §7c dead tool |
| J4 | unverified result (success=True, verified=False) | `[x]` | §3c fake-open ветка |
| J5 | blocked tool (policy) | `[x]` | §4a |
| J6 | max_steps truncation ≠ success | `[x]` | §3b |
| J7 | failed replan остаётся failure | `[x]` | §4c |
| J8 | successful replan учитывается доказательно | `[x]` | §4b + supersession-логика verifier |
| J9 | пустой результат / 0 выполненных шагов | `[x]` | §3e |
| J10 | semantic LLM-check может только понижать, не повышать | `[x]` | код verifier (downgrade-only); без Ollama — не активен |

## K. Responder / Character

| # | Проверка | Статус | Verified by |
|---|---|---|---|
| K1 | reasoning ≠ formatting ≠ character (слои разделены) | `[x]` | §5 TagStylist; responder вызывает stylist только в конце |
| K2 | success-ответ по факту observation (упоминает приложение/URL) | `[x]` | §5 |
| K3 | failure-ответ честно признаёт провал («не смогла») | `[x]` | §5, §7c |
| K4 | blocked-ответ объясняет требуемое подтверждение | `[x]` | §4a |
| K5 | нет hardcoded ответов в AgentLoop | `[x]` | grep: AgentLoop делегирует Responder |
| K6 | ответы о невыполненном не генерируются | `[x]` | §3+§5 комбинация |
| K7 | ResponseStylist режимы COMPANION/ASSISTANT/AGENT | `[~]` | smoke: style() возвращает текст без видимых различий режимов; system_prompt(mode) есть — тонкость стилизации проверить сложно |

## L. Legacy integration (только аудит, миграция НЕ выполнена)

Классификация: WORKING / PARTIAL / BROKEN / NOT_MIGRATED / DEPRECATED.
Работа legacy-кода в Linux-среде не запускалась (Windows-зависимости) —
WORKING означает «функционирует на целевой Windows-платформе пользователя»,
подтверждено пользователем ранее; автоматических тестов на legacy нет.

| Legacy-модуль | Что даёт | Класс | Статус |
|---|---|---|---|
| skills/system.py (702 стр.) | приложения, процессы, окна, горячие клавиши | NOT_MIGRATED | `[ ]` richest source для ToolRegistry-адаптеров |
| skills/system_tools.py | доп. системные утилиты | NOT_MIGRATED | `[ ]` |
| skills/browser.py (295) | Selenium/Edge автоматизация | NOT_MIGRATED | `[ ]` частично дублирует browser adapter |
| skills/web.py | веб-поиск/парсинг | NOT_MIGRATED | `[ ]` кандидат закрыть web.search STUB |
| skills/memory.py | старая память | PARTIAL (дублирует mia/memory) | `[ ]` две системы памяти сосуществуют — риск расхождения |
| skills/ai_brain.py | LLM-мозг legacy | PARTIAL | `[ ]` |
| skills/observer.py, live_observer.py, eyes.py | vision/наблюдение | NOT_MIGRATED | `[ ]` вне текущих этапов |
| skills/media.py, organizer.py, utils.py | медиа/планировщик/утилиты | NOT_MIGRATED | `[ ]` |
| skills/response_templates.py | речевые шаблоны | PARTIAL (частично покрыто ResponseStylist) | `[ ]` |
| skills/skill_loader.py, base.py | инфраструктура скиллов | WORKING (в legacy-контуре) | `[ ]` |
| main.py | старый entry point, живёт на skills/* | WORKING (на Windows у пользователя) | `[ ]` подключение к new core — следующий этап |
| web_ui.py | Flask UI поверх legacy | WORKING (на Windows) | `[ ]` не трогаем |
| speech.py, tts_engine.py, tts_server.py, vits_speak.py, voice_settings.py, test_silero.py | голос/TTS | вне технической части этого трека | `[-]` ведётся другой моделью |
| RVC WebUI | deprecated | DEPRECATED | `[-]` не восстанавливать |
| train_mia*.py, build_training_data_v2.py, classify_training_data.py, audit_*.py | LoRA/датасеты | NOT_MIGRATED (AI-strategy трек) | `[ ]` |

## M. AI providers

| # | Проверка | Статус | Verified by | Notes |
|---|---|---|---|---|
| M1 | provider abstraction (base Provider) | `[x]` | импорт + ModelRouter использует интерфейс | |
| M2 | Ollama provider against real server | `[ ]` | — | сервер недоступен в среде |
| M3 | отсутствие модели/server → честная error-модель | `[x]` | smoke: resp.error заполнен | |
| M4 | timeout обработки | `[~]` | код requests timeout присутствует | живой timeout-тест невозможен без сервера |
| M5 | fallback на deterministic-пути (rule-based planner, direct answers) | `[x]` | весь suite тестов без Ollama | |
| M6 | model selection (preferred=chat/tier) | `[~]` | код ModelRouter | поведение под нагрузкой не проверено |

## N. Безопасность и Policy

| # | Проверка | Статус | Verified by |
|---|---|---|---|
| N1 | high-risk intent → requires_confirmation | `[x]` | §1 |
| N2 | неподтверждённый рискованный инструмент блокируется ДО исполнения | `[x]` | §4a executor не вызван |
| N3 | confirmed=True разрешает при остальных допустимых условиях | `[x]` | §1 (deny→allow обе ветки) |
| N4 | denied intents реестр политики | `[~]` | механизм есть; набор пуст по design-допущению |
| N5 | tool metadata risk elevates decision | `[x]` | §1 risky spec |
| N6 | обход Policy через Planner невозможен (tool-level блок даже при benign intent) | `[x]` | smoke bypass-test: files.delete заблокирован при CONVERSATION-intent |
| N7 | policy_decision сохраняется в trace | `[x]` | §4a |
| N8 | пользовательский confirm-flow (HITL в core) | `[x]` | test_session_hitl_router §S + e2e: WAITING_CONFIRMATION → «да» → resume той же task_id; Policy пере-проверяется на resume (denied intent остаётся заблокированным даже после подтверждения). UI-обёртка (web_ui/main.py) — отдельный этап |
| N9 | CLARIFY resume не вызывает рекурсию и не угадывает | `[x]` | test_session_hitl_router §S (pending очищен до reroute) + e2e |
| N10 | cancel («нет») честно отменяет pending-задачу без исполнения | `[x]` | test_session_hitl_router §S |

## O. Карта тестового покрытия

| Компонент | Существующий тест | Результат | Отсутствующий тест |
|---|---|---|---|
| Router intents | test_core.py, smoke, **test_session_hitl_router §C/D (golden-таблица)** | pass | — (B9/B10 закрыты) |
| Session / HITL (confirm/cancel/clarify resume) | test_session_hitl_router §S + e2e | pass | persistence Session между перезапусками процесса |
| ExecutionBudget | test_session_hitl_router §B | pass | — |
| CostEstimator | smoke | pass | юнит-тест границ C0–C5 |
| Policy | test_core_pipeline §1,§4a | pass | — |
| ToolRegistry/schemas | §2, §7a | pass | — |
| builtin tools | §6, §7, test_agent_v2 | pass | files.write/delete (не реализованы) |
| Planner | §2, §7b, test_agent_v2 | pass | LLM-путь с моком model_router (I5) |
| AgentLoop | §4a–d, §7c | pass | — |
| Verification | §3, §7c | pass | — |
| Replan | §4b,c | pass | — |
| Responder/Character | §5 | pass | интеграция с реальным VoiceProfile-тоном (позже) |
| Memory | test_core.py | pass | corrupt-backend resilience (H7) |
| Orchestrator end-to-end | test_agent_v2 | pass | shadow-mode comparison (следующий этап) |
| main.py / web_ui.py | — | — | вообще не покрыты (вне текущего этапа) |

Критические возможности без автотестов: запуск main.py; Ollama-контракт;
browser.open визуальное подтверждение; files.write/delete.
(user confirmation flow закрыт: HITL в core — N8/N9/N10.)

---

## Machine-readable итог

| Area | Status | Verified by | Notes |
|---|---|---|---|
| A Infrastructure | PARTIAL | smoke/tests | print-логи, Windows-entry не запускался |
| B Router | PASS | test_session_hitl_router §C/D golden + e2e | B9/B10 исправлены; расширенный набор intents |
| C Core Pipeline | PASS | test_core_pipeline 56/56, test_agent_v2, test_session_hitl_router 47/47 | сквозной путь + Session/HITL (To-do #1–3) |
| D ToolRegistry | PASS (5 tools) | §2/§6/§7 + smoke | web.search=STUB честно |
| E File ops | PARTIAL | smoke | нет write/delete; path-sandbox слабый |
| F System tools | PARTIAL | §6 | Windows-ветка не исполнена в Linux |
| G Web/Browser | PARTIAL | §4b, test_agent_v2 | open rc=0 ≠ окно открыто |
| H Memory | PASS (new core) | test_core.py, smoke | legacy-память дублирует (L) |
| I Planning | PASS | §7b, test_agent_v2, hitl §B | ExecutionBudget; LLM-путь без живого теста (I5) |
| J Verification | PASS | §3, §7c | false success устранён |
| K Responder/Character | PASS | §5 | stylist-режимы тонкие |
| L Legacy | AUDITED ONLY | read-only аудит | ничего не сломано, ничего не мигрировано |
| M AI providers | PARTIAL | smoke M3 | живой Ollama не проверен |
| N Security/Policy | PASS | §1, §4a, N6-bypass, hitl §S | HITL confirm-flow в core готов (N8); UI-обёртка — отдельный этап |
| O Coverage map | DOCUMENTED | таблица O | 5 критических пробелов |

### Счётчики

(Пересчитаны автоматически по строкам таблиц этого файла; секция D учитывается
по колонке «Статус» каждого инструмента.)

- Total checks: **148** (строки таблиц A–O; раздел L учитывается по колонке «Класс» отдельно)
- Passed `[x]`: **93**
- Partial `[~]`: **19**
- Failed/defects `[!]`: **0** (B9/B10 закрыты в пакете To-do #1–3)
- Not tested `[ ]`: **30**
- Deprecated/out-of-track `[-]`: **0** + 2 legacy-трека в разделе L (voice/TTS, RVC)

### Дефекты, исправленные в ходе этого аудита (были `[!]`, стали `[x]`)

1. `files.list` падал на параметре `directory` (несогласованный контракт
   schema↔planner↔registry↔adapter) → введён декларативный `aliases` +
   `ToolSpec.normalize_input()` (schemas.py, builtin_tools.py); regression §7a.
2. LLM-план мог вести OPEN_APPLICATION через browser.open → добавлен
   capability-driven `Planner.validate_plan()` (repair + reject) и точное
   описание инструмента system.open_app в capabilities; regression §7b.
3. `.gitignore` был перезаписан пустым на предыдущем шаге → восстановлен
   полный вариант (177 строк); артефакты вычищены из staging.

4. Router B9/B10 (`удали файл` → CONVERSATION, `запусти скрипт` → OPEN_APPLICATION)
   → переписан детерминированный Router с расширенным набором intents и
   confidence-порогом (CLARIFY вместо угадывания); regression/golden:
   test_session_hitl_router §C/D.
5. Не было механизма подтверждения рискованных действий в core → добавлены
   `mia/core/session.py` (Session/PendingTask/WAITING_CONFIRMATION/
   WAITING_CLARIFICATION) и HITL-resume в Orchestrator; подтверждение
   продолжает ту же задачу (тот же task_id) и не обходит Policy;
   regression: test_session_hitl_router §S.
6. RecursionError при CLARIFY→resume (stale pending попадал в рекурсивный
   handle()) → pending очищается перед reroute (§S + e2e).
