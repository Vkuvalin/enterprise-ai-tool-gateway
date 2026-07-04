"""Shared mechanical helpers for thin demo-template runtimes."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from pydantic import BaseModel, ValidationError

from enterprise_ai_tool_gateway.approval import ApprovalDecision, ApprovalRequirement
from enterprise_ai_tool_gateway.audit import create_audit_event
from enterprise_ai_tool_gateway.contracts.enums import (
    AgentRunStatus,
    ApprovalStatus,
    AuditEventType,
    DomainTemplate,
    PolicyDecisionStatus,
    ProviderName,
    RequestType,
    RiskLevel,
    ToolCallStatus,
    ToolType,
)
from enterprise_ai_tool_gateway.contracts.schemas import (
    AgentRunRead,
    ApprovalCreate,
    ApprovalRead,
    AuditEventRead,
    LLMDecisionCreate,
    LLMDecisionPayload,
    ToolCallCreate,
    ToolCallRead,
)
from enterprise_ai_tool_gateway.db import GatewayRepository
from enterprise_ai_tool_gateway.policy import PolicyCheckRequest, PolicyDecision
from enterprise_ai_tool_gateway.tools import (
    ToolExecutionError,
    ToolExecutionNotAuthorizedError,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutor,
    ToolInputValidationError,
    ToolOutputValidationError,
    ToolRegistry,
    UnknownToolError,
)
from enterprise_ai_tool_gateway.workflow import WorkflowEventType

SAFE_TOOL_BOUNDARY_ERROR = "Tool boundary failure was handled safely."
TOOL_BOUNDARY_EXCEPTIONS = (
    UnknownToolError,
    ToolInputValidationError,
    ToolOutputValidationError,
    ToolExecutionNotAuthorizedError,
    ToolExecutionError,
)

RequiredField = str | tuple[str, ...]
ExpectedToolType = Callable[[str], ToolType]


@dataclass(frozen=True)
class ToolPlanItem:
    tool_name: str
    input_payload: dict[str, object]
    execution_authorized: bool = False
    requires_approval: bool = False


@dataclass(frozen=True)
class RuntimeRecords:
    tool_calls: list[ToolCallRead]
    approval: ApprovalRead | None
    audit_events: list[AuditEventRead]


def find_missing_fields(
    values: Mapping[str, object | None],
    required_fields: Sequence[RequiredField],
) -> list[str]:
    """Return missing scalar fields or missing alternative field groups."""

    missing_fields: list[str] = []
    for field in required_fields:
        if isinstance(field, tuple):
            if all(_is_missing(values.get(option)) for option in field):
                missing_fields.append("/".join(field))
            continue
        if _is_missing(values.get(field)):
            missing_fields.append(field)
    return missing_fields


def validate_allowed_tool_names(
    decision_payload: LLMDecisionPayload,
    allowed_tool_names: set[str],
    registry: ToolRegistry,
) -> list[str]:
    """Return provider-proposed tool names outside this runtime's allowed set."""

    unknown_tool_names = {
        tool.name
        for tool in decision_payload.proposed_tool_calls
        if tool.name not in allowed_tool_names or not registry.has(tool.name)
    }
    return sorted(unknown_tool_names)


def missing_registered_tool_names(
    tool_names: set[str],
    registry: ToolRegistry,
) -> list[str]:
    return sorted(tool_name for tool_name in tool_names if not registry.has(tool_name))


async def persist_llm_decision(
    repo: GatewayRepository,
    run_id: UUID,
    provider_response: object,
) -> tuple[LLMDecisionPayload | None, bool]:
    response_payload = model_dump_json_dict(provider_response)
    try:
        decision_payload = LLMDecisionPayload.model_validate(response_payload)
    except ValidationError:
        await repo.add_llm_decision(
            LLMDecisionCreate(
                run_id=run_id,
                validated_payload={},
                schema_valid=False,
                validation_errors=[{"message": "LLM output validation failed"}],
                confidence=None,
            )
        )
        return None, False

    await repo.add_llm_decision(
        LLMDecisionCreate(
            run_id=run_id,
            schema_version=decision_payload.schema_version,
            validated_payload=decision_payload.model_dump(mode="json"),
            schema_valid=True,
            validation_errors=[],
            confidence=decision_payload.confidence,
        )
    )
    return decision_payload, True


async def persist_audit(
    repo: GatewayRepository,
    run_id: UUID,
    event_type: AuditEventType,
    payload: Mapping[str, object] | None = None,
    *,
    actor: str = "system",
) -> AuditEventRead:
    return await repo.add_audit_event(
        create_audit_event(run_id, event_type, actor=actor, payload=payload)
    )


async def execute_tool_and_persist(
    repo: GatewayRepository,
    executor: ToolExecutor,
    registry: ToolRegistry,
    run_id: UUID,
    plan_item: ToolPlanItem,
    expected_tool_type: ExpectedToolType,
) -> ToolCallRead:
    try:
        definition = registry.get(plan_item.tool_name)
    except UnknownToolError:
        tool_call = await repo.add_tool_call(
            ToolCallCreate(
                run_id=run_id,
                tool_name=plan_item.tool_name,
                tool_type=expected_tool_type(plan_item.tool_name),
                status=ToolCallStatus.FAILED,
                input_payload=plan_item.input_payload,
                output_payload=None,
                error_message=SAFE_TOOL_BOUNDARY_ERROR,
                requires_approval=plan_item.requires_approval,
            )
        )
        await persist_audit(
            repo,
            run_id,
            AuditEventType.TOOL_EXECUTED,
            {"tool_name": plan_item.tool_name, "status": tool_call.status.value},
        )
        return tool_call

    tool_call = await repo.add_tool_call(
        ToolCallCreate(
            run_id=run_id,
            tool_name=plan_item.tool_name,
            tool_type=definition.tool_type,
            status=ToolCallStatus.EXECUTING,
            input_payload=plan_item.input_payload,
            requires_approval=plan_item.requires_approval,
        )
    )
    tool_result = await execute_tool_boundary(
        executor,
        plan_item.tool_name,
        plan_item.input_payload,
        execution_authorized=plan_item.execution_authorized,
        expected_tool_type=expected_tool_type,
    )
    tool_call = await repo.update_tool_call_result(
        tool_call.id,
        status=tool_result.status,
        output_payload=tool_result.output_payload,
        error_message=tool_result.error_message,
    )
    await persist_audit(
        repo,
        run_id,
        AuditEventType.TOOL_EXECUTED,
        {"tool_name": plan_item.tool_name, "status": tool_call.status.value},
    )
    return tool_call


async def execute_read_tool_plan(
    repo: GatewayRepository,
    executor: ToolExecutor,
    registry: ToolRegistry,
    run_id: UUID,
    plan: Sequence[ToolPlanItem],
    expected_tool_type: ExpectedToolType,
) -> dict[str, ToolCallRead]:
    results: dict[str, ToolCallRead] = {}
    for plan_item in plan:
        results[plan_item.tool_name] = await execute_tool_and_persist(
            repo,
            executor,
            registry,
            run_id,
            plan_item,
            expected_tool_type,
        )
    return results


async def execute_existing_tool_call(
    repo: GatewayRepository,
    executor: ToolExecutor,
    run_id: UUID,
    tool_call: ToolCallRead,
    expected_tool_type: ExpectedToolType,
    *,
    execution_authorized: bool,
    audit_payload: dict[str, object] | None = None,
) -> ToolCallRead:
    await repo.update_tool_call_result(
        tool_call.id,
        status=ToolCallStatus.EXECUTING,
        output_payload=None,
        error_message=None,
    )
    tool_result = await execute_tool_boundary(
        executor,
        tool_call.tool_name,
        tool_call.input_payload,
        execution_authorized=execution_authorized,
        expected_tool_type=expected_tool_type,
    )
    updated_tool_call = await repo.update_tool_call_result(
        tool_call.id,
        status=tool_result.status,
        output_payload=tool_result.output_payload,
        error_message=tool_result.error_message,
    )
    payload: dict[str, object] = {
        "tool_name": updated_tool_call.tool_name,
        "status": updated_tool_call.status.value,
    }
    if audit_payload is not None:
        payload.update(audit_payload)
    await persist_audit(repo, run_id, AuditEventType.TOOL_EXECUTED, payload)
    return updated_tool_call


async def execute_tool_boundary(
    executor: ToolExecutor,
    tool_name: str,
    input_payload: dict[str, object],
    *,
    execution_authorized: bool,
    expected_tool_type: ExpectedToolType,
) -> ToolExecutionResult:
    try:
        return await executor.execute(
            ToolExecutionRequest(
                tool_name=tool_name,
                input_payload=input_payload,
                execution_authorized=execution_authorized,
            )
        )
    except TOOL_BOUNDARY_EXCEPTIONS:
        return ToolExecutionResult(
            tool_name=tool_name,
            tool_type=expected_tool_type(tool_name),
            status=ToolCallStatus.FAILED,
            output_payload=None,
            error_message=SAFE_TOOL_BOUNDARY_ERROR,
        )


def build_policy_check_request(
    *,
    tool_name: str,
    risk_level: RiskLevel,
    requires_approval_by_default: bool,
    approval_mode,
    context: dict[str, object] | None = None,
) -> PolicyCheckRequest:
    return PolicyCheckRequest(
        tool_name=tool_name,
        tool_type=ToolType.STATE_CHANGING,
        risk_level=risk_level,
        requires_approval_by_default=requires_approval_by_default,
        approval_mode=approval_mode,
        context=context or {},
    )


def map_policy_decision_to_runtime_step(
    policy_decision: PolicyDecision,
    *,
    action_required: bool = True,
) -> WorkflowEventType:
    if policy_decision.status is PolicyDecisionStatus.ALLOWED:
        if action_required:
            return WorkflowEventType.POLICY_ALLOWED_ACTION
        return WorkflowEventType.POLICY_ALLOWED_NO_ACTION
    if policy_decision.status is PolicyDecisionStatus.REQUIRES_APPROVAL:
        return WorkflowEventType.POLICY_REQUIRES_APPROVAL
    if policy_decision.status is PolicyDecisionStatus.NEEDS_MANUAL_REVIEW:
        return WorkflowEventType.POLICY_MANUAL_REVIEW
    if policy_decision.status is PolicyDecisionStatus.DENIED:
        return WorkflowEventType.POLICY_REJECTED
    raise ValueError("Unsupported policy decision status")


async def create_pending_approval(
    repo: GatewayRepository,
    *,
    run_id: UUID,
    action_tool_name: str,
    action_input_payload: dict[str, object],
    risk_level: RiskLevel,
    approver_role: str,
    summary: str,
    reason_codes: Sequence[str],
) -> ApprovalRead:
    action_tool_call = await repo.add_tool_call(
        ToolCallCreate(
            run_id=run_id,
            tool_name=action_tool_name,
            tool_type=ToolType.STATE_CHANGING,
            status=ToolCallStatus.WAITING_FOR_APPROVAL,
            input_payload=action_input_payload,
            output_payload=None,
            requires_approval=True,
        )
    )
    requirement = ApprovalRequirement(
        run_id=run_id,
        tool_call_id=action_tool_call.id,
        required_approver_role=approver_role,
        summary=summary,
        reason=", ".join(reason_codes) if reason_codes else None,
        risk_level=risk_level,
    )
    approval = await repo.add_approval(
        ApprovalCreate(
            run_id=run_id,
            tool_call_id=action_tool_call.id,
            status=ApprovalStatus.PENDING,
            required_approver_role=requirement.required_approver_role,
            summary=requirement.summary,
            reason=requirement.reason,
        )
    )
    await repo.update_tool_call_result(
        action_tool_call.id,
        status=ToolCallStatus.WAITING_FOR_APPROVAL,
        output_payload=None,
        error_message=None,
        approval_id=approval.id,
    )
    return approval


async def apply_approval_decision(
    repo: GatewayRepository,
    approval: ApprovalRead,
    *,
    status: ApprovalStatus,
    decided_by: str,
    decision_comment: str | None,
) -> tuple[ApprovalDecision, ApprovalRead]:
    decision = ApprovalDecision(
        status=status,
        decided_by=decided_by,
        decision_comment=decision_comment,
        decided_at=datetime.now(UTC),
    )
    updated_approval = await repo.update_approval_decision(
        approval.id,
        status=decision.status,
        decided_by=decision.decided_by or decided_by,
        decision_comment=decision.decision_comment,
    )
    return decision, updated_approval


async def find_waiting_action_tool_call(
    repo: GatewayRepository,
    run_id: UUID,
    approval_id: UUID,
    action_tool_name: str,
) -> ToolCallRead | None:
    tool_calls = await repo.list_tool_calls(run_id)
    for tool_call in tool_calls:
        if (
            tool_call.tool_name == action_tool_name
            and tool_call.status is ToolCallStatus.WAITING_FOR_APPROVAL
            and tool_call.approval_id == approval_id
        ):
            return tool_call
    return None


async def collect_runtime_records(
    repo: GatewayRepository,
    run: AgentRunRead,
    approval: ApprovalRead | None = None,
) -> RuntimeRecords:
    tool_calls = await repo.list_tool_calls(run.id)
    approvals = await repo.list_approvals(run.id)
    audit_events = await repo.list_audit_events(run.id)
    if approval is None and approvals:
        approval = approvals[-1]
    return RuntimeRecords(tool_calls=tool_calls, approval=approval, audit_events=audit_events)


async def create_safe_failed_result(
    repo: GatewayRepository,
    *,
    run_id: UUID,
    status: AgentRunStatus,
    request_type: RequestType,
    domain_template: DomainTemplate,
    provider_name: ProviderName,
    model_name: str,
    final_summary: str,
    error_type: str,
    error_message: str,
    audit_payload: Mapping[str, object] | None = None,
) -> AgentRunRead:
    run = await repo.update_agent_run_result(
        run_id,
        status=status,
        request_type=request_type,
        domain_template=domain_template,
        provider_name=provider_name,
        model_name=model_name,
        final_summary=final_summary,
        error_type=error_type,
        error_message=error_message,
    )
    await persist_audit(repo, run.id, AuditEventType.RUN_FAILED, audit_payload)
    return run


def model_dump_json_dict(model: object) -> dict[str, object]:
    if isinstance(model, BaseModel):
        dumped = model.model_dump(mode="json")
        return cast(dict[str, object], dumped)
    return cast(dict[str, object], model)


def _is_missing(value: object | None) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False
