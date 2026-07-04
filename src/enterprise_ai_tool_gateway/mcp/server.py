"""Local deterministic fake MCP server for Stage 6 boundary checks."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from enterprise_ai_tool_gateway.mcp.boundary import (
    DEMO_SYSTEM_STATUS_TOOL,
    DemoSystemStatusOutput,
    MCPSchemaValidationError,
    build_demo_system_status,
    extract_mcp_result_object,
)

mcp = FastMCP(
    "enterprise-ai-tool-gateway-local-demo",
    instructions="Local fake MCP boundary exposing deterministic non-enterprise tools.",
)


@mcp.tool()
def get_demo_system_status(system_id: str = "gateway-demo") -> dict[str, Any]:
    """Return deterministic fake system status for MCP boundary validation."""

    return build_demo_system_status({"system_id": system_id}).model_dump(mode="json")


async def list_demo_tools() -> list[str]:
    """List tools available through the local fake boundary."""

    tools = await mcp.list_tools()
    return [tool.name for tool in tools]


async def call_get_demo_system_status(system_id: str = "gateway-demo") -> dict[str, object]:
    """Call and validate the fake MCP tool through the registered FastMCP path."""

    raw_result = await mcp.call_tool(DEMO_SYSTEM_STATUS_TOOL, {"system_id": system_id})
    raw_object = extract_mcp_result_object(raw_result, tool_name=DEMO_SYSTEM_STATUS_TOOL)
    try:
        validated = DemoSystemStatusOutput.model_validate(raw_object)
    except ValidationError as exc:
        raise MCPSchemaValidationError(tool_name=DEMO_SYSTEM_STATUS_TOOL) from exc
    return validated.model_dump(mode="json")


if __name__ == "__main__":
    mcp.run("stdio")
