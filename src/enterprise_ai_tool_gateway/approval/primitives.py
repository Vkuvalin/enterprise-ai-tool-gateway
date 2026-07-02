"""Approval primitives detached from API, DB, and workflow state."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from enterprise_ai_tool_gateway.contracts.enums import ApprovalStatus, RiskLevel


class ApprovalRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID | None
    tool_call_id: UUID | None
    required_approver_role: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    reason: str | None = None
    risk_level: RiskLevel
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "ApprovalRequirement":
        if self.run_id is None and self.tool_call_id is None:
            raise ValueError("ApprovalRequirement must reference a run or tool call")
        return self


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApprovalStatus
    decided_by: str | None = None
    decision_comment: str | None = None
    decided_at: datetime | None = None

    @model_validator(mode="after")
    def validate_terminal_decision(self) -> "ApprovalDecision":
        if is_approval_terminal(self) and (not self.decided_by or self.decided_at is None):
            raise ValueError("Terminal approval decisions require decided_by and decided_at")
        return self


def is_approval_granted(decision: ApprovalDecision) -> bool:
    return decision.status is ApprovalStatus.APPROVED


def is_approval_terminal(decision: ApprovalDecision) -> bool:
    return decision.status in {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
        ApprovalStatus.CANCELLED,
    }
