"""Typer-based CLI entry point.

The `guppi` binary launches an interactive REPL by default:

    $ guppi
    > build me a hello world in rust
    ...

Slash commands inside the REPL:
    /exit     — quit cleanly
    /clear    — reset the conversation history

Command-line flags:
    --model        override the configured model for this session
    --debug        show raw streaming events and debug-only diagnostics
    --no-skills    skip skill loading (useful for reproducing bugs)
"""

from __future__ import annotations

import asyncio
import sys

import typer

from .agent import DEFAULT_SYSTEM_PROMPT, Agent
from .config import Settings
from .renderer import Renderer
from .skills.loader import build_system_prompt, load_skills, select_relevant_skills
from .tools.registry import build_default_registry

app = typer.Typer(
    add_completion=False,
    help="guppi — an agentic CLI assistant.",
    no_args_is_help=False,
)


@app.command()
def main(
    model: str | None = typer.Option(None, "--model", help="Override the configured model."),
    debug: bool = typer.Option(False, "--debug", help="Show raw streaming events."),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip loading agent skills."),
) -> None:
    """Launch the interactive REPL."""
    try:
        settings = Settings()  # type: ignore[call-arg] — pydantic loads from env.
    except Exception as e:  # noqa: BLE001
        typer.echo(f"config error: {e}", err=True)
        typer.echo("hint: copy .env.example to .env and fill in ANTHROPIC_API_KEY.", err=True)
        raise typer.Exit(code=2) from e

    if model is not None:
        settings.model = model
    if debug:
        settings.debug = True

    renderer = Renderer(debug=settings.debug)
    registry = build_default_registry(bash_timeout=settings.timeout)

    skills = [] if no_skills else load_skills(settings.skills_dir)
    selected = select_relevant_skills(skills)
    system_prompt = build_system_prompt(DEFAULT_SYSTEM_PROMPT, selected)

    renderer.banner(model=settings.model, skills_count=len(selected))
    if settings.debug:
        renderer.info(f"skills dir: {settings.skills_dir}")
        renderer.info(f"loaded {len(skills)} skill(s), using {len(selected)}")

    agent = Agent(
        settings=settings,
        registry=registry,
        renderer=renderer,
        system_prompt=system_prompt,
    )

    try:
        asyncio.run(_repl(agent, renderer))
    except KeyboardInterrupt:
        renderer.info("bye.")


async def _repl(agent: Agent, renderer: Renderer) -> None:
    while True:
        try:
            user_input = _prompt()
        except (EOFError, KeyboardInterrupt):
            renderer.info("\nbye.")
            return

        if not user_input.strip():
            continue

        cmd = user_input.strip().lower()
        if cmd in {"/exit", "/quit"}:
            renderer.info("bye.")
            return
        if cmd == "/clear":
            agent.clear_history()
            renderer.info("conversation cleared.")
            continue

        renderer.user_prompt_marker()
        try:
            await agent.run_turn(user_input)
        except KeyboardInterrupt:
            renderer.warning("turn interrupted.")
        except Exception as e:  # noqa: BLE001
            renderer.error(f"{type(e).__name__}: {e}")
            if agent.settings.debug:
                import traceback
                renderer.console.print(traceback.format_exc(), style="dim red")


def _prompt() -> str:
    """Read one line from stdin with a simple prompt character.

    Kept synchronous: the REPL's idle time is spent blocked in input(),
    and we don't gain anything by making stdin async. If/when we add
    multi-line input or history, swap this for prompt_toolkit.
    """
    sys.stdout.write("\n> ")
    sys.stdout.flush()
    return sys.stdin.readline().rstrip("\n")


if __name__ == "__main__":
    app()
