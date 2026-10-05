from __future__ import annotations

import webbrowser
import subprocess
from typing import Optional

from ..tools.schemas import ToolResult


class BrowserAdapter:
    def open_url(self, url: str, background: bool = False) -> ToolResult:
        try:
            url = url.strip()
            if not url:
                return ToolResult(success=False, error="URL is empty")

            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            if background:
                # Открыть в фоне через subprocess
                # Не переключает фокус
                subprocess.Popen(
                    f'start "" /min "{url}"',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return ToolResult(
                    success=True,
                    data={"url": url, "mode": "background"}
                )
            else:
                # Обычное открытие — переключает фокус
                webbrowser.open(url)
                return ToolResult(
                    success=True,
                    data={"url": url, "mode": "foreground"}
                )

        except Exception as e:
            return ToolResult(success=False, error=str(e))