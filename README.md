# guppi

<img align="right" width="200" height="200" src="img/guppi.png">

GUPPI (or General Unit Primary Peripheral Interface) Is a semi-sentient software
being that helps Replicants interact with the many systems they have at their
disposal. This is an early implementation of the interface and as this is not
the year 2133 in the fictional [Bobverse](https://bobiverse.fandom.com/wiki/We_Are_Legion_(We_Are_Bob)_Wiki),
This GUPPI is not actually semi-sentient or is it?

Guppi is a Python CLI agentic assistant built on the Anthropic API. Small, async,
streaming, with pluggable tools and (soon) MCP + Agent Skills support.

This is a learning project built from first principles — the code is kept
deliberately simple so the agent loop is easy to read and extend.

## Install

guppi uses [`uv`](https://docs.astral.sh/uv/) for packaging.

```bash
# from the repo root
uv sync
```

`uv sync` resolves dependencies and writes `uv.lock`. **Commit `uv.lock`**
to the repo so other contributors get reproducible installs.

## Configure

```bash
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY
```

All other settings are optional — see `.env.example` or `src/guppi/config.py`.

## Run

```bash
uv run guppi
```

Inside the REPL:

* type your message and press Enter
* `/clear` — reset conversation history
* `/exit` — quit (Ctrl+C also works)

Flags:

* `--model <id>` — override the configured model for one session
* `--debug` — show raw streaming events
* `--no-skills` — skip skill loading

## Agent Skills

Drop a `SKILL.md` file under `~/.config/guppi/skills/<skill-name>/`:

```markdown
---
name: git-safety
description: Safe git operations; confirm before destructive commands
triggers: [git, commit, push, rebase]
---

When the user asks for a destructive git operation, always summarise
what will happen and ask for confirmation first.
```

All skills under the skills dir are loaded at session start and appended
to the system prompt.

## Project layout

```
src/guppi/
  cli.py           — typer entry point and REPL
  agent.py         — the agentic streaming loop
  context.py       — history + token-budget truncation
  renderer.py      — rich terminal rendering
  config.py        — pydantic settings (env / .env)
  tools/
    registry.py    — single dispatcher; pydantic → Anthropic schema bridge
    builtin/
      bash.py      — shell exec with persistent cwd + timeouts
      files.py     — read_file / write_file / list_dir
  mcp/
    client.py      — stub; real MCP client lands here
  skills/
    skill.py       — Skill dataclass
    loader.py      — YAML frontmatter + markdown body loader
```

## Model

Default is `claude-sonnet-4-5`. Override via `GUPPI_MODEL` env var or
`--model` flag.

## Status

Working end-to-end for the builtin tools. Explicit stubs:

* MCP: `src/guppi/mcp/client.py` is a no-op; registry has a
  `register_mcp_server` stub that logs and ignores.
* Skill selection: currently "load all"; smarter routing is planned.

## License

MIT.
