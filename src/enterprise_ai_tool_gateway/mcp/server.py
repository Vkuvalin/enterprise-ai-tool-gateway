"""Minimal MCP server spike with one fake local tool."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "enterprise-ai-tool-gateway-spike",
    instructions="Local spike server exposing one safe fake tool.",
)


@mcp.tool()
def fake_policy_lookup(request_type: str) -> dict[str, Any]:
    """Return deterministic policy metadata for one request type."""

    normalized = request_type.strip().upper() or "UNKNOWN"
    requires_approval = normalized in {
        "ACCESS_REQUEST",
        "PROCUREMENT_REQUEST",
        "MAINTENANCE_REQUEST",
    }
    return {
        "request_type": normalized,
        "requires_approval": requires_approval,
        "policy_version": "stage3-spike",
    }


async def list_spike_tools() -> list[str]:
    """List tools registered on the spike MCP server."""

    tools = await mcp.list_tools()
    return [tool.name for tool in tools]


async def call_fake_policy_lookup(request_type: str) -> dict[str, Any]:
    """Call the fake tool through FastMCP's local tool path."""

    result = await mcp.call_tool("fake_policy_lookup", {"request_type": request_type})
    if isinstance(result, dict):
        return result
    if isinstance(result, tuple):
        for item in result:
            if isinstance(item, dict):
                return item
            if isinstance(item, list):
                for content_block in item:
                    text = getattr(content_block, "text", None)
                    if isinstance(text, str):
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            return parsed
    raise TypeError(f"Unexpected MCP tool result type: {type(result).__name__}")


if __name__ == "__main__":
    mcp.run("stdio")
