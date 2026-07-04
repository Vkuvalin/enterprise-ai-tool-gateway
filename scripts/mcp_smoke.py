"""Local fake MCP boundary smoke for Stage 6."""

from __future__ import annotations

import asyncio

from enterprise_ai_tool_gateway.mcp import (
    DEMO_SYSTEM_STATUS_TOOL,
    DemoSystemStatusOutput,
    MCPBoundaryClient,
    MCPError,
    MCPSchemaValidationError,
    MCPToolNotFoundError,
    create_local_demo_mcp_client,
)
from enterprise_ai_tool_gateway.mcp.server import call_get_demo_system_status, list_demo_tools


async def _run() -> int:
    checks: dict[str, str] = {}
    try:
        async with create_local_demo_mcp_client() as client:
            checks["local_boundary"] = "ok"
            tools = await client.discover_tools()
            checks["tool_discovery"] = "ok" if DEMO_SYSTEM_STATUS_TOOL in tools else "fail"
            result = await client.call_tool(
                DEMO_SYSTEM_STATUS_TOOL,
                {"system_id": "gateway-demo"},
                DemoSystemStatusOutput,
            )
            checks["tool_call"] = "ok" if result.output["status"] == "OK" else "fail"

        fastmcp_tools = await list_demo_tools()
        fastmcp_result = await call_get_demo_system_status("gateway-demo")
        checks["fastmcp_tool"] = (
            "ok"
            if DEMO_SYSTEM_STATUS_TOOL in fastmcp_tools and fastmcp_result["status"] == "OK"
            else "fail"
        )
        checks["schema_validation"] = await _schema_validation_check()
        checks["safe_error_mapping"] = await _safe_error_mapping_check()
    except MCPError as exc:
        checks.setdefault("local_boundary", "fail")
        checks.setdefault("fastmcp_tool", "fail")
        checks.setdefault("tool_discovery", "fail")
        checks.setdefault("tool_call", "fail")
        checks.setdefault("schema_validation", "fail")
        checks.setdefault("safe_error_mapping", f"fail:{exc.reason_code}")

    print(
        "local_boundary | fastmcp_tool | tool_discovery | tool_call | schema_validation | safe_error_mapping"
    )
    print(
        " | ".join(
            [
                checks.get("local_boundary", "fail"),
                checks.get("fastmcp_tool", "fail"),
                checks.get("tool_discovery", "fail"),
                checks.get("tool_call", "fail"),
                checks.get("schema_validation", "fail"),
                checks.get("safe_error_mapping", "fail"),
            ]
        )
    )
    return 0 if all(value == "ok" for value in checks.values()) else 1


async def _schema_validation_check() -> str:
    async def list_tools() -> list[str]:
        return [DEMO_SYSTEM_STATUS_TOOL]

    async def invalid_call(_tool_name: str, _arguments: object) -> dict[str, object]:
        return {"system_id": "gateway-demo", "status": "BROKEN"}

    client = MCPBoundaryClient(list_tools=list_tools, call_tool=invalid_call)
    try:
        await client.call_tool(DEMO_SYSTEM_STATUS_TOOL, {}, DemoSystemStatusOutput)
    except MCPSchemaValidationError:
        return "ok"
    return "fail"


async def _safe_error_mapping_check() -> str:
    async with create_local_demo_mcp_client() as client:
        try:
            await client.call_tool("missing_tool", {}, DemoSystemStatusOutput)
        except MCPToolNotFoundError as exc:
            unsafe_markers = ("Traceback", "Authorization", "Bearer", "secret")
            return "ok" if not any(marker in str(exc) for marker in unsafe_markers) else "fail"
    return "fail"


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
