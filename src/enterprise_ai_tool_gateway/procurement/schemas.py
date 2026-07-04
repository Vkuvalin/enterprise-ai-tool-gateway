"""Procurement-specific schemas for the Stage 7 thin demo template."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel


class ProcurementModel(BaseModel):
    """Base model for procurement-domain tool payloads."""

    model_config = ConfigDict(extra="forbid")


class RequesterStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class VendorStatus(StrEnum):
    APPROVED = "APPROVED"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"


class ProcurementItemCategory(StrEnum):
    SOFTWARE = "SOFTWARE"
    HARDWARE = "HARDWARE"
    OFFICE_SUPPLIES = "OFFICE_SUPPLIES"
    SERVICES = "SERVICES"
    RESTRICTED = "RESTRICTED"


class BudgetStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    EXCEEDED = "EXCEEDED"
    UNKNOWN = "UNKNOWN"


class PurchaseRequestStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"


class ProcurementRequesterProfile(ProcurementModel):
    requester_id: str
    full_name: str
    status: RequesterStatus
    department: str
    can_purchase: bool
    manager_id: str | None
    default_cost_center: str | None
    risk_flags: list[str] = Field(default_factory=list)


class VendorProfile(ProcurementModel):
    vendor_id: str
    name: str
    status: VendorStatus
    risk_flags: list[str] = Field(default_factory=list)


class CatalogItem(ProcurementModel):
    item_id: str
    item_name: str
    category: ProcurementItemCategory
    unit_price: float = Field(ge=0)
    currency: str
    restricted: bool = False


class CostCenterBudget(ProcurementModel):
    cost_center: str
    name: str
    status: BudgetStatus
    remaining_budget: float = Field(ge=0)
    currency: str


class ProcurementPolicyRule(ProcurementModel):
    category: ProcurementItemCategory
    high_value_threshold: float = Field(ge=0)
    default_risk_level: RiskLevel
    high_value_risk_level: RiskLevel
    reason_codes: list[str] = Field(default_factory=list)


class ExistingPurchaseRequest(ProcurementModel):
    purchase_request_id: str
    requester_id: str
    item_id: str | None
    item_name: str
    quantity: int = Field(gt=0)
    status: PurchaseRequestStatus
    created_at: datetime


class GetProcurementRequesterProfileInput(ProcurementModel):
    requester_id: str


class GetProcurementRequesterProfileOutput(ProcurementModel):
    found: bool
    requester: ProcurementRequesterProfile | None
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class GetVendorInfoInput(ProcurementModel):
    vendor_id: str | None = None


class GetVendorInfoOutput(ProcurementModel):
    found: bool
    vendor: VendorProfile | None
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class GetCatalogItemInput(ProcurementModel):
    item_id: str | None = None
    item_name: str | None = None


class GetCatalogItemOutput(ProcurementModel):
    found: bool
    item: CatalogItem | None
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class CheckProcurementPolicyInput(ProcurementModel):
    requester_id: str
    item_id: str | None = None
    item_name: str | None = None
    quantity: int = Field(gt=0)
    estimated_total: float = Field(ge=0)
    currency: str
    cost_center: str
    preferred_vendor_id: str | None = None


class ProcurementPolicyOutput(ProcurementModel):
    allowed: bool
    forbidden: bool
    manual_review: bool
    risk_level: RiskLevel
    requires_approval_by_default: bool
    required_approver_role: str | None
    budget_status: BudgetStatus
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class GetExistingPurchaseRequestsInput(ProcurementModel):
    requester_id: str
    item_id: str | None = None
    item_name: str | None = None


class GetExistingPurchaseRequestsOutput(ProcurementModel):
    purchase_requests: list[ExistingPurchaseRequest] = Field(default_factory=list)
    has_open_duplicate: bool
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str


class CreatePurchaseRequestDraftInput(ProcurementModel):
    run_id: UUID
    requester_id: str
    item_id: str | None = None
    item_name: str
    vendor_id: str | None = None
    quantity: int = Field(gt=0)
    estimated_total: float = Field(ge=0)
    currency: str
    cost_center: str
    justification: str
    reason_codes: list[str] = Field(default_factory=list)


class CreatePurchaseRequestDraftOutput(ProcurementModel):
    draft_id: str
    status: str = "draft"
    requester_id: str
    item_id: str | None = None
    item_name: str
    vendor_id: str | None = None
    quantity: int = Field(gt=0)
    estimated_total: float = Field(ge=0)
    currency: str
    cost_center: str
    summary: str
    reason_codes: list[str] = Field(default_factory=list)
