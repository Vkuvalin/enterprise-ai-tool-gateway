"""Application DTOs for the Stage 5 access workflow."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from enterprise_ai_tool_gateway.access.schemas import AccessLevel
from enterprise_ai_tool_gateway.contracts.enums import ApprovalMode, ApprovalStatus
from enterprise_ai_tool_gateway.contracts.schemas import (
    AgentRunRead,
    ApprovalRead,
    AuditEventRead,
    ToolCallRead,
)
from enterprise_ai_tool_gateway.maintenance_lite.schemas import MaintenanceSeverity


class ApplicationModel(BaseModel):
    """Base DTO settings for application-level boundaries."""

    model_config = ConfigDict(extra="forbid")


class AccessWorkflowRequest(ApplicationModel):
    user_id: str
    request_text: str
    employee_id: str | None = None
    system_id: str | None = None
    access_level: AccessLevel | None = None
    duration_days: int | None = None
    justification: str | None = None
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY


class AccessWorkflowResult(ApplicationModel):
    run: AgentRunRead
    final_summary: str | None
    requires_approval: bool
    approval: ApprovalRead | None
    tool_calls: list[ToolCallRead] = Field(default_factory=list)
    audit_events: list[AuditEventRead] = Field(default_factory=list)


class AccessApprovalResolutionRequest(ApplicationModel):
    run_id: UUID
    approval_id: UUID
    status: ApprovalStatus
    decided_by: str
    decision_comment: str | None = None

    @model_validator(mode="after")
    def validate_decision_status(self) -> "AccessApprovalResolutionRequest":
        if self.status is ApprovalStatus.PENDING:
            raise ValueError("PENDING is not a valid approval decision status")
        return self


class ProcurementWorkflowRequest(ApplicationModel):
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


class ProcurementWorkflowResult(ApplicationModel):
    run: AgentRunRead
    final_summary: str | None
    requires_approval: bool
    approval: ApprovalRead | None
    tool_calls: list[ToolCallRead] = Field(default_factory=list)
    audit_events: list[AuditEventRead] = Field(default_factory=list)


class ProcurementApprovalResolutionRequest(ApplicationModel):
    run_id: UUID
    approval_id: UUID
    status: ApprovalStatus
    decided_by: str
    decision_comment: str | None = None

    @model_validator(mode="after")
    def validate_decision_status(self) -> "ProcurementApprovalResolutionRequest":
        if self.status is ApprovalStatus.PENDING:
            raise ValueError("PENDING is not a valid approval decision status")
        return self


class MaintenanceWorkflowRequest(ApplicationModel):
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


class MaintenanceWorkflowResult(ApplicationModel):
    run: AgentRunRead
    final_summary: str | None
    requires_approval: bool
    approval: ApprovalRead | None
    tool_calls: list[ToolCallRead] = Field(default_factory=list)
    audit_events: list[AuditEventRead] = Field(default_factory=list)


class MaintenanceApprovalResolutionRequest(ApplicationModel):
    run_id: UUID
    approval_id: UUID
    status: ApprovalStatus
    decided_by: str
    decision_comment: str | None = None

    @model_validator(mode="after")
    def validate_decision_status(self) -> "MaintenanceApprovalResolutionRequest":
        if self.status is ApprovalStatus.PENDING:
            raise ValueError("PENDING is not a valid approval decision status")
        return self
