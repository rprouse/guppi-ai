"""MCP client — stub.

The real implementation will use the official `mcp` Python SDK to
launch a server (stdio or SSE transport), call `list_tools`, and
forward `call_tool` requests. It will then be wired into the
ToolRegistry by `register_mcp_server`.

For now this file exists to lock in the shape of the API so the agent
loop and registry can be written against a stable interface.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class MCPClient:
    """Stub MCP client. Methods log a not-implemented warning and no-op."""

    def __init__(self, server_config: dict[str, Any]) -> None:
        self.server_config = server_config
        self._connected = False

    async def connect(self) -> None:
        log.warning("MCPClient.connect not yet implemented (config=%s)", self.server_config)

    async def list_tools(self) -> list[dict[str, Any]]:
        log.warning("MCPClient.list_tools not yet implemented")
        return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        log.warning("MCPClient.call_tool not yet implemented (name=%s)", name)
        return {"error": "MCP not yet implemented"}

    async def close(self) -> None:
        self._connected = False
