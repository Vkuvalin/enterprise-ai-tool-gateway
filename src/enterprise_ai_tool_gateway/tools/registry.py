"""In-memory registry for approved tool definitions."""

from __future__ import annotations

from enterprise_ai_tool_gateway.tools.base import ToolDefinition


class DuplicateToolError(ValueError):
    """Raised when a tool is registered more than once."""


class UnknownToolError(KeyError):
    """Raised when a requested tool is not registered."""


class ToolRegistry:
    """Source of truth for tools available to the backend."""

    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise DuplicateToolError(f"Tool {definition.name!r} is already registered")
        self._definitions[definition.name] = definition

    def get(self, tool_name: str) -> ToolDefinition:
        try:
            return self._definitions[tool_name]
        except KeyError as exc:
            raise UnknownToolError(f"Tool {tool_name!r} is not registered") from exc

    def has(self, tool_name: str) -> bool:
        return tool_name in self._definitions

    def list_tools(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._definitions.values())
