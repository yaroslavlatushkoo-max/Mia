from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ..tools.schemas import ToolResult


class FileAdapter:
    """Файловые операции.

    Обратная совместимость сохранена: без ``sandbox`` методы работают с
    путями как раньше (используется ``workspace_root`` или текущий каталог).
    С переданным ``sandbox`` (mia.tools.sandbox.PathSandbox) каждый путь
    проверяется НЕПОСРЕДСТВЕННО перед операцией и любые выходы за границу
    песочницы возвращаются как честная ошибка ToolResult(success=False).
    """

    def __init__(self, workspace_root: Optional[str] = None, sandbox=None):
        self.workspace_root = (
            Path(workspace_root).expanduser().resolve() if workspace_root else None
        )
        self.sandbox = sandbox

    # ------------------------------------------------------------------
    def _guard(self, path: str, operation: str):
        """(allowed, Path|error-str). No sandbox -> legacy behavior."""
        if self.sandbox is None:
            p = Path(path)
            if self.workspace_root is not None and not p.is_absolute():
                p = self.workspace_root / p
            return True, p
        decision = self.sandbox.resolve_for(path, operation)
        if not decision.allowed:
            return False, decision.reason
        return True, decision.path

    def list_files(self, path: str = ".", limit: int = 50) -> ToolResult:
        allowed, target = self._guard(path, "read")
        if not allowed:
            return ToolResult(success=False, error=target, verified=False)
        p = target
        try:
            if not p.exists():
                return ToolResult(success=False, error=f"Path does not exist: {path}")

            items = []
            for i, item in enumerate(p.iterdir()):
                if i >= limit:
                    break
                items.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "path": str(item),
                })

            return ToolResult(success=True, data={"path": str(p), "items": items})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def read_file(self, path: str, max_chars: int = 4000) -> ToolResult:
        allowed, target = self._guard(path, "read")
        if not allowed:
            return ToolResult(success=False, error=target, verified=False)
        p = target
        try:
            if not p.exists():
                return ToolResult(success=False, error=f"File does not exist: {path}")

            if not p.is_file():
                return ToolResult(success=False, error=f"Path is not a file: {path}")

            text = p.read_text(encoding="utf-8", errors="ignore")
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]

            return ToolResult(
                success=True,
                data={
                    "path": str(p),
                    "content": text,
                    "truncated": truncated,
                    "size_chars": len(text),
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    # ------------------------------------------------------------------
    # Sandbox-aware write/delete (Task: safe tool execution).
    # These methods REQUIRE a configured sandbox — there is deliberately
    # no unsandboxed variant, so no caller can write outside the boundary.
    # Path is validated immediately before each operation.
    # ------------------------------------------------------------------
    def write_file(self, path: str, content: str, append: bool = False,
                   max_bytes=None) -> ToolResult:
        if self.sandbox is None:
            return ToolResult(success=False, verified=False,
                              error="files.write requires a configured sandbox.")
        allowed, target = self._guard(path, "write")
        if not allowed:
            return ToolResult(success=False, error=target, verified=False)
        p = target
        try:
            data = content.encode("utf-8", errors="replace")
            if max_bytes is not None and len(data) > int(max_bytes):
                return ToolResult(
                    success=False, verified=False,
                    error=f"Content too large ({len(data)} > {max_bytes} bytes).",
                )
            if p.is_dir():
                return ToolResult(success=False, error=f"Path is a directory: {path}",
                                  verified=False)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(str(p), "ab" if append else "wb") as fh:
                fh.write(data)
            # Verification hint: effect actually observed on disk.
            written = os.path.getsize(str(p))
            return ToolResult(
                success=True, verified=written > 0 or not data,
                data={
                    "path": str(p),
                    "bytes_written": len(data),
                    "size_after": written,
                    "mode": "append" if append else "overwrite",
                },
            )
        except OSError as e:
            return ToolResult(success=False, error=str(e), verified=False)

    def delete_file(self, path: str) -> ToolResult:
        if self.sandbox is None:
            return ToolResult(success=False, verified=False,
                              error="files.delete requires a configured sandbox.")
        allowed, target = self._guard(path, "delete")
        if not allowed:
            return ToolResult(success=False, error=target, verified=False)
        p = target
        try:
            if not p.exists():
                return ToolResult(success=False,
                                  error=f"File does not exist: {path}")
            if p.is_dir():
                # Directory removal is intentionally NOT supported: it is
                # recursive and far beyond the current safety envelope.
                return ToolResult(
                    success=False, verified=False,
                    error=f"Refusing to delete a directory: {path}. "
                          f"Only single files can be deleted.",
                )
            os.remove(str(p))
            return ToolResult(
                success=True, verified=not os.path.lexists(str(p)),
                data={"deleted": str(p)},
            )
        except OSError as e:
            return ToolResult(success=False, error=str(e), verified=False)
