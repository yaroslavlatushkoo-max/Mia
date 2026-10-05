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
                return ToolResult(success=False, error="App name is empty", verified=False)

            # On Windows shell=True may spawn cmd.exe even for unknown
            # commands; Popen succeeding does NOT mean the app launched.
            # Use `start` and check its exit code for an honest result
            # (CORE_MIGRATION.md §7: tool-level verification).
            import platform

            if platform.system() == "Windows":
                proc = subprocess.Popen(
                    f'start "" {app_name}',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    code = proc.wait(timeout=5)
                except Exception:
                    code = None
                if code == 0:
                    return ToolResult(
                        success=True,
                        data={"app_name": app_name, "method": "start", "exit_code": code},
                        verified=True,
                    )
                # Fallback: treat as a path to exe / lnk
                candidate = Path(app_name)
                if candidate.exists():
                    os.startfile(str(candidate))
                    return ToolResult(
                        success=True,
                        data={"app_name": app_name, "method": "path"},
                        verified=True,
                    )
                return ToolResult(
                    success=False,
                    error=f"Could not open app: {app_name} (exit code {code})",
                    verified=False,
                )

            # Non-Windows development environment: no GUI apps expected.
            # Report honestly instead of faking success.
            return ToolResult(
                success=False,
                error=(
                    f"Opening applications is only supported on Windows; "
                    f"current platform is {platform.system()}"
                ),
                verified=False,
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e), verified=False)