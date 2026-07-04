from __future__ import annotations

import json

import pytest

from enterprise_ai_tool_gateway.mcp import DEMO_SYSTEM_STATUS_TOOL
from enterprise_ai_tool_gateway.mcp import MCPToolExecutionError
from enterprise_ai_tool_gateway.mcp import server as server_module
from enterprise_ai_tool_gateway.mcp.server import (
    call_get_demo_system_status,
    list_demo_tools,
)


@pytest.mark.asyncio
async def test_mcp_demo_tool_is_registered_and_callable() -> None:
    tool_names = await list_demo_tools()
    result = await call_get_demo_system_status("gateway-demo")

    assert DEMO_SYSTEM_STATUS_TOOL in tool_names
    assert result["system_id"] == "gateway-demo"
    assert result["status"] == "OK"


@pytest.mark.asyncio
async def test_call_get_demo_system_status_uses_registered_fastmcp_tool(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_call_tool(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((tool_name, arguments))
        return {
            "system_id": "patched-demo",
            "status": "OK",
            "checked_by": "local_fake_mcp",
            "details": {"source": "patched-fastmcp-path"},
        }

    monkeypatch.setattr(server_module.mcp, "call_tool", fake_call_tool)

    result = await call_get_demo_system_status("gateway-demo")

    assert calls == [(DEMO_SYSTEM_STATUS_TOOL, {"system_id": "gateway-demo"})]
    assert result["system_id"] == "patched-demo"


@pytest.mark.asyncio
async def test_call_get_demo_system_status_rejects_error_flagged_fastmcp_result(
    monkeypatch,
) -> None:
    class TextContent:
        def __init__(self, text: str) -> None:
            self.text = text

    class ErrorResult:
        is_error = True

        def __init__(self) -> None:
            self.content = [
                TextContent(
                    json.dumps(
                        {
                            "system_id": "patched-demo",
                            "status": "OK",
                            "checked_by": "local_fake_mcp",
                        }
                    )
                )
            ]

    async def fake_call_tool(_tool_name: str, _arguments: dict[str, object]) -> ErrorResult:
        return ErrorResult()

    monkeypatch.setattr(server_module.mcp, "call_tool", fake_call_tool)

    with pytest.raises(MCPToolExecutionError) as exc_info:
        await call_get_demo_system_status("gateway-demo")

    assert exc_info.value.reason_code == "mcp_tool_result_error_flagged"
