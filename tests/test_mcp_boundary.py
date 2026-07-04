from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pytest

from enterprise_ai_tool_gateway.mcp import (
    DEMO_SYSTEM_STATUS_TOOL,
    DemoSystemStatusOutput,
    MCPBoundaryClient,
    MCPConfigurationError,
    MCPConnectionError,
    MCPSchemaValidationError,
    MCPTimeoutError,
    MCPToolExecutionError,
    MCPToolNotFoundError,
    create_local_demo_mcp_client,
)


@pytest.mark.asyncio
async def test_fake_mcp_tool_call_succeeds() -> None:
    async with create_local_demo_mcp_client() as client:
        result = await client.call_tool(
            DEMO_SYSTEM_STATUS_TOOL,
            {"system_id": "gateway-demo"},
            DemoSystemStatusOutput,
        )

    assert result.tool_name == DEMO_SYSTEM_STATUS_TOOL
    assert result.output["status"] == "OK"
    assert result.output["checked_by"] == "local_fake_mcp"


@pytest.mark.asyncio
async def test_unknown_mcp_tool_maps_to_tool_not_found() -> None:
    async with create_local_demo_mcp_client() as client:
        with pytest.raises(MCPToolNotFoundError) as exc_info:
            await client.call_tool("unknown_tool", {}, DemoSystemStatusOutput)

    assert exc_info.value.reason_code == "mcp_tool_not_found"


@pytest.mark.asyncio
async def test_schema_invalid_mcp_response_maps_to_schema_error() -> None:
    async def list_tools() -> list[str]:
        return [DEMO_SYSTEM_STATUS_TOOL]

    async def call_tool(_tool_name: str, _arguments: Mapping[str, object]) -> dict[str, object]:
        return {"system_id": "gateway-demo", "status": "BROKEN"}

    client = MCPBoundaryClient(list_tools=list_tools, call_tool=call_tool)

    with pytest.raises(MCPSchemaValidationError):
        await client.call_tool(DEMO_SYSTEM_STATUS_TOOL, {}, DemoSystemStatusOutput)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_flag_name", ["isError", "is_error"])
async def test_error_flagged_mcp_response_maps_to_execution_error(
    error_flag_name: str,
) -> None:
    async def list_tools() -> list[str]:
        return [DEMO_SYSTEM_STATUS_TOOL]

    async def call_tool(_tool_name: str, _arguments: Mapping[str, object]) -> dict[str, object]:
        return {
            error_flag_name: True,
            "system_id": "gateway-demo",
            "status": "OK",
            "checked_by": "local_fake_mcp",
            "details": {"source": "schema-valid-but-error-flagged"},
        }

    client = MCPBoundaryClient(list_tools=list_tools, call_tool=call_tool)

    with pytest.raises(MCPToolExecutionError) as exc_info:
        await client.call_tool(DEMO_SYSTEM_STATUS_TOOL, {}, DemoSystemStatusOutput)

    assert exc_info.value.reason_code == "mcp_tool_result_error_flagged"


@pytest.mark.asyncio
async def test_timeout_maps_to_timeout_error() -> None:
    async def list_tools() -> list[str]:
        return [DEMO_SYSTEM_STATUS_TOOL]

    async def call_tool(_tool_name: str, _arguments: Mapping[str, object]) -> dict[str, object]:
        await asyncio.Event().wait()
        return {"system_id": "gateway-demo", "status": "OK", "checked_by": "local_fake_mcp"}

    client = MCPBoundaryClient(list_tools=list_tools, call_tool=call_tool, timeout_seconds=0.001)

    with pytest.raises(MCPTimeoutError):
        await client.call_tool(DEMO_SYSTEM_STATUS_TOOL, {}, DemoSystemStatusOutput)


def test_excessive_mcp_timeout_fails_safely() -> None:
    async def list_tools() -> list[str]:
        return [DEMO_SYSTEM_STATUS_TOOL]

    async def call_tool(_tool_name: str, _arguments: Mapping[str, object]) -> dict[str, object]:
        return {"system_id": "gateway-demo", "status": "OK", "checked_by": "local_fake_mcp"}

    with pytest.raises(MCPConfigurationError) as exc_info:
        MCPBoundaryClient(list_tools=list_tools, call_tool=call_tool, timeout_seconds=31.0)

    assert exc_info.value.reason_code == "mcp_timeout_invalid"


@pytest.mark.asyncio
async def test_maximum_mcp_timeout_is_valid() -> None:
    async def list_tools() -> list[str]:
        return [DEMO_SYSTEM_STATUS_TOOL]

    async def call_tool(_tool_name: str, _arguments: Mapping[str, object]) -> dict[str, object]:
        return {"system_id": "gateway-demo", "status": "OK", "checked_by": "local_fake_mcp"}

    client = MCPBoundaryClient(list_tools=list_tools, call_tool=call_tool, timeout_seconds=30.0)

    result = await client.call_tool(DEMO_SYSTEM_STATUS_TOOL, {}, DemoSystemStatusOutput)

    assert result.output["status"] == "OK"


@pytest.mark.asyncio
async def test_server_failure_maps_to_execution_error_without_raw_exception() -> None:
    async def list_tools() -> list[str]:
        return [DEMO_SYSTEM_STATUS_TOOL]

    async def call_tool(_tool_name: str, _arguments: Mapping[str, object]) -> dict[str, object]:
        raise RuntimeError("Traceback Authorization Bearer secret")

    client = MCPBoundaryClient(list_tools=list_tools, call_tool=call_tool)

    with pytest.raises(MCPToolExecutionError) as exc_info:
        await client.call_tool(DEMO_SYSTEM_STATUS_TOOL, {}, DemoSystemStatusOutput)

    error_text = str(exc_info.value)
    assert "Traceback" not in error_text
    assert "Authorization" not in error_text
    assert "secret" not in error_text


@pytest.mark.asyncio
async def test_client_cleanup_close_path_blocks_later_calls() -> None:
    client = create_local_demo_mcp_client()

    await client.close()

    with pytest.raises(MCPConnectionError) as exc_info:
        await client.discover_tools()

    assert exc_info.value.reason_code == "mcp_client_closed"


@pytest.mark.asyncio
async def test_invalid_discover_tools_shape_maps_to_schema_error() -> None:
    async def list_tools() -> dict[str, list[str]]:
        return {"tools": [DEMO_SYSTEM_STATUS_TOOL]}

    async def call_tool(_tool_name: str, _arguments: Mapping[str, object]) -> dict[str, object]:
        return {"system_id": "gateway-demo", "status": "OK", "checked_by": "local_fake_mcp"}

    client = MCPBoundaryClient(list_tools=list_tools, call_tool=call_tool)

    with pytest.raises(MCPSchemaValidationError) as exc_info:
        await client.discover_tools()

    assert exc_info.value.reason_code == "mcp_tool_discovery_schema_invalid"


def test_mcp_safe_context_redacts_unsafe_tool_name() -> None:
    error = MCPToolNotFoundError(tool_name="Authorization Bearer secret-token")

    context = error.safe_context()

    assert context["tool_name"] == "<redacted>"
    assert "secret-token" not in str(context)


@pytest.mark.asyncio
async def test_local_demo_mcp_boundary_has_no_external_tool_names() -> None:
    async with create_local_demo_mcp_client() as client:
        tools = await client.discover_tools()

    assert tools == [DEMO_SYSTEM_STATUS_TOOL]
