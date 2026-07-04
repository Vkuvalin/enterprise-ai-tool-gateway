"""Typed local MCP boundary helpers for Stage 6."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEMO_SYSTEM_STATUS_TOOL = "get_demo_system_status"
MAX_MCP_TIMEOUT_SECONDS = 30.0
_SAFE_TOOL_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}\Z")


class MCPError(RuntimeError):
    """Base MCP boundary error with safe context only."""

    def __init__(
        self,
        safe_message: str,
        *,
        reason_code: str,
        tool_name: str | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.reason_code = reason_code
        self.tool_name = tool_name

    def safe_context(self) -> dict[str, str | None]:
        return {
            "safe_message": self.safe_message,
            "reason_code": self.reason_code,
            "tool_name": _sanitize_tool_name(self.tool_name),
        }

    def __str__(self) -> str:
        return self.safe_message


class MCPConfigurationError(MCPError):
    def __init__(
        self,
        safe_message: str = "MCP boundary is not configured.",
        *,
        reason_code: str = "mcp_configuration_error",
        tool_name: str | None = None,
    ) -> None:
        super().__init__(safe_message, reason_code=reason_code, tool_name=tool_name)


class MCPConnectionError(MCPError):
    def __init__(
        self,
        safe_message: str = "MCP server is unavailable.",
        *,
        reason_code: str = "mcp_connection_error",
        tool_name: str | None = None,
    ) -> None:
        super().__init__(safe_message, reason_code=reason_code, tool_name=tool_name)


class MCPTimeoutError(MCPError):
    def __init__(
        self,
        safe_message: str = "MCP tool call timed out.",
        *,
        reason_code: str = "mcp_timeout",
        tool_name: str | None = None,
    ) -> None:
        super().__init__(safe_message, reason_code=reason_code, tool_name=tool_name)


class MCPToolNotFoundError(MCPError):
    def __init__(
        self,
        safe_message: str = "MCP tool was not found.",
        *,
        reason_code: str = "mcp_tool_not_found",
        tool_name: str | None = None,
    ) -> None:
        super().__init__(safe_message, reason_code=reason_code, tool_name=tool_name)


class MCPToolExecutionError(MCPError):
    def __init__(
        self,
        safe_message: str = "MCP tool execution failed.",
        *,
        reason_code: str = "mcp_tool_execution_error",
        tool_name: str | None = None,
    ) -> None:
        super().__init__(safe_message, reason_code=reason_code, tool_name=tool_name)


class MCPSchemaValidationError(MCPError):
    def __init__(
        self,
        safe_message: str = "MCP tool result failed schema validation.",
        *,
        reason_code: str = "mcp_schema_validation_error",
        tool_name: str | None = None,
    ) -> None:
        super().__init__(safe_message, reason_code=reason_code, tool_name=tool_name)


class DemoSystemStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_id: str = Field(min_length=1, max_length=80)


class DemoSystemStatusOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_id: str
    status: Literal["OK", "DEGRADED"]
    checked_by: Literal["local_fake_mcp"]
    details: dict[str, str] = Field(default_factory=dict)


class MCPToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    output: dict[str, object]


OutputModelT = TypeVar("OutputModelT", bound=BaseModel)
CallToolFunc = Callable[[str, Mapping[str, object]], Awaitable[Any]]
ListToolsFunc = Callable[[], Awaitable[Any]]


class MCPBoundaryClient:
    """Thin typed boundary around an MCP-like async tool transport."""

    def __init__(
        self,
        *,
        list_tools: ListToolsFunc,
        call_tool: CallToolFunc,
        timeout_seconds: float = 2.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise MCPConfigurationError(
                "MCP timeout must be positive.",
                reason_code="mcp_timeout_invalid",
            )
        if timeout_seconds > MAX_MCP_TIMEOUT_SECONDS:
            raise MCPConfigurationError(
                "MCP timeout must not exceed the configured maximum.",
                reason_code="mcp_timeout_invalid",
            )
        self._list_tools = list_tools
        self._call_tool = call_tool
        self._timeout_seconds = timeout_seconds
        self._closed = False

    async def __aenter__(self) -> MCPBoundaryClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        self._closed = True

    async def discover_tools(self) -> list[str]:
        self._ensure_open()
        try:
            raw_tools = await asyncio.wait_for(self._list_tools(), timeout=self._timeout_seconds)
            return _validate_discovered_tools(raw_tools)
        except TimeoutError as exc:
            raise MCPTimeoutError(
                "MCP tool discovery timed out.",
                reason_code="mcp_tool_discovery_timeout",
            ) from exc
        except MCPError:
            raise
        except Exception as exc:
            raise MCPConnectionError(
                "MCP tool discovery failed safely.",
                reason_code="mcp_tool_discovery_failed",
            ) from exc

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, object],
        output_model: type[OutputModelT],
    ) -> MCPToolResult:
        self._ensure_open()
        tool_names = await self.discover_tools()
        if tool_name not in tool_names:
            raise MCPToolNotFoundError(tool_name=tool_name)
        try:
            raw_result = await asyncio.wait_for(
                self._call_tool(tool_name, arguments),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            raise MCPTimeoutError(tool_name=tool_name) from exc
        except MCPError:
            raise
        except Exception as exc:
            raise MCPToolExecutionError(tool_name=tool_name) from exc

        raw_object = extract_mcp_result_object(raw_result, tool_name=tool_name)
        try:
            validated = output_model.model_validate(raw_object)
        except ValidationError as exc:
            raise MCPSchemaValidationError(tool_name=tool_name) from exc
        return MCPToolResult(tool_name=tool_name, output=validated.model_dump(mode="json"))

    def _ensure_open(self) -> None:
        if self._closed:
            raise MCPConnectionError(
                "MCP client is closed.",
                reason_code="mcp_client_closed",
            )


def build_demo_system_status(arguments: Mapping[str, object]) -> DemoSystemStatusOutput:
    """Validate fake tool input and return deterministic output."""

    payload = DemoSystemStatusInput.model_validate(arguments)
    return DemoSystemStatusOutput(
        system_id=payload.system_id,
        status="OK",
        checked_by="local_fake_mcp",
        details={"source": "deterministic-local-fake"},
    )


async def list_demo_mcp_tools() -> list[str]:
    return [DEMO_SYSTEM_STATUS_TOOL]


async def call_demo_mcp_tool_raw(
    tool_name: str,
    arguments: Mapping[str, object],
) -> dict[str, object]:
    if tool_name != DEMO_SYSTEM_STATUS_TOOL:
        raise MCPToolNotFoundError(tool_name=tool_name)
    try:
        return build_demo_system_status(arguments).model_dump(mode="json")
    except ValidationError as exc:
        raise MCPToolExecutionError(
            "MCP demo tool input failed validation.",
            reason_code="mcp_tool_input_invalid",
            tool_name=tool_name,
        ) from exc


def create_local_demo_mcp_client(timeout_seconds: float = 2.0) -> MCPBoundaryClient:
    """Create an offline deterministic MCP boundary client."""

    return MCPBoundaryClient(
        list_tools=list_demo_mcp_tools,
        call_tool=call_demo_mcp_tool_raw,
        timeout_seconds=timeout_seconds,
    )


def extract_mcp_result_object(raw_result: object, *, tool_name: str | None = None) -> dict[str, object]:
    """Extract one object from MCP SDK/local result shapes."""

    _raise_if_error_flagged(raw_result, tool_name=tool_name)
    if isinstance(raw_result, dict):
        return raw_result
    if isinstance(raw_result, str):
        return _loads_mcp_object(raw_result, tool_name=tool_name)

    content = getattr(raw_result, "content", None)
    if isinstance(content, list):
        return _extract_from_content_blocks(content, tool_name=tool_name)

    if isinstance(raw_result, tuple | list):
        for item in raw_result:
            _raise_if_error_flagged(item, tool_name=tool_name)
            if isinstance(item, dict):
                return item
            item_content = getattr(item, "content", None)
            if isinstance(item_content, list):
                return _extract_from_content_blocks(item_content, tool_name=tool_name)
            if isinstance(item, list):
                return _extract_from_content_blocks(item, tool_name=tool_name)

    raise MCPSchemaValidationError(
        "MCP tool result could not be normalized to an object.",
        reason_code="mcp_result_not_object",
        tool_name=tool_name,
    )


def _raise_if_error_flagged(result: object, *, tool_name: str | None) -> None:
    if isinstance(result, dict):
        error_flag = result.get("isError") is True or result.get("is_error") is True
    else:
        error_flag = (
            getattr(result, "isError", False) is True
            or getattr(result, "is_error", False) is True
        )
    if error_flag:
        raise MCPToolExecutionError(
            "MCP tool result was marked as an error.",
            reason_code="mcp_tool_result_error_flagged",
            tool_name=tool_name,
        )


def _extract_from_content_blocks(
    content_blocks: list[object],
    *,
    tool_name: str | None,
) -> dict[str, object]:
    for block in content_blocks:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            return _loads_mcp_object(text, tool_name=tool_name)
    raise MCPSchemaValidationError(
        "MCP tool result did not contain object text.",
        reason_code="mcp_result_text_missing",
        tool_name=tool_name,
    )


def _loads_mcp_object(text: str, *, tool_name: str | None) -> dict[str, object]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MCPSchemaValidationError(
            "MCP tool result text was not valid JSON.",
            reason_code="mcp_result_invalid_json",
            tool_name=tool_name,
        ) from exc
    if not isinstance(parsed, dict):
        raise MCPSchemaValidationError(
            "MCP tool result JSON root was not an object.",
            reason_code="mcp_result_not_object",
            tool_name=tool_name,
        )
    return parsed


def _validate_discovered_tools(raw_tools: object) -> list[str]:
    if not isinstance(raw_tools, list) or not all(isinstance(item, str) for item in raw_tools):
        raise MCPSchemaValidationError(
            "MCP tool discovery returned an invalid tool list.",
            reason_code="mcp_tool_discovery_schema_invalid",
        )
    return cast(list[str], raw_tools)


def _sanitize_tool_name(tool_name: str | None) -> str | None:
    if tool_name is None:
        return None
    if _SAFE_TOOL_NAME_PATTERN.fullmatch(tool_name):
        return tool_name
    return "<redacted>"
