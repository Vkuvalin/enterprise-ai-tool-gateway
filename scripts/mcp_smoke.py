"""Local MCP stdio smoke for the Stage 3 spike server."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def _run() -> int:
    project_root = Path(__file__).resolve().parents[1]
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "enterprise_ai_tool_gateway.mcp.server"],
        cwd=project_root,
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            if "fake_policy_lookup" not in tool_names:
                print("MCP smoke failed: fake_policy_lookup is not registered.")
                return 1
            result = await session.call_tool(
                "fake_policy_lookup",
                {"request_type": "ACCESS_REQUEST"},
            )
            print(
                "MCP smoke OK: "
                f"tools={tool_names}; "
                f"content_blocks={len(result.content)}; "
                f"is_error={result.isError}"
            )
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
