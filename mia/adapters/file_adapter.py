from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..tools.schemas import ToolResult


class FileAdapter:
    def list_files(self, path: str = ".", limit: int = 50) -> ToolResult:
        try:
            p = Path(path)
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
        try:
            p = Path(path)
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