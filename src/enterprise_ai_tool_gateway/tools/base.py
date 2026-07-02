"""Generic tool boundary contracts."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel, ToolCallStatus, ToolType

ToolHandlerResult: TypeAlias = BaseModel | Mapping[str, object]
ToolHandler: TypeAlias = Callable[[BaseModel], ToolHandlerResult | Awaitable[ToolHandlerResult]]

_TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class InvalidToolDefinitionError(ValueError):
    """Raised when a tool definition violates registry rules."""


class ToolDefinition(BaseModel):
    """Registry-owned definition of one callable capability."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    name: str
    description: str
    tool_type: ToolType
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    risk_level: RiskLevel
    requires_approval_by_default: bool
    handler: ToolHandler

    @field_validator("name")
    @classmethod
    def validate_tool_name(cls, value: str) -> str:
        if not _TOOL_NAME_PATTERN.fullmatch(value):
            raise InvalidToolDefinitionError(
                "Tool names must use lower_snake_case and start with a letter"
            )
        return value

    @field_validator("input_model", "output_model")
    @classmethod
    def validate_model_type(cls, value: type[BaseModel]) -> type[BaseModel]:
        if not isinstance(value, type) or not issubclass(value, BaseModel):
            raise InvalidToolDefinitionError("Tool input_model and output_model must be Pydantic models")
        return value

    @field_validator("handler")
    @classmethod
    def validate_handler(cls, value: ToolHandler) -> ToolHandler:
        if not callable(value):
            raise InvalidToolDefinitionError("Tool handler must be callable")
        return value


class ToolExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    input_payload: dict[str, object] = Field(default_factory=dict)
    execution_authorized: bool = False


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_type: ToolType
    status: ToolCallStatus
    output_payload: dict[str, object] | None = None
    error_message: str | None = None
