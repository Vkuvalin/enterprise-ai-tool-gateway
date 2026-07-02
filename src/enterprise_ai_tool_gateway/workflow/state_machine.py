"""Pure AgentRun workflow transition helpers."""

from __future__ import annotations

from enterprise_ai_tool_gateway.contracts.enums import AgentRunStatus
from enterprise_ai_tool_gateway.workflow.events import WorkflowEventType
from enterprise_ai_tool_gateway.workflow.transitions import (
    BLOCKING_STATUSES,
    TERMINAL_STATUSES,
    TRANSITION_TABLE,
)


class InvalidWorkflowTransitionError(ValueError):
    """Raised when an event is not allowed for the current AgentRun status."""

    def __init__(self, current_status: AgentRunStatus, event_type: WorkflowEventType) -> None:
        super().__init__(
            f"Event {event_type.value} is not allowed from status {current_status.value}"
        )
        self.current_status = current_status
        self.event_type = event_type


def is_terminal_status(status: AgentRunStatus) -> bool:
    return status in TERMINAL_STATUSES


def is_blocking_status(status: AgentRunStatus) -> bool:
    return status in BLOCKING_STATUSES


def can_handle_event(current_status: AgentRunStatus, event_type: WorkflowEventType) -> bool:
    if is_terminal_status(current_status):
        return False
    return (current_status, event_type) in TRANSITION_TABLE


def allowed_events_for(status: AgentRunStatus) -> tuple[WorkflowEventType, ...]:
    if is_terminal_status(status):
        return ()
    return tuple(
        event_type
        for (current_status, event_type), _target_status in TRANSITION_TABLE.items()
        if current_status == status
    )


def transition(current_status: AgentRunStatus, event_type: WorkflowEventType) -> AgentRunStatus:
    if not can_handle_event(current_status, event_type):
        raise InvalidWorkflowTransitionError(current_status, event_type)
    return TRANSITION_TABLE[(current_status, event_type)]
