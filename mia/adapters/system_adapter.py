from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..tools.schemas import ToolResult
from .legacy_system_bridge import get_system_skills, resolve_app


class SystemAdapter:
    """Thin adapter over the LEGACY app-resolution chain.

    Chain (Task 5 contract):

        ToolRegistry -> system.open_app -> SystemAdapter
                     -> legacy SystemSkills.find_app / find_app_fuzzy
                     -> config.APPS (single source of the app list)
                     -> Windows launch

    The adapter deliberately owns NO second APPS dictionary and NO copy
    of legacy search logic. When the legacy stack is unavailable in the
    current OS environment it reports an honest FAILURE — never success.
    """

    # ------------------------------------------------------------------
    def open_app(self, app_name: str) -> ToolResult:
        try:
            app_name = (app_name or "").strip()
            if not app_name:
                return ToolResult(success=False, error="App name is empty", verified=False)

            target, legacy_available = resolve_app(app_name)

            if not legacy_available:
                # Legacy skills cannot run here (non-Windows dev env).
                # Honest failure, no fake success (CORE_MIGRATION.md §7).
                import platform

                return ToolResult(
                    success=False,
                    error=(
                        "Legacy app resolution (SystemSkills/config.APPS) is "
                        f"unavailable on {platform.system()}; application opening "
                        "is only supported on Windows"
                    ),
                    verified=False,
                    data={"reason": "LEGACY_UNAVAILABLE"},
                )

            if target is None:
                # Legacy stack works but the app genuinely does not exist.
                return ToolResult(
                    success=False,
                    error=f"Application not found via legacy lookup: {app_name}",
                    verified=False,
                    data={"reason": "APP_NOT_FOUND"},
                )

            return self._launch(target, app_name)
        except Exception as e:
            return ToolResult(success=False, error=str(e), verified=False)

    # ------------------------------------------------------------------
    def _launch(self, target: str, app_name: str) -> ToolResult:
        """Launch a resolved target; verify honestly that it started."""
        import platform

        candidate = Path(target)
        try:
            if platform.system() == "Windows":
                if candidate.exists() or target.endswith((".lnk", ".url")):
                    os.startfile(str(target))
                    return ToolResult(
                        success=True,
                        data={
                            "app_name": app_name,
                            "target": target,
                            "method": "startfile",
                            "resolver": "legacy",
                        },
                        verified=True,
                    )
                # Bare exe name from config.APPS: `start` resolves via PATH/App Paths.
                proc = subprocess.Popen(
                    f'start "" {target}',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                code = proc.wait(timeout=5)
                if code == 0:
                    return ToolResult(
                        success=True,
                        data={
                            "app_name": app_name,
                            "target": target,
                            "method": "start",
                            "exit_code": code,
                            "resolver": "legacy",
                        },
                        verified=True,
                    )
                return ToolResult(
                    success=False,
                    error=f"Launch failed for '{app_name}' ({target}), exit code {code}",
                    verified=False,
                    data={"reason": "LAUNCH_FAILED"},
                )

            # Non-Windows: os.startfile absent; do not pretend.
            return ToolResult(
                success=False,
                error=(
                    f"Opening applications is only supported on Windows; "
                    f"current platform is {platform.system()}"
                ),
                verified=False,
                data={"reason": "UNSUPPORTED_OS", "resolved_target": target},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Launch failed for '{app_name}': {e}",
                verified=False,
                data={"reason": "LAUNCH_FAILED"},
            )