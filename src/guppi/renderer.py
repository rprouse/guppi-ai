"""Rich-based terminal rendering.

The Renderer is the *only* place that calls into `rich`. Keeping I/O
concentrated here makes the agent loop pure(ish) and easy to test —
anything else that wants to speak to the user goes through these
methods.

Rendering model:
  * Streaming assistant text is drawn inside a `Live` region so each
    delta lands in-place instead of scrolling.
  * Tool calls render as dim panels *before* execution, for
    transparency/debugging.
  * Warnings, errors, and debug events get distinct styles.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text


class Renderer:
    def __init__(self, debug: bool = False) -> None:
        self.console = Console()
        self.debug = debug

    # ---- session-level ----------------------------------------------------

    def banner(self, model: str, skills_count: int) -> None:
        self.console.print(
            Panel.fit(
                f"[bold cyan]guppi[/] · model=[yellow]{model}[/] · "
                f"skills=[magenta]{skills_count}[/]\n"
                "Type [green]/exit[/] to quit, [green]/clear[/] to reset history.",
                border_style="cyan",
            )
        )

    def user_prompt_marker(self) -> None:
        self.console.print(Rule(style="dim"))

    # ---- streaming assistant text ----------------------------------------

    @contextmanager
    def stream_assistant(self) -> Iterator["AssistantStream"]:
        """Context manager yielding a handle that accepts text deltas."""
        buffer: list[str] = []
        with Live(
            Text(""),
            console=self.console,
            refresh_per_second=24,
            transient=False,
        ) as live:
            yield AssistantStream(buffer, live)
        # After the Live region closes, re-render as Markdown for code blocks etc.
        final = "".join(buffer).strip()
        if final:
            self.console.print(Markdown(final))

    # ---- tool calls / results --------------------------------------------

    def tool_call(self, name: str, inputs: dict[str, Any]) -> None:
        pretty = json.dumps(inputs, indent=2, default=str)
        body = Syntax(pretty, "json", theme="ansi_dark", word_wrap=True)
        self.console.print(
            Panel(
                body,
                title=f"[bold]tool →[/] [cyan]{name}[/]",
                border_style="dim",
                padding=(0, 1),
            )
        )

    def tool_result(self, name: str, result: str, is_error: bool = False) -> None:
        # Keep tool results compact in the UI (the model still sees full content).
        preview = result if len(result) < 800 else result[:800] + "…"
        style = "red" if is_error else "dim"
        label = "error" if is_error else "result"
        self.console.print(
            Panel(
                preview,
                title=f"[bold]{label} ←[/] [cyan]{name}[/]",
                border_style=style,
                padding=(0, 1),
            )
        )

    # ---- diagnostics -----------------------------------------------------

    def warning(self, message: str) -> None:
        self.console.print(f"[yellow]⚠ {message}[/]")

    def error(self, message: str) -> None:
        self.console.print(f"[bold red]✖ {message}[/]")

    def info(self, message: str) -> None:
        self.console.print(f"[dim]{message}[/]")

    def debug_event(self, label: str, data: Any = None) -> None:
        if not self.debug:
            return
        if data is None:
            self.console.print(f"[dim grey50][debug] {label}[/]")
        else:
            self.console.print(f"[dim grey50][debug] {label}: {data!r}[/]")


class AssistantStream:
    """Handle yielded by Renderer.stream_assistant() for appending deltas."""

    def __init__(self, buffer: list[str], live: Live) -> None:
        self._buffer = buffer
        self._live = live

    def append(self, delta: str) -> None:
        self._buffer.append(delta)
        # Re-render with a plain Text for streaming; final pass uses Markdown.
        self._live.update(Text("".join(self._buffer)))
