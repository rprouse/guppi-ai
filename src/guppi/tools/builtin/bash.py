"""The `bash` tool.

Executes shell commands via `asyncio.create_subprocess_shell` with an
explicit working directory that survives across calls. This object is
the *shared* source of truth for "where we are" — `files.py` reads from
the same instance so all file paths resolve relative to the same cwd.

Why not spawn one persistent shell?
  A long-lived shell is simple to describe but a nightmare to supervise:
  stuck prompts, ANSI escape leakage, and partial output all become
  problems the agent has to debug. Tracking cwd in Python and handing
  each command a fresh subprocess is the standard agent-framework trade.

`cd` is intercepted rather than executed: we update `self.cwd` directly
and return a synthetic success message. Compound commands (e.g.
`cd foo && make`) are executed in the shell normally — their effect on
the shell's own cwd is discarded when the subprocess exits. Pure `cd`
calls are how the model navigates the session.
"""

from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class BashInput(BaseModel):
    """Schema for the `bash` tool."""

    command: str = Field(..., description="The shell command to execute.")
    timeout: int | None = Field(
        None,
        description=(
            "Optional override for the command timeout in seconds. "
            "Defaults to the session-configured timeout."
        ),
    )


class BashTool:
    """Stateful bash executor with persistent cwd."""

    name = "bash"
    description = (
        "Run a shell command and return stdout, stderr, and exit code. "
        "Working directory persists between calls. Use `cd <path>` alone "
        "to change the directory for subsequent calls."
    )
    input_model = BashInput

    def __init__(self, default_timeout: int) -> None:
        self.cwd: Path = Path(os.getcwd()).resolve()
        self.default_timeout = default_timeout

    async def __call__(self, command: str, timeout: int | None = None) -> dict[str, Any]:
        timeout_s = timeout if timeout is not None else self.default_timeout

        # Intercept a bare `cd` so we can persist the directory change.
        stripped = command.strip()
        if stripped.startswith("cd ") or stripped == "cd":
            return self._handle_cd(stripped)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.cwd),
            )
        except OSError as e:
            return {"error": f"failed to spawn shell: {e}"}

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "error": f"command timed out after {timeout_s}s",
                "command": command,
                "cwd": str(self.cwd),
            }

        return {
            "stdout": stdout_b.decode("utf-8", errors="replace"),
            "stderr": stderr_b.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode,
            "cwd": str(self.cwd),
        }

    # ---- helpers ---------------------------------------------------------

    def _handle_cd(self, cmd: str) -> dict[str, Any]:
        # cd with no argument → home dir (parity with real shells).
        parts = shlex.split(cmd)
        target = Path.home() if len(parts) == 1 else Path(parts[1]).expanduser()
        if not target.is_absolute():
            target = self.cwd / target
        target = target.resolve()
        if not target.is_dir():
            return {"error": f"cd: no such directory: {target}"}
        self.cwd = target
        return {"stdout": "", "stderr": "", "exit_code": 0, "cwd": str(self.cwd)}
