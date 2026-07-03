"""Foundation-level Pydantic contracts for gateway layers."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from enterprise_ai_tool_gateway.contracts.enums import (
    AgentRunStatus,
    ApprovalMode,
    ApprovalStatus,
    AuditEventType,
    DomainTemplate,
    ProviderName,
    RequestType,
    RiskLevel,
    ToolCallStatus,
    ToolType,
)

LEGACY_DOMAIN_TEMPLATE_ALIASES = {
    RequestType.ACCESS_REQUEST.value: DomainTemplate.ACCESS,
    RequestType.PROCUREMENT_REQUEST.value: DomainTemplate.PROCUREMENT,
    RequestType.MAINTENANCE_REQUEST.value: DomainTemplate.MAINTENANCE_LITE,
    RequestType.POLICY_INQUIRY.value: DomainTemplate.POLICY,
}


class ContractModel(BaseModel):
    """Base contract settings for explicit schema boundaries."""

    model_config = ConfigDict(extra="forbid")


class AgentRunCreate(ContractModel):
    user_id: str
    request_text: str
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY


class ProposedToolCall(ContractModel):
    name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    requires_approval: bool = True


class LLMDecisionPayload(ContractModel):
    schema_version: str = "1.0"
    request_type: RequestType
    domain_template: DomainTemplate
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    requires_approval: bool
    missing_fields: list[str] = Field(default_factory=list)
    proposed_tool_calls: list[ProposedToolCall] = Field(default_factory=list)
    user_facing_summary: str
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("domain_template", mode="before")
    @classmethod
    def normalize_legacy_domain_template(cls, value: Any) -> Any:
        if isinstance(value, str):
            return LEGACY_DOMAIN_TEMPLATE_ALIASES.get(value, value)
        return value


class AgentRunRead(ContractModel):
    id: UUID
    user_id: str
    request_text: str
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY
    request_type: RequestType = RequestType.UNKNOWN
    domain_template: DomainTemplate = DomainTemplate.UNKNOWN
    status: AgentRunStatus
    risk_level: RiskLevel | None = None
    requires_approval: bool = False
    provider_name: ProviderName | None = None
    model_name: str | None = None
    final_summary: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class LLMDecisionCreate(ContractModel):
    run_id: UUID
    schema_version: str = "1.0"
    raw_response_ref: str | None = None
    validated_payload: dict[str, object] = Field(default_factory=dict)
    schema_valid: bool
    validation_errors: list[object] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class LLMDecisionRead(ContractModel):
    id: UUID
    run_id: UUID
    schema_version: str
    raw_response_ref: str | None = None
    validated_payload: dict[str, object] = Field(default_factory=dict)
    schema_valid: bool
    validation_errors: list[object] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime


class ToolCallCreate(ContractModel):
    run_id: UUID
    tool_name: str
    tool_type: ToolType
    status: ToolCallStatus = ToolCallStatus.PROPOSED
    input_payload: dict[str, object] = Field(default_factory=dict)
    output_payload: dict[str, object] | None = None
    error_message: str | None = None
    requires_approval: bool
    approval_id: UUID | None = None


class ToolCallRead(ContractModel):
    id: UUID
    run_id: UUID
    tool_name: str
    tool_type: ToolType
    status: ToolCallStatus
    input_payload: dict[str, object] = Field(default_factory=dict)
    output_payload: dict[str, object] | None = None
    error_message: str | None = None
    requires_approval: bool
    approval_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ApprovalCreate(ContractModel):
    run_id: UUID
    tool_call_id: UUID | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    required_approver_role: str
    summary: str
    reason: str | None = None
    decided_by: str | None = None
    decision_comment: str | None = None


class ApprovalRead(ContractModel):
    id: UUID
    run_id: UUID
    tool_call_id: UUID | None = None
    status: ApprovalStatus
    required_approver_role: str
    summary: str
    reason: str | None = None
    decided_by: str | None = None
    decision_comment: str | None = None
    created_at: datetime
    updated_at: datetime


class AuditEventCreate(ContractModel):
    run_id: UUID
    event_type: AuditEventType
    actor: str = "system"
    payload: dict[str, object] = Field(default_factory=dict)


class AuditEventRead(ContractModel):
    id: UUID
    run_id: UUID
    event_type: AuditEventType
    actor: str
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
