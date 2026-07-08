"""Map API DTOs to application DTOs and API responses."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast, overload
from uuid import UUID

from enterprise_ai_tool_gateway.audit import redact_payload
from enterprise_ai_tool_gateway.api.http.schemas.approvals import ApprovalResolveRequest
from enterprise_ai_tool_gateway.api.http.schemas.runs import (
    ApprovalResponse,
    AuditEventResponse,
    RunDetailResponse,
    RunResponse,
    ToolCallResponse,
)
from enterprise_ai_tool_gateway.api.http.schemas.workflows import (
    AccessSubmitRequest,
    MaintenanceSubmitRequest,
    ProcurementSubmitRequest,
    WorkflowResultResponse,
)
from enterprise_ai_tool_gateway.application import (
    AccessApprovalResolutionRequest,
    AccessWorkflowRequest,
    AccessWorkflowResult,
    MaintenanceApprovalResolutionRequest,
    MaintenanceWorkflowRequest,
    MaintenanceWorkflowResult,
    ProcurementApprovalResolutionRequest,
    ProcurementWorkflowRequest,
    ProcurementWorkflowResult,
)
from enterprise_ai_tool_gateway.contracts.schemas import (
    AgentRunRead,
    ApprovalRead,
    AuditEventRead,
    ToolCallRead,
)

WorkflowResult = (
    AccessWorkflowResult | ProcurementWorkflowResult | MaintenanceWorkflowResult
)


def to_access_workflow_request(request: AccessSubmitRequest) -> AccessWorkflowRequest:
    return AccessWorkflowRequest(**request.model_dump())


def to_procurement_workflow_request(
    request: ProcurementSubmitRequest,
) -> ProcurementWorkflowRequest:
    return ProcurementWorkflowRequest(**request.model_dump())


def to_maintenance_workflow_request(
    request: MaintenanceSubmitRequest,
) -> MaintenanceWorkflowRequest:
    return MaintenanceWorkflowRequest(**request.model_dump())


def to_access_approval_request(
    approval_id: UUID,
    request: ApprovalResolveRequest,
) -> AccessApprovalResolutionRequest:
    return AccessApprovalResolutionRequest(approval_id=approval_id, **request.model_dump())


def to_procurement_approval_request(
    approval_id: UUID,
    request: ApprovalResolveRequest,
) -> ProcurementApprovalResolutionRequest:
    return ProcurementApprovalResolutionRequest(approval_id=approval_id, **request.model_dump())


def to_maintenance_approval_request(
    approval_id: UUID,
    request: ApprovalResolveRequest,
) -> MaintenanceApprovalResolutionRequest:
    return MaintenanceApprovalResolutionRequest(approval_id=approval_id, **request.model_dump())


def workflow_result_to_response(result: WorkflowResult) -> WorkflowResultResponse:
    return WorkflowResultResponse(
        run=agent_run_to_response(result.run),
        final_summary=result.final_summary,
        requires_approval=result.requires_approval,
        approval=approval_to_response(result.approval) if result.approval is not None else None,
        tool_calls=[tool_call_to_response(tool_call) for tool_call in result.tool_calls],
        audit_events=[audit_event_to_response(event) for event in result.audit_events],
    )


def run_detail_to_response(
    run: AgentRunRead,
    *,
    approvals: list[ApprovalRead],
    tool_calls: list[ToolCallRead],
    audit_events: list[AuditEventRead],
) -> RunDetailResponse:
    approval = approvals[-1] if approvals else None
    return RunDetailResponse(
        run=agent_run_to_response(run),
        final_summary=run.final_summary,
        requires_approval=run.requires_approval,
        approval=approval_to_response(approval) if approval is not None else None,
        tool_calls=[tool_call_to_response(tool_call) for tool_call in tool_calls],
        audit_events=[audit_event_to_response(event) for event in audit_events],
    )


def agent_run_to_response(run: AgentRunRead) -> RunResponse:
    return RunResponse(
        id=str(run.id),
        user_id=run.user_id,
        approval_mode=run.approval_mode.value,
        request_type=run.request_type.value,
        domain_template=run.domain_template.value,
        status=run.status.value,
        risk_level=run.risk_level.value if run.risk_level is not None else None,
        requires_approval=run.requires_approval,
        provider_name=run.provider_name.value if run.provider_name is not None else None,
        model_name=run.model_name,
        final_summary=run.final_summary,
        error_type=run.error_type,
        error_message=run.error_message,
        created_at=_iso(run.created_at),
        updated_at=_iso(run.updated_at),
    )


def tool_call_to_response(tool_call: ToolCallRead) -> ToolCallResponse:
    return ToolCallResponse(
        id=str(tool_call.id),
        run_id=str(tool_call.run_id),
        tool_name=tool_call.tool_name,
        tool_type=tool_call.tool_type.value,
        status=tool_call.status.value,
        input_payload=_public_tool_input_payload(tool_call.input_payload),
        output_payload=_public_tool_output_payload(tool_call.output_payload),
        error_message=tool_call.error_message,
        requires_approval=tool_call.requires_approval,
        approval_id=str(tool_call.approval_id) if tool_call.approval_id is not None else None,
        created_at=_iso(tool_call.created_at),
        updated_at=_iso(tool_call.updated_at),
    )


def approval_to_response(approval: ApprovalRead) -> ApprovalResponse:
    return ApprovalResponse(
        id=str(approval.id),
        run_id=str(approval.run_id),
        tool_call_id=str(approval.tool_call_id) if approval.tool_call_id is not None else None,
        status=approval.status.value,
        required_approver_role=approval.required_approver_role,
        summary=_public_approval_text("summary", approval.summary),
        reason=_public_approval_text("reason", approval.reason),
        decided_by=_public_approval_text("decided_by", approval.decided_by),
        decision_comment=_public_approval_text(
            "decision_comment",
            approval.decision_comment,
        ),
        created_at=_iso(approval.created_at),
        updated_at=_iso(approval.updated_at),
    )


def audit_event_to_response(event: AuditEventRead) -> AuditEventResponse:
    return AuditEventResponse(
        id=str(event.id),
        run_id=str(event.run_id),
        event_type=event.event_type.value,
        actor=event.actor,
        payload=dict(event.payload),
        created_at=_iso(event.created_at),
    )


def _iso(value: datetime) -> str:
    return value.isoformat()


def _public_tool_input_payload(payload: Mapping[str, object]) -> dict[str, object]:
    return redact_payload(payload)


def _public_tool_output_payload(payload: Mapping[str, object] | None) -> dict[str, object] | None:
    if payload is None:
        return None
    return redact_payload(payload)


@overload
def _public_approval_text(field_name: str, value: str) -> str: ...


@overload
def _public_approval_text(field_name: str, value: None) -> None: ...


def _public_approval_text(field_name: str, value: str | None) -> str | None:
    if value is None:
        return None
    redacted = redact_payload({field_name: value})[field_name]
    return cast(str, redacted)
