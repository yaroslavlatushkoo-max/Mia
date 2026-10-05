from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..tools.schemas import ToolResult


class SystemAdapter:
    def open_app(self, app_name: str) -> ToolResult:
        try:
            app_name = app_name.strip()
            if not app_name:
                return ToolResult(success=False, error="App name is empty")

            # Сначала пробуем как обычное приложение Windows
            try:
                subprocess.Popen(app_name, shell=True)
                return ToolResult(
                    success=True,
                    data={"app_name": app_name, "method": "shell"}
                )
            except Exception:
                pass

            # Потом пробуем как путь к exe / lnk
            candidate = Path(app_name)
            if candidate.exists():
                os.startfile(str(candidate))
                return ToolResult(
                    success=True,
                    data={"app_name": app_name, "method": "path"}
                )

            return ToolResult(
                success=False,
                error=f"Could not open app: {app_name}"
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))