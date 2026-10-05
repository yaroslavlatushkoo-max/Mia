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
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results": [],
                    "note": "Web search adapter is connected, but real search backend is not implemented yet."
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
