"""Maintenance-lite schemas for the Stage 7 thin demo template."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel


class MaintenanceModel(BaseModel):
    """Base model for maintenance-lite tool payloads."""

    model_config = ConfigDict(extra="forbid")


class MaintenanceRequesterStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class AssetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DECOMMISSIONED = "DECOMMISSIONED"


class AssetCriticality(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MaintenanceSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MaintenanceTicketStatus(StrEnum):
    OPEN = "OPEN"
    PENDING_REVIEW = "PENDING_REVIEW"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class MaintenanceRequesterProfile(MaintenanceModel):
    requester_id: str
    full_name: str
    status: MaintenanceRequesterStatus
    department: str
    manager_id: str | None
    risk_flags: list[str] = Field(default_factory=list)


class AssetInfo(MaintenanceModel):
    asset_id: str
    asset_name: str
    status: AssetStatus
    criticality: AssetCriticality
    location: str
    safety_sensitive: bool


class MaintenancePolicyRule(MaintenanceModel):
    severity: MaintenanceSeverity
    criticality: AssetCriticality
    risk_level: RiskLevel
    requires_approval_by_default: bool
    manual_review: bool
    reason_codes: list[str] = Field(default_factory=list)


class ExistingMaintenanceTicket(MaintenanceModel):
    ticket_id: str
    requester_id: str
    asset_id: str
    asset_name: str
    status: MaintenanceTicketStatus
    issue_summary: str
    created_at: datetime


class GetMaintenanceRequesterProfileInput(MaintenanceModel):
    requester_id: str


class GetMaintenanceRequesterProfileOutput(MaintenanceModel):
    found: bool
    requester: MaintenanceRequesterProfile | None
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class GetAssetInfoInput(MaintenanceModel):
    asset_id: str | None = None
    asset_name: str | None = None


class GetAssetInfoOutput(MaintenanceModel):
    found: bool
    asset: AssetInfo | None
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class ClassifyMaintenanceSeverityInput(MaintenanceModel):
    issue_description: str
    observed_severity: MaintenanceSeverity | None = None
    safety_concern: bool | None = None


class ClassifyMaintenanceSeverityOutput(MaintenanceModel):
    severity: MaintenanceSeverity
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class GetOpenMaintenanceTicketsInput(MaintenanceModel):
    asset_id: str | None = None
    asset_name: str | None = None


class GetOpenMaintenanceTicketsOutput(MaintenanceModel):
    tickets: list[ExistingMaintenanceTicket] = Field(default_factory=list)
    has_open_duplicate: bool
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class CheckMaintenancePolicyInput(MaintenanceModel):
    requester_id: str
    asset_id: str | None = None
    asset_name: str | None = None
    issue_description: str
    severity: MaintenanceSeverity
    safety_concern: bool


class MaintenancePolicyOutput(MaintenanceModel):
    allowed: bool
    forbidden: bool
    manual_review: bool
    risk_level: RiskLevel
    requires_approval_by_default: bool
    required_approver_role: str | None
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class CreateWorkOrderDraftInput(MaintenanceModel):
    run_id: UUID
    requester_id: str
    asset_id: str
    asset_name: str
    severity: MaintenanceSeverity
    location: str | None = None
    issue_description: str
    safety_concern: bool
    reason_codes: list[str] = Field(default_factory=list)


class CreateWorkOrderDraftOutput(MaintenanceModel):
    draft_id: str
    status: str = "draft"
    requester_id: str
    asset_id: str
    asset_name: str
    severity: MaintenanceSeverity
    location: str | None = None
    issue_summary: str
    safety_concern: bool
    reason_codes: list[str] = Field(default_factory=list)
