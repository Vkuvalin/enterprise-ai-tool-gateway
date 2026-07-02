from __future__ import annotations

import pytest

from enterprise_ai_tool_gateway.contracts.enums import AgentRunStatus
from enterprise_ai_tool_gateway.workflow import (
    BLOCKING_STATUSES,
    TERMINAL_STATUSES,
    TRANSITION_TABLE,
    InvalidWorkflowTransitionError,
    WorkflowEventType,
    can_handle_event,
    is_blocking_status,
    is_terminal_status,
    transition,
)

EXPECTED_TRANSITION_TABLE = {
    (AgentRunStatus.CREATED, WorkflowEventType.START_CLASSIFICATION): AgentRunStatus.CLASSIFYING,
    (
        AgentRunStatus.CLASSIFYING,
        WorkflowEventType.PROVIDER_DECISION_RECEIVED,
    ): AgentRunStatus.DECISION_VALIDATION,
    (AgentRunStatus.CLASSIFYING, WorkflowEventType.PROVIDER_FAILED): AgentRunStatus.FAILED_PROVIDER,
    (
        AgentRunStatus.CLASSIFYING,
        WorkflowEventType.MANUAL_REVIEW_REQUIRED,
    ): AgentRunStatus.NEEDS_MANUAL_REVIEW,
    (
        AgentRunStatus.DECISION_VALIDATION,
        WorkflowEventType.DECISION_VALID,
    ): AgentRunStatus.TOOL_PLANNING,
    (
        AgentRunStatus.DECISION_VALIDATION,
        WorkflowEventType.DECISION_MISSING_INPUT,
    ): AgentRunStatus.NEEDS_USER_INPUT,
    (
        AgentRunStatus.DECISION_VALIDATION,
        WorkflowEventType.DECISION_INVALID,
    ): AgentRunStatus.FAILED_VALIDATION,
    (
        AgentRunStatus.DECISION_VALIDATION,
        WorkflowEventType.MANUAL_REVIEW_REQUIRED,
    ): AgentRunStatus.NEEDS_MANUAL_REVIEW,
    (
        AgentRunStatus.NEEDS_USER_INPUT,
        WorkflowEventType.USER_INPUT_RECEIVED,
    ): AgentRunStatus.DECISION_VALIDATION,
    (
        AgentRunStatus.TOOL_PLANNING,
        WorkflowEventType.TOOL_PLAN_CREATED,
    ): AgentRunStatus.TOOL_VALIDATION,
    (
        AgentRunStatus.TOOL_PLANNING,
        WorkflowEventType.NO_TOOLS_REQUIRED,
    ): AgentRunStatus.POLICY_CHECK,
    (
        AgentRunStatus.TOOL_PLANNING,
        WorkflowEventType.MANUAL_REVIEW_REQUIRED,
    ): AgentRunStatus.NEEDS_MANUAL_REVIEW,
    (
        AgentRunStatus.TOOL_VALIDATION,
        WorkflowEventType.TOOL_PLAN_VALID,
    ): AgentRunStatus.EXECUTING_READ_TOOLS,
    (
        AgentRunStatus.TOOL_VALIDATION,
        WorkflowEventType.TOOL_PLAN_INVALID,
    ): AgentRunStatus.FAILED_VALIDATION,
    (
        AgentRunStatus.TOOL_VALIDATION,
        WorkflowEventType.MANUAL_REVIEW_REQUIRED,
    ): AgentRunStatus.NEEDS_MANUAL_REVIEW,
    (
        AgentRunStatus.EXECUTING_READ_TOOLS,
        WorkflowEventType.READ_TOOLS_EXECUTED,
    ): AgentRunStatus.POLICY_CHECK,
    (
        AgentRunStatus.EXECUTING_READ_TOOLS,
        WorkflowEventType.TOOL_EXECUTION_FAILED,
    ): AgentRunStatus.FAILED_TOOL,
    (
        AgentRunStatus.POLICY_CHECK,
        WorkflowEventType.POLICY_ALLOWED_NO_ACTION,
    ): AgentRunStatus.COMPLETED,
    (
        AgentRunStatus.POLICY_CHECK,
        WorkflowEventType.POLICY_ALLOWED_ACTION,
    ): AgentRunStatus.EXECUTING_ACTION,
    (
        AgentRunStatus.POLICY_CHECK,
        WorkflowEventType.POLICY_REQUIRES_APPROVAL,
    ): AgentRunStatus.WAITING_FOR_APPROVAL,
    (AgentRunStatus.POLICY_CHECK, WorkflowEventType.POLICY_REJECTED): AgentRunStatus.REJECTED,
    (
        AgentRunStatus.POLICY_CHECK,
        WorkflowEventType.POLICY_MANUAL_REVIEW,
    ): AgentRunStatus.NEEDS_MANUAL_REVIEW,
    (
        AgentRunStatus.WAITING_FOR_APPROVAL,
        WorkflowEventType.APPROVAL_APPROVED,
    ): AgentRunStatus.EXECUTING_ACTION,
    (
        AgentRunStatus.WAITING_FOR_APPROVAL,
        WorkflowEventType.APPROVAL_REJECTED,
    ): AgentRunStatus.REJECTED,
    (
        AgentRunStatus.EXECUTING_ACTION,
        WorkflowEventType.ACTION_EXECUTED,
    ): AgentRunStatus.COMPLETED,
    (
        AgentRunStatus.EXECUTING_ACTION,
        WorkflowEventType.ACTION_FAILED,
    ): AgentRunStatus.FAILED_TOOL,
}


def test_transition_table_matches_stage_brief_contract() -> None:
    assert TRANSITION_TABLE == EXPECTED_TRANSITION_TABLE


def test_valid_event_transitions() -> None:
    assert (
        transition(AgentRunStatus.CREATED, WorkflowEventType.START_CLASSIFICATION)
        is AgentRunStatus.CLASSIFYING
    )
    assert (
        transition(AgentRunStatus.POLICY_CHECK, WorkflowEventType.POLICY_ALLOWED_NO_ACTION)
        is AgentRunStatus.COMPLETED
    )
    assert (
        transition(AgentRunStatus.WAITING_FOR_APPROVAL, WorkflowEventType.APPROVAL_APPROVED)
        is AgentRunStatus.EXECUTING_ACTION
    )


def test_invalid_event_rejected() -> None:
    assert (
        can_handle_event(AgentRunStatus.CREATED, WorkflowEventType.APPROVAL_APPROVED)
        is False
    )
    with pytest.raises(InvalidWorkflowTransitionError):
        transition(AgentRunStatus.CREATED, WorkflowEventType.APPROVAL_APPROVED)


def test_terminal_statuses_reject_events() -> None:
    for status in TERMINAL_STATUSES:
        assert is_terminal_status(status) is True
        assert can_handle_event(status, WorkflowEventType.START_CLASSIFICATION) is False
        with pytest.raises(InvalidWorkflowTransitionError):
            transition(status, WorkflowEventType.START_CLASSIFICATION)


def test_blocking_statuses_are_not_terminal() -> None:
    for status in BLOCKING_STATUSES:
        assert is_blocking_status(status) is True
        assert is_terminal_status(status) is False


def test_every_transition_target_is_valid_agent_run_status() -> None:
    valid_statuses = set(AgentRunStatus)

    assert TRANSITION_TABLE
    for target_status in TRANSITION_TABLE.values():
        assert target_status in valid_statuses
