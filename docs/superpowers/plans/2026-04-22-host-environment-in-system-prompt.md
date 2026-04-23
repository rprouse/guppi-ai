# Host Environment in System Prompt — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At session startup, detect host OS and the shell dispatched through by the `bash` tool, then append an `## Environment` block to the system prompt so the model picks syntactically-appropriate commands.

**Architecture:** Add a new pure module `src/guppi/env.py` whose single function returns the markdown block. Wire it into `cli.py` so the block is appended to `DEFAULT_SYSTEM_PROMPT` before skills are merged. No changes to `agent.py`, `skills/loader.py`, or any tool.

**Tech Stack:** Python 3, `platform` / `sys` / `os` stdlib modules, `uv` for running the CLI.

**Spec:** `docs/superpowers/specs/2026-04-22-host-environment-in-system-prompt-design.md`

**Testing note:** The project has no existing test suite (matches the codebase's "deliberately simple" convention — see `README.md` line 15). Each task ends with a manual smoke-test that runs the CLI and verifies the observable effect, rather than pytest runs.

---

## File Structure

```
src/guppi/
  env.py            — NEW. describe_environment() returns the ## Environment markdown block.
  cli.py            — MODIFIED. Imports describe_environment, appends its output, optionally logs at --debug.
docs/superpowers/
  specs/2026-04-22-host-environment-in-system-prompt-design.md  — existing spec (reference only)
  plans/2026-04-22-host-environment-in-system-prompt.md          — this plan
```

Nothing else in the repo is touched.

---

## Task 1: Create `src/guppi/env.py`

**Files:**
- Create: `src/guppi/env.py`

- [ ] **Step 1: Write the module**

Create `src/guppi/env.py` with the following contents exactly:

```python
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
```

- [ ] **Step 2: Smoke-test the function in isolation**

Run:

```bash
uv run python -c "from guppi.env import describe_environment; print(describe_environment())"
```

Expected output on Windows (exact OS release and shell path will vary):

```
## Environment

- Host OS: Windows 11 (win32)
- Default shell invoked by `bash` tool: C:\WINDOWS\system32\cmd.exe
- Path separator: `\`
- Prefer shell syntax compatible with cmd.exe (e.g. `dir` not `ls`, `type` not `cat`, `%VAR%` not `$VAR`).
```

Expected output on Linux (release will vary):

```
## Environment

- Host OS: Linux 6.5.0-generic (linux)
- Default shell invoked by `bash` tool: /bin/sh
- Path separator: `/`
- Prefer POSIX-compatible shell syntax (e.g. `ls`, `cat`, `$VAR`).
```

Verify all four bullets are present and the values match the running host. If the import fails with `ModuleNotFoundError: No module named 'guppi'`, run `uv sync` first.

- [ ] **Step 3: Commit**

```bash
git add src/guppi/env.py
git commit -m "feat: add host environment detection for system prompt"
```

---

## Task 2: Wire `describe_environment()` into the CLI

**Files:**
- Modify: `src/guppi/cli.py` (import at top + two line changes inside `main()`)

- [ ] **Step 1: Add the import**

Open `src/guppi/cli.py`. Find the existing imports block at the top (around line 26-30). Add an import for the new module so the imports section looks like this:

```python
from .agent import DEFAULT_SYSTEM_PROMPT, Agent
from .config import Settings
from .env import describe_environment
from .renderer import Renderer
from .skills.loader import build_system_prompt, load_skills, select_relevant_skills
from .tools.registry import build_default_registry
```

(Import is inserted alphabetically between `.config` and `.renderer`.)

- [ ] **Step 2: Append the environment block when building the system prompt**

In `src/guppi/cli.py`, find this line inside `main()` (currently line 63):

```python
    system_prompt = build_system_prompt(DEFAULT_SYSTEM_PROMPT, selected)
```

Replace those two lines (the one that builds `skills`/`selected` stays the same — we're only replacing the `build_system_prompt` line and adding one above it):

```python
    skills = [] if no_skills else load_skills(settings.skills_dir)
    selected = select_relevant_skills(skills)
    base_prompt = DEFAULT_SYSTEM_PROMPT + "\n\n" + describe_environment()
    system_prompt = build_system_prompt(base_prompt, selected)
```

- [ ] **Step 3: Add a debug-only log line for the detected environment**

Still in `main()`, find the existing debug block (currently around lines 66-68):

```python
    if settings.debug:
        renderer.info(f"skills dir: {settings.skills_dir}")
        renderer.info(f"loaded {len(skills)} skill(s), using {len(selected)}")
```

Add one more line inside that block so it reads:

```python
    if settings.debug:
        renderer.info(f"skills dir: {settings.skills_dir}")
        renderer.info(f"loaded {len(skills)} skill(s), using {len(selected)}")
        renderer.info(f"host: {platform.system()} ({sys.platform}), shell: {os.environ.get('COMSPEC') if platform.system() == 'Windows' else '/bin/sh'}")
```

Then add the three stdlib imports at the top of the file, alongside the existing `import asyncio` / `import sys` block:

```python
import asyncio
import os
import platform
import sys
```

(`sys` is already imported; add `os` and `platform` only.)

- [ ] **Step 4: Smoke-test the full CLI with `--debug --no-skills`**

Run:

```bash
uv run guppi --debug --no-skills
```

The `--no-skills` flag keeps the prompt minimal so the environment block is easier to inspect. The banner should appear as normal, followed by three `info` lines — one for skills dir, one for skill count, and the new one for host/shell. Example expected extra line on Windows:

```
host: Windows (win32), shell: C:\WINDOWS\system32\cmd.exe
```

Type `/exit` and press Enter to leave the REPL.

If the debug line does not appear or the CLI crashes with `NameError: name 'os' is not defined` or similar, re-check Step 3's imports.

- [ ] **Step 5: Verify the env block reaches the model**

Inside the same REPL session (or a new one with `uv run guppi --debug --no-skills`), send this message:

```
what operating system and shell are you running on? quote the Environment block verbatim.
```

Expected: the model quotes back the four-bullet `## Environment` block matching the running host. If it does not (e.g. says "I don't know" or invents values), inspect that `base_prompt` actually contains the block — add a temporary `print(base_prompt)` above the `build_system_prompt` call, rerun, remove the print afterward.

Exit with `/exit`.

- [ ] **Step 6: Commit**

```bash
git add src/guppi/cli.py
git commit -m "feat: inject host environment block into system prompt"
```

---

## Self-review checklist (performed while writing this plan)

- **Spec coverage:** Every section of the spec maps to a task.
  - New module `src/guppi/env.py` with `describe_environment()` → Task 1.
  - `cli.py` wiring (append block before `build_system_prompt`) → Task 2, Step 2.
  - `--debug` one-liner log → Task 2, Step 3.
  - Unchanged `agent.py` / `skills/loader.py` / tools → verified (no task touches them).
  - No unit tests → verified (project convention; smoke-tests substitute).
- **Placeholder scan:** No TBDs, TODOs, "similar to task N", or abstract descriptions. Every code block is complete.
- **Type consistency:** Function name `describe_environment` is consistent across Task 1 (definition), Task 2 Step 1 (import), and Task 2 Step 2 (call site). No other symbols introduced.
