"""File tools: `read_file`, `write_file`, `list_dir`.

Paths are resolved relative to the BashTool's cwd so that the model's
mental model of "current directory" is consistent across tools. The
BashTool instance is injected on construction rather than imported as a
module global — that keeps tests hermetic and permits multiple sessions
in-process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .bash import BashTool


def _resolve(bash: BashTool, path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = bash.cwd / p
    return p


# ---- read_file -----------------------------------------------------------


class ReadFileInput(BaseModel):
    path: str = Field(..., description="Path to the file (absolute or relative to cwd).")


class ReadFileTool:
    name = "read_file"
    description = "Read the full contents of a UTF-8 text file."
    input_model = ReadFileInput

    def __init__(self, bash: BashTool) -> None:
        self._bash = bash

    async def __call__(self, path: str) -> dict[str, Any]:
        target = _resolve(self._bash, path)
        if not target.exists():
            return {"error": f"file not found: {target}"}
        if target.is_dir():
            return {"error": f"path is a directory, not a file: {target}"}
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return {"error": f"failed to read {target}: {e}"}
        return {"path": str(target), "content": content, "bytes": target.stat().st_size}


# ---- write_file ----------------------------------------------------------


class WriteFileInput(BaseModel):
    path: str = Field(..., description="Path to write (absolute or relative to cwd).")
    content: str = Field(..., description="Full file contents. Existing file is overwritten.")


class WriteFileTool:
    name = "write_file"
    description = (
        "Write text to a file, overwriting if it exists. Parent directories "
        "must already exist."
    )
    input_model = WriteFileInput

    def __init__(self, bash: BashTool) -> None:
        self._bash = bash

    async def __call__(self, path: str, content: str) -> dict[str, Any]:
        target = _resolve(self._bash, path)
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as e:
            return {"error": f"failed to write {target}: {e}"}
        return {"path": str(target), "bytes_written": len(content.encode("utf-8"))}


# ---- list_dir ------------------------------------------------------------


class ListDirInput(BaseModel):
    path: str = Field(".", description="Directory to list. Defaults to cwd.")


class ListDirTool:
    name = "list_dir"
    description = "List the entries of a directory (names only, with type tags)."
    input_model = ListDirInput

    def __init__(self, bash: BashTool) -> None:
        self._bash = bash

    async def __call__(self, path: str = ".") -> dict[str, Any]:
        target = _resolve(self._bash, path)
        if not target.exists():
            return {"error": f"no such path: {target}"}
        if not target.is_dir():
            return {"error": f"not a directory: {target}"}
        entries = []
        for entry in sorted(target.iterdir()):
            kind = "dir" if entry.is_dir() else ("link" if entry.is_symlink() else "file")
            entries.append({"name": entry.name, "type": kind})
        return {"path": str(target), "entries": entries}
