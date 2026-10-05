from __future__ import annotations

"""Responder — final response layer (docs/CORE_MIGRATION.md §8).

Converts execution result + verification + relevant context into the
final user-facing answer. It runs strictly AFTER AgentLoop and
Verification; it does not execute tools, verify success or decide
safety. Character styling is applied through ResponseStylist only.
"""

from typing import Any, Dict, Optional

from .task_context import TaskContext


class Responder:
    def __init__(self, stylist=None):
        # ResponseStylist instance (character layer). Optional so that
        # the responder remains testable without a character module.
        self.stylist = stylist

    # ------------------------------------------------------------------
    def respond(
        self,
        ctx: TaskContext,
        trace,
        plan: Optional[Any] = None,
        verification: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the honest final answer for an agent-path task."""
        status = getattr(getattr(trace, "status", None), "value", "")
        steps = list(getattr(trace, "steps", []) or [])
        errors = list(getattr(trace, "errors", []) or [])

        verified_success = bool(verification and verification.get("success"))

        # Policy blocked execution before any tool ran.
        blocked = [s for s in steps if s.status == "blocked"]
        if blocked and not any(s.status == "success" for s in steps):
            reason = blocked[0].error or "Действие заблокировано политикой безопасности."
            return self._style(
                f"Я не выполнила это действие без подтверждения: {reason}",
                ctx,
            )

        if verified_success:
            return self._style(self._success_text(ctx, steps), ctx)

        # Not verified — report honestly what happened.
        failed = [s for s in steps if s.status == "failed"]
        pending = [
            s for s in steps
            if s.status == "pending" and getattr(s, "action", "") != "replan"
        ]

        parts = []
        if failed:
            names = ", ".join(sorted({(s.tool or s.action) for s in failed}))
            parts.append(f"не удалось выполнить: {names}")
        if pending:
            parts.append(f"не начато шагов: {len(pending)}")
        if "Max steps exceeded." in errors:
            parts.append("превышен лимит шагов выполнения")
        if errors:
            clean_errors = [e for e in errors if e != "Max steps exceeded."]
            if clean_errors:
                parts.append("ошибки: " + "; ".join(clean_errors[:3]))

        if not parts:
            parts.append("задача не подтверждена проверкой результата")

        summary = "; ".join(parts)
        return self._style(
            f"Я начала задачу «{ctx.raw_input}», но не смогла её честно завершить: {summary}.",
            ctx,
        )

    # ------------------------------------------------------------------
    def direct_response(self, ctx: TaskContext, text: str) -> str:
        """Wrap a non-agent (direct/chat) answer through the character layer."""
        return self._style(text, ctx)

    # ------------------------------------------------------------------
    def _success_text(self, ctx: TaskContext, steps) -> str:
        done_steps = [s for s in steps if s.status == "success"]
        last = done_steps[-1] if done_steps else None
        tool = getattr(last, "tool", None) if last else None
        obs_data = (getattr(last, "observation", None) or {}).get("data", {}) if last else {}

        if tool == "system.open_app":
            app = obs_data.get("app_name") or ctx.entities.get("app_name", "приложение")
            return f"Готово~ Приложение «{app}» запущено."
        if tool == "browser.open":
            url = obs_data.get("url", "")
            return f"Готово~ Открыла страницу в браузере: {url}"
        if tool == "files.list":
            items = obs_data.get("items", [])
            return f"Готово~ В папке найдено объектов: {len(items)}."
        if tool == "files.read":
            path = obs_data.get("path", "файл")
            return f"Готово~ Файл {path} прочитан."
        if len(done_steps) > 1:
            return f"Задача выполнена: шагов — {len(done_steps)}."
        return "Задача выполнена и проверена."

    def _style(self, text: str, ctx: TaskContext) -> str:
        if self.stylist is not None:
            try:
                mode = getattr(ctx.mode, "value", str(ctx.mode))
                styled = self.stylist.style(text, mode)
                if styled:
                    return styled
            except Exception:
                pass
        return text
