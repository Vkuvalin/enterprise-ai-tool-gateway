"""Generic policy decision primitives."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from enterprise_ai_tool_gateway.contracts.enums import (
    ApprovalMode,
    PolicyDecisionStatus,
    RiskLevel,
    ToolType,
)


class PolicyCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_type: ToolType
    risk_level: RiskLevel
    requires_approval_by_default: bool
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY
    context: dict[str, object] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PolicyDecisionStatus
    risk_level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    requires_approval: bool
    required_approver_role: str | None = None
    safe_summary: str
