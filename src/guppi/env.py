"""Host environment detection for the system prompt.

`describe_environment()` returns a markdown block that gets appended to the
base system prompt at session start. The model uses this to pick
syntactically-appropriate shell commands (cmd.exe on Windows vs POSIX sh on
Linux and macOS).

Why this module exists:
  `asyncio.create_subprocess_shell` — used by the bash tool — runs through
  `cmd.exe` on Windows (via the `COMSPEC` env var) and `/bin/sh` on POSIX,
  regardless of the user's login shell. Without this block, the model
  cheerfully emits `ls` on Windows or `dir` on Linux. The block tells the
  model what shell it is actually talking to.
"""

from __future__ import annotations

import os
import platform
import sys


def describe_environment() -> str:
    """Return the ## Environment markdown block for the current host."""
    os_name = platform.system()        # "Windows" | "Linux" | "Darwin"
    os_release = platform.release()    # e.g. "11", "6.5.0-generic"
    plat = sys.platform                # "win32" | "linux" | "darwin"

    if os_name == "Windows":
        shell = os.environ.get("COMSPEC", "cmd.exe")
        sep = "\\"
        hint = (
            "Prefer shell syntax compatible with cmd.exe "
            "(e.g. `dir` not `ls`, `type` not `cat`, `%VAR%` not `$VAR`)."
        )
    else:
        shell = "/bin/sh"
        sep = "/"
        hint = "Prefer POSIX-compatible shell syntax (e.g. `ls`, `cat`, `$VAR`)."

    return (
        "## Environment\n\n"
        f"- Host OS: {os_name} {os_release} ({plat})\n"
        f"- Default shell invoked by `bash` tool: {shell}\n"
        f"- Path separator: `{sep}`\n"
        f"- {hint}"
    )
