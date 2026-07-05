"""Run and related-record response schemas."""

from __future__ import annotations

from enterprise_ai_tool_gateway.api.http.schemas.common import ApiModel


class RunResponse(ApiModel):
    id: str
    user_id: str
    approval_mode: str
    request_type: str
    domain_template: str
    status: str
    risk_level: str | None = None
    requires_approval: bool
    provider_name: str | None = None
    model_name: str | None = None
    final_summary: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str


class ToolCallResponse(ApiModel):
    id: str
    run_id: str
    tool_name: str
    tool_type: str
    status: str
    input_payload: dict[str, object]
    output_payload: dict[str, object] | None = None
    error_message: str | None = None
    requires_approval: bool
    approval_id: str | None = None
    created_at: str
    updated_at: str


class ApprovalResponse(ApiModel):
    id: str
    run_id: str
    tool_call_id: str | None = None
    status: str
    required_approver_role: str
    summary: str
    reason: str | None = None
    decided_by: str | None = None
    decision_comment: str | None = None
    created_at: str
    updated_at: str


class AuditEventResponse(ApiModel):
    id: str
    run_id: str
    event_type: str
    actor: str
    payload: dict[str, object]
    created_at: str


class RunDetailResponse(ApiModel):
    run: RunResponse
    final_summary: str | None
    requires_approval: bool
    approval: ApprovalResponse | None
    tool_calls: list[ToolCallResponse]
    audit_events: list[AuditEventResponse]
