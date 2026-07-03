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
