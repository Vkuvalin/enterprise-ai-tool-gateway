"""Access-specific schemas for the Stage 5 reference workflow."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel


class AccessModel(BaseModel):
    """Base model for access-domain tool payloads."""

    model_config = ConfigDict(extra="forbid")


class AccessLevel(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    ADMIN = "ADMIN"


class EmployeeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class EmploymentType(StrEnum):
    EMPLOYEE = "EMPLOYEE"
    INTERN = "INTERN"


class SystemSensitivity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AccessTicketStatus(StrEnum):
    OPEN = "OPEN"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


class EmployeeProfile(AccessModel):
    employee_id: str
    full_name: str
    status: EmployeeStatus
    department: str
    role: str
    manager_id: str | None
    employment_type: EmploymentType
    risk_flags: list[str] = Field(default_factory=list)


class SystemInfo(AccessModel):
    system_id: str
    name: str
    description: str
    sensitivity: SystemSensitivity
    available_access_levels: list[AccessLevel]
    owner_role: str


class AccessPolicyRule(AccessModel):
    system_id: str
    access_level: AccessLevel
    max_duration_days: int
    risk_level: RiskLevel
    requires_approval_by_default: bool
    forbidden: bool
    required_approver_role: str | None
    reason_codes: list[str] = Field(default_factory=list)


class ExistingAccessTicket(AccessModel):
    ticket_id: str
    employee_id: str
    system_id: str
    access_level: AccessLevel
    status: AccessTicketStatus
    created_at: datetime


class GetEmployeeProfileInput(AccessModel):
    employee_id: str


class GetEmployeeProfileOutput(AccessModel):
    found: bool
    employee: EmployeeProfile | None
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class GetSystemInfoInput(AccessModel):
    system_id: str


class GetSystemInfoOutput(AccessModel):
    found: bool
    system: SystemInfo | None
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class SearchAccessPolicyInput(AccessModel):
    employee_id: str
    system_id: str
    access_level: AccessLevel
    duration_days: int = Field(gt=0)


class AccessPolicyOutput(AccessModel):
    allowed: bool
    forbidden: bool
    risk_level: RiskLevel
    requires_approval_by_default: bool
    required_approver_role: str | None
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class GetExistingAccessTicketsInput(AccessModel):
    employee_id: str
    system_id: str
    access_level: AccessLevel


class GetExistingAccessTicketsOutput(AccessModel):
    tickets: list[ExistingAccessTicket] = Field(default_factory=list)
    has_open_duplicate: bool
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class CreateAccessRequestDraftInput(AccessModel):
    run_id: UUID
    employee_id: str
    system_id: str
    access_level: AccessLevel
    duration_days: int = Field(gt=0)
    justification: str | None = None


class CreateAccessRequestDraftOutput(AccessModel):
    draft_id: str
    status: str = "draft"
    summary: str
    reason_codes: list[str] = Field(default_factory=list)
