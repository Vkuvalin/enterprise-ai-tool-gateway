"""Workflow submit request and result schemas."""

from __future__ import annotations

from pydantic import Field

from enterprise_ai_tool_gateway.access.schemas import AccessLevel
from enterprise_ai_tool_gateway.api.http.schemas.common import ApiModel
from enterprise_ai_tool_gateway.api.http.schemas.runs import (
    ApprovalResponse,
    AuditEventResponse,
    RunResponse,
    ToolCallResponse,
)
from enterprise_ai_tool_gateway.contracts.enums import ApprovalMode
from enterprise_ai_tool_gateway.maintenance_lite.schemas import MaintenanceSeverity


class AccessSubmitRequest(ApiModel):
    user_id: str
    request_text: str
    employee_id: str | None = None
    system_id: str | None = None
    access_level: AccessLevel | None = None
    duration_days: int | None = Field(default=None, gt=0)
    justification: str | None = None
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY


class ProcurementSubmitRequest(ApiModel):
    user_id: str
    request_text: str
    requester_id: str | None = None
    item_id: str | None = None
    item_name: str | None = None
    quantity: int | None = Field(default=None, gt=0)
    estimated_total: float | None = Field(default=None, ge=0)
    currency: str = "USD"
    cost_center: str | None = None
    justification: str | None = None
    preferred_vendor_id: str | None = None
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY


class MaintenanceSubmitRequest(ApiModel):
    user_id: str
    request_text: str
    requester_id: str | None = None
    asset_id: str | None = None
    asset_name: str | None = None
    issue_description: str | None = None
    location: str | None = None
    observed_severity: MaintenanceSeverity | None = None
    safety_concern: bool | None = None
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY


class WorkflowResultResponse(ApiModel):
    run: RunResponse
    final_summary: str | None
    requires_approval: bool
    approval: ApprovalResponse | None
    tool_calls: list[ToolCallResponse]
    audit_events: list[AuditEventResponse]
