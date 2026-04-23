# Host environment info in the system prompt

**Date:** 2026-04-22
**Status:** Approved

## Problem

The guppi agent currently emits shell commands without knowing what OS or shell
it is running against. On Windows, `asyncio.create_subprocess_shell` routes
commands through `cmd.exe` (via `COMSPEC`); on Linux and macOS it routes them
through `/bin/sh`. The model has no way to distinguish these cases and will
cheerfully emit `ls` on Windows or `dir` on Linux.

## Goal

Detect the host OS and the shell that the `bash` tool actually dispatches
through, then surface that information in the system prompt so the model picks
syntactically-appropriate commands from the first turn.

Scope: detection and prompt injection only. Execution behaviour of the `bash`
tool is unchanged.

## Non-goals

- No PowerShell tool. A future `pwsh` tool is possible but out of scope here.
- No changes to `BashTool.__call__`; the default shell per platform stays as-is.
- No unit tests — the project has no test suite today, and this change is small
  and pure.

## Architecture

### New module: `src/guppi/env.py`

Single public function:

```python
def describe_environment() -> str: ...
```

Returns a markdown `## Environment` block. Pure, no side effects, safe to call
from anywhere.

### Modified: `src/guppi/cli.py`

After skills are loaded and before `build_system_prompt` is called, append the
environment block to `DEFAULT_SYSTEM_PROMPT`:

```python
base_prompt = DEFAULT_SYSTEM_PROMPT + "\n\n" + describe_environment()
system_prompt = build_system_prompt(base_prompt, selected)
```

`build_system_prompt` in `skills/loader.py` is unchanged. `agent.py` is
unchanged.

### Why this seam

The environment is a property of the process launching guppi, not of the
agent's conversation state. `cli.py` already owns config/skill wiring, so it is
the natural place for environment detection.

## Detection rules

```python
import os, platform, sys

def describe_environment() -> str:
    os_name = platform.system()        # "Windows" | "Linux" | "Darwin"
    os_release = platform.release()    # e.g. "11", "6.5.0-generic"
    plat = sys.platform                # "win32" | "linux" | "darwin"

    if os_name == "Windows":
        shell = os.environ.get("COMSPEC", "cmd.exe")
        sep = "\\"
        hint = ("Prefer shell syntax compatible with cmd.exe "
                "(e.g. `dir` not `ls`, `type` not `cat`, `%VAR%` not `$VAR`).")
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
```

### Why these specific fields

- **OS name + release + `sys.platform`** — the model benefits from knowing both
  the human-readable name ("Windows 11") and the machine identifier ("win32")
  because it often pattern-matches on the latter.
- **Default shell = what `create_subprocess_shell` actually uses** — not the
  user's `$SHELL`. On POSIX, commands run through `/bin/sh` regardless of the
  user's login shell; reporting bash/zsh would mislead the model.
- **`COMSPEC` on Windows** — `create_subprocess_shell` reads this env var. If a
  user has overridden it, we report the truth.
- **Path separator** — called out explicitly because it is a common source of
  cross-platform bugs.
- **Syntax hint** — one concrete nudge per platform. Enough to steer the model,
  not so much that it bloats the prompt.

## Build sequence

At session start, in `cli.py`, the system prompt is assembled in this order:

1. `DEFAULT_SYSTEM_PROMPT` — GUPPI character, tools section, voice rules.
2. `describe_environment()` — new `## Environment` block.
3. Skills block — appended by `build_system_prompt`, unchanged.

## Debug output

When `--debug` is set, log a one-liner during startup so the user can see what
was detected:

```python
if settings.debug:
    renderer.info(f"host: {os_name} ({plat}), shell: {shell}")
```

## Example output (Windows 11)

```
## Environment

- Host OS: Windows 11 (win32)
- Default shell invoked by `bash` tool: C:\WINDOWS\system32\cmd.exe
- Path separator: `\`
- Prefer shell syntax compatible with cmd.exe (e.g. `dir` not `ls`, `type` not `cat`, `%VAR%` not `$VAR`).
```

## Example output (Linux)

```
## Environment

- Host OS: Linux 6.5.0-generic (linux)
- Default shell invoked by `bash` tool: /bin/sh
- Path separator: `/`
- Prefer POSIX-compatible shell syntax (e.g. `ls`, `cat`, `$VAR`).
```

## Future work (not in this change)

- A `PwshTool` that dispatches through `pwsh -NoProfile -Command` and shares
  cwd state with `BashTool`. When present, `describe_environment()` should
  mention it so the model picks between tools deliberately.
- Smarter detection for WSL, Git Bash on Windows, or containerised shells.
