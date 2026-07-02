"""Safe tool execution boundary."""

from __future__ import annotations

from inspect import isawaitable
from typing import cast

from pydantic import BaseModel, ValidationError

from enterprise_ai_tool_gateway.contracts.enums import ToolCallStatus, ToolType
from enterprise_ai_tool_gateway.tools.base import (
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolHandlerResult,
)
from enterprise_ai_tool_gateway.tools.registry import ToolRegistry


class ToolInputValidationError(ValueError):
    """Raised when a tool input payload does not match the registered schema."""


class ToolOutputValidationError(ValueError):
    """Raised when a tool handler returns output outside the registered schema."""


class ToolExecutionError(RuntimeError):
    """Raised for unsafe tool execution failures."""


class ToolExecutionNotAuthorizedError(PermissionError):
    """Raised when a state-changing tool is called without authorization."""


class ToolExecutor:
    """Validate, authorize, execute, and validate one registered tool call."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        definition = self._registry.get(request.tool_name)
        try:
            validated_input = definition.input_model.model_validate(request.input_payload)
        except ValidationError as exc:
            raise ToolInputValidationError("Tool input validation failed") from exc

        if definition.tool_type is not ToolType.READ_ONLY and not request.execution_authorized:
            raise ToolExecutionNotAuthorizedError(
                f"Tool {definition.name!r} requires execution authorization"
            )

        try:
            handler_result = definition.handler(validated_input)
            if isawaitable(handler_result):
                handler_result = await handler_result
        except Exception:
            return ToolExecutionResult(
                tool_name=definition.name,
                tool_type=definition.tool_type,
                status=ToolCallStatus.FAILED,
                output_payload=None,
                error_message="Tool execution failed",
            )

        try:
            output_payload = _validate_output(definition.output_model, handler_result)
        except ValidationError as exc:
            raise ToolOutputValidationError("Tool output validation failed") from exc

        return ToolExecutionResult(
            tool_name=definition.name,
            tool_type=definition.tool_type,
            status=ToolCallStatus.SUCCEEDED,
            output_payload=output_payload,
            error_message=None,
        )


def _validate_output(
    output_model: type[BaseModel],
    handler_result: ToolHandlerResult,
) -> dict[str, object]:
    if isinstance(handler_result, BaseModel):
        output_candidate = handler_result.model_dump(mode="python")
    else:
        output_candidate = handler_result
    validated_output = output_model.model_validate(output_candidate)
    return cast(dict[str, object], validated_output.model_dump(mode="json"))
