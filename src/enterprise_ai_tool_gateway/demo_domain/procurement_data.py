"""Synthetic procurement data for the Stage 7 procurement demo template."""

from __future__ import annotations

from datetime import UTC, datetime

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel
from enterprise_ai_tool_gateway.procurement.schemas import (
    BudgetStatus,
    CatalogItem,
    CostCenterBudget,
    ExistingPurchaseRequest,
    ProcurementItemCategory,
    ProcurementPolicyRule,
    ProcurementRequesterProfile,
    PurchaseRequestStatus,
    RequesterStatus,
    VendorProfile,
    VendorStatus,
)

PROCUREMENT_REQUESTERS: dict[str, ProcurementRequesterProfile] = {
    "req-001": ProcurementRequesterProfile(
        requester_id="req-001",
        full_name="Nina Petrova",
        status=RequesterStatus.ACTIVE,
        department="Operations",
        can_purchase=True,
        manager_id="mgr-proc-001",
        default_cost_center="cc-ops",
        risk_flags=[],
    ),
    "req-inactive-001": ProcurementRequesterProfile(
        requester_id="req-inactive-001",
        full_name="Sergey Orlov",
        status=RequesterStatus.INACTIVE,
        department="Finance",
        can_purchase=True,
        manager_id="mgr-proc-002",
        default_cost_center="cc-finance",
        risk_flags=["INACTIVE_REQUESTER"],
    ),
    "req-no-purchase-001": ProcurementRequesterProfile(
        requester_id="req-no-purchase-001",
        full_name="Maria Volkova",
        status=RequesterStatus.ACTIVE,
        department="Support",
        can_purchase=False,
        manager_id="mgr-proc-003",
        default_cost_center="cc-support",
        risk_flags=["PURCHASE_PERMISSION_MISSING"],
    ),
    "req-duplicate-001": ProcurementRequesterProfile(
        requester_id="req-duplicate-001",
        full_name="Denis Smirnov",
        status=RequesterStatus.ACTIVE,
        department="Operations",
        can_purchase=True,
        manager_id="mgr-proc-001",
        default_cost_center="cc-ops",
        risk_flags=[],
    ),
}

VENDORS: dict[str, VendorProfile] = {
    "vendor-approved-001": VendorProfile(
        vendor_id="vendor-approved-001",
        name="Approved Software Supplies",
        status=VendorStatus.APPROVED,
        risk_flags=[],
    ),
    "vendor-blocked-001": VendorProfile(
        vendor_id="vendor-blocked-001",
        name="Blocked Demo Vendor",
        status=VendorStatus.BLOCKED,
        risk_flags=["BLOCKED_VENDOR"],
    ),
}

CATALOG_ITEMS: dict[str, CatalogItem] = {
    "item-laptop": CatalogItem(
        item_id="item-laptop",
        item_name="Standard laptop",
        category=ProcurementItemCategory.HARDWARE,
        unit_price=900.0,
        currency="USD",
        restricted=False,
    ),
    "item-monitor": CatalogItem(
        item_id="item-monitor",
        item_name="Office monitor",
        category=ProcurementItemCategory.OFFICE_SUPPLIES,
        unit_price=250.0,
        currency="USD",
        restricted=False,
    ),
    "item-service": CatalogItem(
        item_id="item-service",
        item_name="Implementation services",
        category=ProcurementItemCategory.SERVICES,
        unit_price=1500.0,
        currency="USD",
        restricted=False,
    ),
    "item-restricted-001": CatalogItem(
        item_id="item-restricted-001",
        item_name="Restricted security appliance",
        category=ProcurementItemCategory.RESTRICTED,
        unit_price=2000.0,
        currency="USD",
        restricted=True,
    ),
}

COST_CENTER_BUDGETS: dict[str, CostCenterBudget] = {
    "cc-ops": CostCenterBudget(
        cost_center="cc-ops",
        name="Operations demo budget",
        status=BudgetStatus.AVAILABLE,
        remaining_budget=10000.0,
        currency="USD",
    ),
    "cc-exceeded": CostCenterBudget(
        cost_center="cc-exceeded",
        name="Exceeded demo budget",
        status=BudgetStatus.EXCEEDED,
        remaining_budget=100.0,
        currency="USD",
    ),
}

PROCUREMENT_POLICY_RULES: dict[ProcurementItemCategory, ProcurementPolicyRule] = {
    ProcurementItemCategory.SOFTWARE: ProcurementPolicyRule(
        category=ProcurementItemCategory.SOFTWARE,
        high_value_threshold=1000.0,
        default_risk_level=RiskLevel.MEDIUM,
        high_value_risk_level=RiskLevel.HIGH,
        reason_codes=["SOFTWARE_PURCHASE_STANDARD"],
    ),
    ProcurementItemCategory.HARDWARE: ProcurementPolicyRule(
        category=ProcurementItemCategory.HARDWARE,
        high_value_threshold=1000.0,
        default_risk_level=RiskLevel.MEDIUM,
        high_value_risk_level=RiskLevel.HIGH,
        reason_codes=["HARDWARE_PURCHASE_STANDARD"],
    ),
    ProcurementItemCategory.OFFICE_SUPPLIES: ProcurementPolicyRule(
        category=ProcurementItemCategory.OFFICE_SUPPLIES,
        high_value_threshold=1000.0,
        default_risk_level=RiskLevel.MEDIUM,
        high_value_risk_level=RiskLevel.HIGH,
        reason_codes=["OFFICE_SUPPLIES_STANDARD"],
    ),
    ProcurementItemCategory.SERVICES: ProcurementPolicyRule(
        category=ProcurementItemCategory.SERVICES,
        high_value_threshold=1000.0,
        default_risk_level=RiskLevel.MEDIUM,
        high_value_risk_level=RiskLevel.HIGH,
        reason_codes=["SERVICES_PURCHASE_STANDARD"],
    ),
    ProcurementItemCategory.RESTRICTED: ProcurementPolicyRule(
        category=ProcurementItemCategory.RESTRICTED,
        high_value_threshold=0.0,
        default_risk_level=RiskLevel.CRITICAL,
        high_value_risk_level=RiskLevel.CRITICAL,
        reason_codes=["RESTRICTED_ITEM_FORBIDDEN"],
    ),
}

EXISTING_PURCHASE_REQUESTS: tuple[ExistingPurchaseRequest, ...] = (
    ExistingPurchaseRequest(
        purchase_request_id="pr-open-001",
        requester_id="req-duplicate-001",
        item_id="item-laptop",
        item_name="Standard laptop",
        quantity=1,
        status=PurchaseRequestStatus.DRAFT,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    ),
    ExistingPurchaseRequest(
        purchase_request_id="pr-approved-001",
        requester_id="req-001",
        item_id="item-monitor",
        item_name="Office monitor",
        quantity=1,
        status=PurchaseRequestStatus.APPROVED,
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
    ),
)
