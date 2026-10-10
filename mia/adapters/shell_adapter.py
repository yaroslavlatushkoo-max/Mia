from __future__ import annotations

"""ShellAdapter — безопасное исполнение shell.safe_run (Task: safe tools).

Ограничения (никакого произвольного исполнения):
  * только список аргументов, shell=False (без интерпретатора);
  * shell-мета-символы (&& ; | > < $ ` и пр.) запрещены в аргументах;
  * бинарник обязан быть в allowlist и существовать в PATH;
  * рабочий каталог subprocess — строго workspace_root песочницы;
  * wall-clock timeout с честным kill процесса;
  * вывод ограничен по объёму (stdout/stderr, max_output_bytes).

HITL не обходится: подтверждение high-risk инструмента обеспечивает
PolicyEngine/AgentLoop до вызова executor'а.
"""

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from ..tools.schemas import ToolResult

# Минимальный allowlist безвредных informational-команд (кроссплатформенно).
DEFAULT_ALLOWED_BINARIES = {
    "python", "python3", "py",
    "echo", "dir", "ls", "pwd", "whoami", "hostname", "date", "type",
}

#: символы, наличие которых превращает аргумент в shell-инъекцию
_SHELL_META = set('&|<>()`*"\n\r\\{}!')  # ';' легален как часть аргумента:
# shlex уже разделил команду, оболочка не запускается (shell=False)


class ShellAdapter:
    def __init__(self, sandbox=None, allowed_binaries: Optional[List[str]] = None,
                 timeout: int = 15, max_output_bytes: int = 64 * 1024):
        self.sandbox = sandbox
        self.allowed = {os.path.normcase(b) for b in (
            allowed_binaries or sorted(DEFAULT_ALLOWED_BINARIES))}
        self.timeout = max(1, int(timeout))
        self.max_output_bytes = max(1024, int(max_output_bytes))

    # ------------------------------------------------------------------
    def run(self, command, cwd: Optional[str] = None) -> ToolResult:
        if self.sandbox is None:
            return ToolResult(success=False, verified=False,
                              error="shell.safe_run requires a configured sandbox.")
        workspace_root = self.sandbox.workspace_root

        # Аргумент мог пройти через JSON-схему инструмента как список argv —
        # это каноническая форма (никакого shell-парсинга).
        if isinstance(command, (list, tuple)):
            argv = [str(t) for t in command]
        else:
            try:
                argv = shlex.split(str(command))
            except ValueError as e:
                return ToolResult(success=False, verified=False,
                                  error=f"Cannot parse command: {e}")
        if not argv:
            return ToolResult(success=False, error="Empty command.", verified=False)

        # 1. Мета-символы -> отказ (мы не запускаем оболочку вообще).
        for token in argv:
            if _SHELL_META & set(token):
                return ToolResult(
                    success=False, verified=False,
                    error=f"Shell metacharacters are not allowed in safe_run: '{token}'.")

        # 2. Бинарник: только имя (не путь), только из allowlist, только из PATH.
        binary = argv[0]
        base = os.path.basename(binary)
        if base != binary or "/" in binary or "\\" in binary:
            return ToolResult(
                success=False, verified=False,
                error="Only bare executable names from the allowlist are accepted "
                      "(no paths).")
        if os.path.normcase(base) not in self.allowed:
            return ToolResult(
                success=False, verified=False,
                error=f"Command '{base}' is not in the safe_run allowlist "
                      f"({sorted(self.allowed)}). Arbitrary execution is forbidden.")
        exe = shutil.which(base)
        if not exe:
            return ToolResult(success=False, verified=False,
                              error=f"Allowed command '{base}' not found in PATH.")

        # 3. cwd — если задан, обязан резолвиться внутри песочницы.
        workdir = str(workspace_root)
        if cwd not in (None, "", "."):
            decision = self.sandbox.resolve_for(cwd, "read")
            if not decision.allowed or not decision.path.is_dir():
                return ToolResult(
                    success=False, verified=False,
                    error=f"cwd rejected by sandbox: {decision.reason or 'not a directory'}")
            workdir = str(decision.path)

        # 4. Запуск БЕЗ оболочки, с таймаутом и лимитом вывода.
        try:
            proc = subprocess.Popen(
                argv, cwd=workdir, shell=False,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, text=True,
            )
        except OSError as e:
            return ToolResult(success=False, verified=False, error=str(e))

        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except Exception:
                stdout, stderr = "", ""

        truncated = (len(stdout or "") > self.max_output_bytes or
                     len(stderr or "") > self.max_output_bytes)
        stdout = (stdout or "")[: self.max_output_bytes]
        stderr = (stderr or "")[: self.max_output_bytes]

        if timed_out:
            return ToolResult(
                success=False, verified=False,
                data={"stdout": stdout, "returncode": -1, "killed": True,
                      "truncated": truncated},
                error=f"Command exceeded {self.timeout}s timeout and was killed.",
            )

        rc = proc.returncode
        return ToolResult(
            success=rc == 0,
            verified=rc == 0,
            data={
                "stdout": stdout,
                "stderr": stderr,
                "returncode": rc,
                "argv": argv,
                "cwd": workdir,
                "truncated": truncated,
            },
            error=None if rc == 0 else f"Exit code {rc}: {stderr.strip()[:200]}",
        )
