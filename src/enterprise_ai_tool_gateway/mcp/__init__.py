"""Optional local MCP boundary."""

from enterprise_ai_tool_gateway.mcp.boundary import (
    DEMO_SYSTEM_STATUS_TOOL,
    DemoSystemStatusInput,
    DemoSystemStatusOutput,
    MCPBoundaryClient,
    MCPConfigurationError,
    MCPConnectionError,
    MCPError,
    MCPSchemaValidationError,
    MCPTimeoutError,
    MCPToolExecutionError,
    MCPToolNotFoundError,
    MCPToolResult,
    build_demo_system_status,
    create_local_demo_mcp_client,
)

__all__ = [
    "DEMO_SYSTEM_STATUS_TOOL",
    "DemoSystemStatusInput",
    "DemoSystemStatusOutput",
    "MCPBoundaryClient",
    "MCPConfigurationError",
    "MCPConnectionError",
    "MCPError",
    "MCPSchemaValidationError",
    "MCPTimeoutError",
    "MCPToolExecutionError",
    "MCPToolNotFoundError",
    "MCPToolResult",
    "build_demo_system_status",
    "create_local_demo_mcp_client",
]
