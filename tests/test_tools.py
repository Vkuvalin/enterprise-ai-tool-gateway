from __future__ import annotations

from typing import cast

import pytest
from pydantic import BaseModel, ValidationError

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel, ToolCallStatus, ToolType
from enterprise_ai_tool_gateway.tools import (
    DuplicateToolError,
    ToolDefinition,
    ToolExecutionNotAuthorizedError,
    ToolExecutionRequest,
    ToolExecutor,
    ToolInputValidationError,
    ToolOutputValidationError,
    ToolRegistry,
    UnknownToolError,
)
from enterprise_ai_tool_gateway.tools.base import ToolHandler


class EchoInput(BaseModel):
    text: str


class EchoOutput(BaseModel):
    text: str


def echo_handler(payload: BaseModel) -> dict[str, object]:
    echo_input = cast(EchoInput, payload)
    return {"text": echo_input.text}


async def async_echo_handler(payload: BaseModel) -> dict[str, object]:
    echo_input = cast(EchoInput, payload)
    return {"text": f"async:{echo_input.text}"}


def invalid_output_handler(_payload: BaseModel) -> dict[str, object]:
    return {"unexpected": "value"}


def failing_handler(_payload: BaseModel) -> dict[str, object]:
    raise RuntimeError("internal implementation detail")


def make_definition(
    *,
    name: str = "echo_tool",
    tool_type: ToolType = ToolType.READ_ONLY,
    handler: ToolHandler = echo_handler,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="Echo input text.",
        tool_type=tool_type,
        input_model=EchoInput,
        output_model=EchoOutput,
        risk_level=RiskLevel.LOW,
        requires_approval_by_default=False,
        handler=handler,
    )


def test_register_tool() -> None:
    registry = ToolRegistry()
    definition = make_definition()

    registry.register(definition)

    assert registry.has("echo_tool") is True
    assert registry.get("echo_tool") == definition
    assert registry.list_tools() == (definition,)


def test_duplicate_registration_rejected() -> None:
    registry = ToolRegistry()
    registry.register(make_definition())

    with pytest.raises(DuplicateToolError):
        registry.register(make_definition())


def test_unknown_tool_rejected() -> None:
    registry = ToolRegistry()

    with pytest.raises(UnknownToolError):
        registry.get("missing_tool")


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "Bad Tool Name"},
        {"input_model": dict},
        {"output_model": dict},
        {"handler": "not-callable"},
    ],
)
def test_invalid_tool_definition_validation_behavior(overrides: dict[str, object]) -> None:
    payload = {
        "name": "echo_tool",
        "description": "Echo input text.",
        "tool_type": ToolType.READ_ONLY,
        "input_model": EchoInput,
        "output_model": EchoOutput,
        "risk_level": RiskLevel.LOW,
        "requires_approval_by_default": False,
        "handler": echo_handler,
    } | overrides

    with pytest.raises(ValidationError):
        ToolDefinition.model_validate(payload)


@pytest.mark.asyncio
async def test_input_validation() -> None:
    registry = ToolRegistry()
    registry.register(make_definition())
    executor = ToolExecutor(registry)

    with pytest.raises(ToolInputValidationError):
        await executor.execute(
            ToolExecutionRequest(tool_name="echo_tool", input_payload={"missing": "text"})
        )


@pytest.mark.asyncio
async def test_output_validation() -> None:
    registry = ToolRegistry()
    registry.register(make_definition(handler=invalid_output_handler))
    executor = ToolExecutor(registry)

    with pytest.raises(ToolOutputValidationError):
        await executor.execute(ToolExecutionRequest(tool_name="echo_tool", input_payload={"text": "ok"}))


@pytest.mark.asyncio
async def test_read_only_execution_success() -> None:
    registry = ToolRegistry()
    registry.register(make_definition())
    executor = ToolExecutor(registry)

    result = await executor.execute(
        ToolExecutionRequest(tool_name="echo_tool", input_payload={"text": "ok"})
    )

    assert result.status is ToolCallStatus.SUCCEEDED
    assert result.output_payload == {"text": "ok"}


@pytest.mark.asyncio
async def test_async_handler_execution_success() -> None:
    registry = ToolRegistry()
    registry.register(make_definition(handler=async_echo_handler))
    executor = ToolExecutor(registry)

    result = await executor.execute(
        ToolExecutionRequest(tool_name="echo_tool", input_payload={"text": "ok"})
    )

    assert result.status is ToolCallStatus.SUCCEEDED
    assert result.output_payload == {"text": "async:ok"}


@pytest.mark.asyncio
async def test_state_changing_execution_blocked_without_authorization() -> None:
    registry = ToolRegistry()
    registry.register(make_definition(tool_type=ToolType.STATE_CHANGING))
    executor = ToolExecutor(registry)

    with pytest.raises(ToolExecutionNotAuthorizedError):
        await executor.execute(
            ToolExecutionRequest(tool_name="echo_tool", input_payload={"text": "ok"})
        )


@pytest.mark.asyncio
async def test_authorized_state_changing_execution_success() -> None:
    registry = ToolRegistry()
    registry.register(make_definition(tool_type=ToolType.STATE_CHANGING))
    executor = ToolExecutor(registry)

    result = await executor.execute(
        ToolExecutionRequest(
            tool_name="echo_tool",
            input_payload={"text": "ok"},
            execution_authorized=True,
        )
    )

    assert result.status is ToolCallStatus.SUCCEEDED
    assert result.output_payload == {"text": "ok"}


@pytest.mark.asyncio
async def test_handler_error_handled_safely() -> None:
    registry = ToolRegistry()
    registry.register(make_definition(handler=failing_handler))
    executor = ToolExecutor(registry)

    result = await executor.execute(
        ToolExecutionRequest(tool_name="echo_tool", input_payload={"text": "ok"})
    )

    assert result.status is ToolCallStatus.FAILED
    assert result.error_message == "Tool execution failed"
    assert result.output_payload is None
