"""Tool registry and dispatcher.

The registry is the single seam between the agent loop and any tool
implementation. This is the *one* interface the loop calls. Adding a
new tool — builtin Python, local script, or (eventually) an MCP server
— means registering it here, and nothing in `agent.py` needs to know.

Responsibilities:
  * Maintain a name → handler map.
  * Convert pydantic input models to Anthropic-compatible schemas.
  * Validate tool_use inputs via the pydantic model before dispatch, so
    the agent gets back a clean error message (not a stack trace) when
    the model hallucinates a bad argument shape.
  * Route `tool_use` blocks to the right handler and return the result
    as a string (the agent loop wraps it in the tool_result block).

The MCP stub lives here too. When MCP lands, `register_mcp_server` will
connect to a server, call `list_tools`, and register each remote tool
under a namespaced name (e.g. `linear__create_issue`).
"""

from __future__ import annotations

import inspect
import json
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError


class _ToolHandler(Protocol):
    """A registered tool exposes name, description, pydantic input model, and is callable."""

    name: str
    description: str
    input_model: type[BaseModel]

    async def __call__(self, **kwargs: Any) -> Any: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, _ToolHandler] = {}
        # Future: set of "always inject" tool names vs. "details on demand".
        # See the note at the bottom of this file.

    # ---- registration ----------------------------------------------------

    def register(self, handler: _ToolHandler) -> None:
        if handler.name in self._handlers:
            raise ValueError(f"tool already registered: {handler.name}")
        self._handlers[handler.name] = handler

    def register_mcp_server(self, server_config: dict[str, Any]) -> None:
        """Stub: register all tools from a remote MCP server.

        When implemented, this will spawn the server via
        `mcp.stdio_client`, call `list_tools()`, and add each remote
        tool here under a prefixed name so collisions with builtins are
        impossible.
        """
        import logging

        logging.getLogger(__name__).warning(
            "MCP not yet implemented; ignoring server config: %s", server_config
        )

    # ---- introspection ---------------------------------------------------

    def names(self) -> list[str]:
        return list(self._handlers)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return Anthropic-format tool definitions for all registered tools."""
        schemas: list[dict[str, Any]] = []
        for h in self._handlers.values():
            schemas.append(
                {
                    "name": h.name,
                    "description": h.description,
                    "input_schema": h.input_model.model_json_schema(),
                }
            )
        return schemas

    # ---- dispatch --------------------------------------------------------

    async def dispatch(self, name: str, raw_input: dict[str, Any]) -> str:
        """Validate `raw_input` against the tool's model and invoke.

        Returns a string suitable for a `tool_result.content`. Errors
        become structured error strings — we never throw back into the
        agent loop because the model recovers better from "here is the
        error as your tool result" than from a crashed turn.
        """
        handler = self._handlers.get(name)
        if handler is None:
            return json.dumps({"error": f"unknown tool: {name}"})

        try:
            validated = handler.input_model(**raw_input)
        except ValidationError as ve:
            return json.dumps(
                {
                    "error": "invalid tool arguments",
                    "tool": name,
                    "details": json.loads(ve.json()),
                }
            )

        kwargs = validated.model_dump()
        try:
            result = handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:  # noqa: BLE001 — we surface every error to the model.
            return json.dumps(
                {"error": f"{type(e).__name__}: {e}", "tool": name}
            )

        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, default=str)
        except (TypeError, ValueError) as e:
            return json.dumps(
                {"error": f"tool returned non-serializable result: {e}", "tool": name}
            )


# ---------------------------------------------------------------------------
# FUTURE: tiered tool injection
#
# Today every tool's full schema is sent on every turn. With N builtins +
# M MCP tools that grows fast. The planned evolution:
#
#   1. Always inject: tool *name* + one-line description for every tool.
#   2. A meta-tool `get_tool_details(tool_names: list[str])` returns the
#      full input_schema for the named tools on demand.
#   3. The agent loop lazily appends those details to the next request.
#
# This keeps the top-of-prompt tool list cheap while preserving the
# model's ability to discover any tool it needs.
# ---------------------------------------------------------------------------


def build_default_registry(bash_timeout: int) -> ToolRegistry:
    """Factory: construct a registry with all builtin tools wired up."""
    from .builtin.bash import BashTool
    from .builtin.files import ListDirTool, ReadFileTool, WriteFileTool

    registry = ToolRegistry()
    bash = BashTool(default_timeout=bash_timeout)
    registry.register(bash)
    registry.register(ReadFileTool(bash))
    registry.register(WriteFileTool(bash))
    registry.register(ListDirTool(bash))
    return registry
