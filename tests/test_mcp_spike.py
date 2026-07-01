from __future__ import annotations

import pytest

from enterprise_ai_tool_gateway.mcp.server import (
    call_fake_policy_lookup,
    list_spike_tools,
)


@pytest.mark.asyncio
async def test_mcp_fake_tool_is_registered_and_callable() -> None:
    tool_names = await list_spike_tools()
    result = await call_fake_policy_lookup("ACCESS_REQUEST")

    assert "fake_policy_lookup" in tool_names
    assert result["request_type"] == "ACCESS_REQUEST"
    assert result["requires_approval"] is True
