"""Declarative AgentRun transition table."""

from __future__ import annotations

from enterprise_ai_tool_gateway.contracts.enums import AgentRunStatus
from enterprise_ai_tool_gateway.workflow.events import WorkflowEventType

TERMINAL_STATUSES = frozenset(
    {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED_PROVIDER,
        AgentRunStatus.FAILED_VALIDATION,
        AgentRunStatus.FAILED_TOOL,
        AgentRunStatus.REJECTED,
        AgentRunStatus.NEEDS_MANUAL_REVIEW,
    }
)

BLOCKING_STATUSES = frozenset(
    {
        AgentRunStatus.NEEDS_USER_INPUT,
        AgentRunStatus.WAITING_FOR_APPROVAL,
    }
)

TRANSITION_TABLE: dict[tuple[AgentRunStatus, WorkflowEventType], AgentRunStatus] = {
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
