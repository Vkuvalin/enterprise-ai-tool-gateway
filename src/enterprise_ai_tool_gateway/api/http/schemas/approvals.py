"""Approval request schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import model_validator

from enterprise_ai_tool_gateway.api.http.schemas.common import ApiModel
from enterprise_ai_tool_gateway.contracts.enums import ApprovalStatus


class ApprovalResolveRequest(ApiModel):
    run_id: UUID
    status: ApprovalStatus
    decided_by: str
    decision_comment: str | None = None

    @model_validator(mode="after")
    def validate_decision_status(self) -> "ApprovalResolveRequest":
        if self.status is ApprovalStatus.PENDING:
            raise ValueError("PENDING is not a valid approval decision status")
        return self
