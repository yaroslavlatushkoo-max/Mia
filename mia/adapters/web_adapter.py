from __future__ import annotations

from ..tools.schemas import ToolResult


class WebAdapter:
    def search(self, query: str) -> ToolResult:
        try:
            query = query.strip()
            if not query:
                return ToolResult(success=False, error="Query is empty")

            # Пока не делаем реальный поиск.
            # Это место для подключения старого web-модуля или нового search provider.
            # STUB: честный failure до подключения реального backend
            # (CORE_MIGRATION.md §5 — stub must not masquerade as success).
            return ToolResult(
                success=False,
                error=(
                    "web.search is a stub: real search backend is not "
                    "connected yet; use browser.open with a Google search URL"
                ),
                data={"query": query, "results": [], "stub": True},
                verified=False,
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
