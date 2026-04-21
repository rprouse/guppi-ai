"""The agentic loop.

This is the smallest possible correct agent:

    while True:
        stream a message from the model
        for each tool_use block in the response:
            validate args, dispatch via registry, append tool_result
        if the model signaled it's done (stop_reason != "tool_use"):
            return

Streaming details:
  * Text deltas are rendered live as they arrive.
  * tool_use blocks arrive in pieces (`input_json_delta.partial_json`)
    and must be reassembled before we can act on them. We do that by
    accumulating per-block state keyed on the content_block index.
  * The Anthropic SDK exposes an async stream via
    `client.messages.stream(...)` — we iterate raw events rather than
    using the higher-level helpers so we control exactly what gets
    rendered and when.

Error policy:
  * Tool failures return `{"error": "..."}` as the tool_result. Throwing
    here would poison the whole turn; the model recovers gracefully
    when errors come back as data.
  * A hard max_iterations guard prevents infinite tool loops from
    silently burning tokens.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anthropic import AsyncAnthropic

from .config import Settings
from .context import ConversationHistory, clip_tool_result
from .renderer import Renderer
from .tools.registry import ToolRegistry

log = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = """\
You are guppi, a capable agentic CLI assistant running in the user's terminal.

You have tools for running shell commands (`bash`) and reading, writing, and
listing files (`read_file`, `write_file`, `list_dir`). Prefer small, focused
tool calls over mega-commands so the user can follow along. Paths for file
tools resolve relative to the shell's current working directory, which
persists across `bash` calls.

Be concise. You're on a terminal — favor short, scannable replies, code blocks
for code, and no filler. When a task is done, stop; don't narrate."""


class Agent:
    """Owns a client, a registry, a renderer, and a conversation history."""

    def __init__(
        self,
        settings: Settings,
        registry: ToolRegistry,
        renderer: Renderer,
        system_prompt: str,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.renderer = renderer
        self.system_prompt = system_prompt
        self.history = ConversationHistory(max_tokens=settings.max_context_tokens)
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    # ---- public entry point ---------------------------------------------

    async def run_turn(self, user_message: str) -> None:
        """Run a single user turn to completion (may include many tool hops)."""
        self.history.append({"role": "user", "content": user_message})
        self._truncate_and_warn()

        for iteration in range(self.settings.max_iterations):
            self.renderer.debug_event(
                "iteration", f"{iteration + 1}/{self.settings.max_iterations}"
            )

            assistant_content, stop_reason = await self._stream_one_response()
            # Always record what the model said — including any tool_use blocks —
            # *before* we run the tools, so the resulting tool_results slot in
            # next to their matching tool_use blocks.
            self.history.append({"role": "assistant", "content": assistant_content})

            if stop_reason != "tool_use":
                return

            tool_results = await self._execute_tool_uses(assistant_content)
            self.history.append({"role": "user", "content": tool_results})
            self._truncate_and_warn()

        self.renderer.warning(
            f"hit max iterations ({self.settings.max_iterations}); stopping. "
            "The model may not have finished — raise GUPPI_MAX_ITERATIONS if "
            "this was a legitimate long task."
        )

    def clear_history(self) -> None:
        self.history.clear()

    # ---- internals -------------------------------------------------------

    async def _stream_one_response(self) -> tuple[list[dict[str, Any]], str | None]:
        """Issue one streamed API call; return (content_blocks, stop_reason).

        Text is rendered live as it arrives. Tool_use blocks are fully
        assembled (their JSON input arrives in fragments) before being
        returned for dispatch.
        """
        # Per-index buffers. The API sends content blocks out as a sequence
        # of (content_block_start, *deltas, content_block_stop) keyed by index.
        text_buffers: dict[int, list[str]] = {}
        tool_buffers: dict[int, dict[str, Any]] = {}
        block_types: dict[int, str] = {}
        stop_reason: str | None = None

        with self.renderer.stream_assistant() as stream:
            async with self._client.messages.stream(
                model=self.settings.model,
                system=self.system_prompt,
                max_tokens=4096,
                tools=self.registry.get_tool_schemas(),
                messages=self.history.messages,
            ) as response_stream:
                async for event in response_stream:
                    etype = getattr(event, "type", None)
                    self.renderer.debug_event("event", etype)

                    if etype == "content_block_start":
                        idx = event.index
                        block = event.content_block
                        block_types[idx] = block.type
                        if block.type == "text":
                            text_buffers[idx] = []
                        elif block.type == "tool_use":
                            tool_buffers[idx] = {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input_json": [],
                            }

                    elif etype == "content_block_delta":
                        idx = event.index
                        delta = event.delta
                        if delta.type == "text_delta":
                            text_buffers[idx].append(delta.text)
                            stream.append(delta.text)
                        elif delta.type == "input_json_delta":
                            tool_buffers[idx]["input_json"].append(delta.partial_json)

                    elif etype == "message_delta":
                        # stop_reason lands here on the penultimate event.
                        stop_reason = getattr(event.delta, "stop_reason", stop_reason)

        # Assemble the final content blocks in original index order.
        content_blocks: list[dict[str, Any]] = []
        for idx in sorted(block_types):
            if block_types[idx] == "text":
                text = "".join(text_buffers.get(idx, []))
                if text:
                    content_blocks.append({"type": "text", "text": text})
            elif block_types[idx] == "tool_use":
                tb = tool_buffers[idx]
                raw = "".join(tb["input_json"]) or "{}"
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    # Malformed JSON from the model — pass through as-is; the
                    # registry will validate and return a readable error.
                    parsed = {"__raw__": raw}
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": tb["id"],
                        "name": tb["name"],
                        "input": parsed,
                    }
                )

        return content_blocks, stop_reason

    async def _execute_tool_uses(
        self, assistant_content: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Dispatch every tool_use block and return matching tool_result blocks."""
        results: list[dict[str, Any]] = []
        for block in assistant_content:
            if block.get("type") != "tool_use":
                continue

            name = block["name"]
            tool_input = block.get("input") or {}

            self.renderer.tool_call(name, tool_input)
            raw = await self.registry.dispatch(name, tool_input)
            clipped = clip_tool_result(raw, self.settings.tool_result_max_tokens)

            # Heuristic: if the dispatch returned a JSON object with an "error"
            # key, render in red. Content sent to the model is unchanged.
            is_error = False
            try:
                parsed = json.loads(clipped)
                is_error = isinstance(parsed, dict) and "error" in parsed
            except (ValueError, TypeError):
                pass
            self.renderer.tool_result(name, clipped, is_error=is_error)

            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": clipped,
                    "is_error": is_error,
                }
            )
        return results

    def _truncate_and_warn(self) -> None:
        dropped = self.history.truncate_if_needed()
        if dropped:
            self.renderer.warning(
                f"context budget exceeded; dropped {dropped} oldest message(s)"
            )
