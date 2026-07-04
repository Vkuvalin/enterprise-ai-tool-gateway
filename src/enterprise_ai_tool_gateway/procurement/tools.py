"""Procurement tool definitions backed by deterministic synthetic data."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel, ToolType
from enterprise_ai_tool_gateway.demo_domain.procurement_data import (
    CATALOG_ITEMS,
    COST_CENTER_BUDGETS,
    EXISTING_PURCHASE_REQUESTS,
    PROCUREMENT_POLICY_RULES,
    PROCUREMENT_REQUESTERS,
    VENDORS,
)
from enterprise_ai_tool_gateway.procurement.schemas import (
    BudgetStatus,
    CatalogItem,
    CheckProcurementPolicyInput,
    CreatePurchaseRequestDraftInput,
    CreatePurchaseRequestDraftOutput,
    GetCatalogItemInput,
    GetCatalogItemOutput,
    GetExistingPurchaseRequestsInput,
    GetExistingPurchaseRequestsOutput,
    GetProcurementRequesterProfileInput,
    GetProcurementRequesterProfileOutput,
    GetVendorInfoInput,
    GetVendorInfoOutput,
    ProcurementItemCategory,
    ProcurementPolicyOutput,
    PurchaseRequestStatus,
    RequesterStatus,
    VendorStatus,
)
from enterprise_ai_tool_gateway.tools.base import ToolDefinition
from enterprise_ai_tool_gateway.tools.registry import ToolRegistry

_OPEN_DUPLICATE_STATUSES = {
    PurchaseRequestStatus.DRAFT,
    PurchaseRequestStatus.PENDING_APPROVAL,
}
_ESTIMATED_TOTAL_TOLERANCE = 0.01


def get_procurement_requester_profile(
    payload: BaseModel,
) -> GetProcurementRequesterProfileOutput:
    request = cast(GetProcurementRequesterProfileInput, payload)
    requester = PROCUREMENT_REQUESTERS.get(request.requester_id)
    if requester is None:
        return GetProcurementRequesterProfileOutput(
            found=False,
            requester=None,
            reason_codes=["REQUESTER_NOT_FOUND"],
            safe_summary="Requester profile was not found in synthetic procurement data.",
        )

    reason_codes: list[str] = []
    if requester.status is RequesterStatus.INACTIVE:
        reason_codes.append("REQUESTER_INACTIVE")
    if not requester.can_purchase:
        reason_codes.append("PURCHASE_PERMISSION_MISSING")

    return GetProcurementRequesterProfileOutput(
        found=True,
        requester=requester,
        reason_codes=reason_codes,
        safe_summary=f"Requester profile found for {requester.full_name}.",
    )


def get_vendor_info(payload: BaseModel) -> GetVendorInfoOutput:
    request = cast(GetVendorInfoInput, payload)
    if request.vendor_id is None:
        return GetVendorInfoOutput(
            found=False,
            vendor=None,
            reason_codes=["VENDOR_NOT_SPECIFIED"],
            safe_summary="No preferred vendor was specified.",
        )

    vendor = VENDORS.get(request.vendor_id)
    if vendor is None:
        return GetVendorInfoOutput(
            found=False,
            vendor=None,
            reason_codes=["VENDOR_UNKNOWN"],
            safe_summary="Preferred vendor was not found in synthetic vendor data.",
        )

    reason_codes = ["VENDOR_BLOCKED"] if vendor.status is VendorStatus.BLOCKED else []
    return GetVendorInfoOutput(
        found=True,
        vendor=vendor,
        reason_codes=reason_codes,
        safe_summary=f"Vendor information found for {vendor.name}.",
    )


def get_catalog_item(payload: BaseModel) -> GetCatalogItemOutput:
    request = cast(GetCatalogItemInput, payload)
    item = _find_catalog_item(request.item_id, request.item_name)
    if item is None:
        return GetCatalogItemOutput(
            found=False,
            item=None,
            reason_codes=["CATALOG_ITEM_NOT_FOUND"],
            safe_summary="Catalog item was not found in synthetic procurement data.",
        )

    reason_codes = ["RESTRICTED_ITEM"] if item.restricted else []
    return GetCatalogItemOutput(
        found=True,
        item=item,
        reason_codes=reason_codes,
        safe_summary=f"Catalog item found for {item.item_name}.",
    )


def check_procurement_policy(payload: BaseModel) -> ProcurementPolicyOutput:
    request = cast(CheckProcurementPolicyInput, payload)
    item = _find_catalog_item(request.item_id, request.item_name)
    budget = COST_CENTER_BUDGETS.get(request.cost_center)
    requester = PROCUREMENT_REQUESTERS.get(request.requester_id)
    vendor = VENDORS.get(request.preferred_vendor_id) if request.preferred_vendor_id else None

    reason_codes: list[str] = []
    if requester is None:
        reason_codes.append("REQUESTER_NOT_FOUND")
    elif requester.status is RequesterStatus.INACTIVE:
        reason_codes.append("REQUESTER_INACTIVE")
    elif not requester.can_purchase:
        reason_codes.append("PURCHASE_PERMISSION_MISSING")

    if item is None:
        reason_codes.append("CATALOG_ITEM_NOT_FOUND")
    if request.preferred_vendor_id and vendor is None:
        reason_codes.append("VENDOR_UNKNOWN")
    if budget is None:
        reason_codes.append("COST_CENTER_UNKNOWN")

    if reason_codes:
        return ProcurementPolicyOutput(
            allowed=False,
            forbidden=False,
            manual_review=True,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            required_approver_role="procurement_review",
            budget_status=BudgetStatus.UNKNOWN if budget is None else budget.status,
            reason_codes=reason_codes,
            safe_summary="Procurement request needs manual review before draft creation.",
        )

    if item is None or budget is None:
        return ProcurementPolicyOutput(
            allowed=False,
            forbidden=False,
            manual_review=True,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            required_approver_role="procurement_review",
            budget_status=BudgetStatus.UNKNOWN,
            reason_codes=["PROCUREMENT_POLICY_INPUT_INCOMPLETE"],
            safe_summary="Procurement policy input was incomplete.",
        )

    computed_total = item.unit_price * request.quantity
    if item.category is ProcurementItemCategory.RESTRICTED or item.restricted:
        return ProcurementPolicyOutput(
            allowed=False,
            forbidden=True,
            manual_review=False,
            risk_level=RiskLevel.CRITICAL,
            requires_approval_by_default=False,
            required_approver_role=None,
            budget_status=budget.status,
            reason_codes=["RESTRICTED_ITEM_FORBIDDEN"],
            safe_summary="Restricted procurement item is forbidden.",
        )

    if vendor is not None and vendor.status is VendorStatus.BLOCKED:
        return ProcurementPolicyOutput(
            allowed=False,
            forbidden=True,
            manual_review=False,
            risk_level=RiskLevel.CRITICAL,
            requires_approval_by_default=False,
            required_approver_role=None,
            budget_status=budget.status,
            reason_codes=["BLOCKED_VENDOR_FORBIDDEN"],
            safe_summary="Blocked vendor is forbidden for procurement drafts.",
        )

    if abs(request.estimated_total - computed_total) > _ESTIMATED_TOTAL_TOLERANCE:
        return ProcurementPolicyOutput(
            allowed=False,
            forbidden=False,
            manual_review=True,
            risk_level=RiskLevel.HIGH,
            requires_approval_by_default=False,
            required_approver_role="procurement_review",
            budget_status=budget.status,
            reason_codes=["ESTIMATED_TOTAL_MISMATCH"],
            safe_summary="Estimated total differs from catalog price and quantity.",
        )

    if budget.status is BudgetStatus.EXCEEDED or computed_total > budget.remaining_budget:
        return ProcurementPolicyOutput(
            allowed=False,
            forbidden=False,
            manual_review=True,
            risk_level=RiskLevel.HIGH,
            requires_approval_by_default=False,
            required_approver_role="procurement_review",
            budget_status=BudgetStatus.EXCEEDED,
            reason_codes=["BUDGET_EXCEEDED"],
            safe_summary="Budget is exceeded and requires manual review.",
        )

    rule = PROCUREMENT_POLICY_RULES[item.category]
    high_value = computed_total > rule.high_value_threshold
    risk_level = rule.high_value_risk_level if high_value else rule.default_risk_level
    requires_approval = high_value
    reason_codes.extend(rule.reason_codes)
    if high_value:
        reason_codes.append("HIGH_VALUE_PURCHASE")
    else:
        reason_codes.append("STANDARD_PURCHASE")
    if vendor is not None:
        reason_codes.append("APPROVED_VENDOR")
    else:
        reason_codes.append("NO_PREFERRED_VENDOR")

    return ProcurementPolicyOutput(
        allowed=True,
        forbidden=False,
        manual_review=False,
        risk_level=risk_level,
        requires_approval_by_default=requires_approval,
        required_approver_role="procurement_manager" if requires_approval else None,
        budget_status=budget.status,
        reason_codes=reason_codes,
        safe_summary="Synthetic procurement policy allows draft processing.",
    )


def get_existing_purchase_requests(payload: BaseModel) -> GetExistingPurchaseRequestsOutput:
    request = cast(GetExistingPurchaseRequestsInput, payload)
    request_item_name = (request.item_name or "").casefold()
    purchase_requests = [
        purchase_request
        for purchase_request in EXISTING_PURCHASE_REQUESTS
        if purchase_request.requester_id == request.requester_id
        and (
            (request.item_id is not None and purchase_request.item_id == request.item_id)
            or (
                request.item_id is None
                and request_item_name
                and purchase_request.item_name.casefold() == request_item_name
            )
        )
    ]
    has_open_duplicate = any(
        purchase_request.status in _OPEN_DUPLICATE_STATUSES
        for purchase_request in purchase_requests
    )

    return GetExistingPurchaseRequestsOutput(
        purchase_requests=purchase_requests,
        has_open_duplicate=has_open_duplicate,
        reason_codes=["OPEN_DUPLICATE_PURCHASE_REQUEST"] if has_open_duplicate else [],
        safe_summary=(
            "Open duplicate purchase request found."
            if has_open_duplicate
            else "No open duplicate purchase request found."
        ),
    )


def create_purchase_request_draft(payload: BaseModel) -> CreatePurchaseRequestDraftOutput:
    request = cast(CreatePurchaseRequestDraftInput, payload)
    draft_id = f"draft-{str(request.run_id)[:8]}-{request.requester_id}"
    vendor_summary = request.vendor_id if request.vendor_id is not None else "no preferred vendor"

    return CreatePurchaseRequestDraftOutput(
        draft_id=draft_id,
        requester_id=request.requester_id,
        item_id=request.item_id,
        item_name=request.item_name,
        vendor_id=request.vendor_id,
        quantity=request.quantity,
        estimated_total=request.estimated_total,
        currency=request.currency,
        cost_center=request.cost_center,
        summary=(
            f"Purchase request draft created for {request.quantity} x {request.item_name} "
            f"with {vendor_summary}."
        ),
        reason_codes=["SYNTHETIC_PURCHASE_DRAFT_CREATED", *request.reason_codes],
    )


def get_procurement_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="get_procurement_requester_profile",
            description="Read a synthetic procurement requester profile.",
            tool_type=ToolType.READ_ONLY,
            input_model=GetProcurementRequesterProfileInput,
            output_model=GetProcurementRequesterProfileOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=get_procurement_requester_profile,
        ),
        ToolDefinition(
            name="get_vendor_info",
            description="Read synthetic vendor information.",
            tool_type=ToolType.READ_ONLY,
            input_model=GetVendorInfoInput,
            output_model=GetVendorInfoOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=get_vendor_info,
        ),
        ToolDefinition(
            name="get_catalog_item",
            description="Read synthetic procurement catalog item information.",
            tool_type=ToolType.READ_ONLY,
            input_model=GetCatalogItemInput,
            output_model=GetCatalogItemOutput,
            risk_level=RiskLevel.LOW,
            requires_approval_by_default=False,
            handler=get_catalog_item,
        ),
        ToolDefinition(
            name="check_procurement_policy",
            description="Evaluate deterministic synthetic procurement policy.",
            tool_type=ToolType.READ_ONLY,
            input_model=CheckProcurementPolicyInput,
            output_model=ProcurementPolicyOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=check_procurement_policy,
        ),
        ToolDefinition(
            name="get_existing_purchase_requests",
            description="Read synthetic purchase requests for duplicate detection.",
            tool_type=ToolType.READ_ONLY,
            input_model=GetExistingPurchaseRequestsInput,
            output_model=GetExistingPurchaseRequestsOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=get_existing_purchase_requests,
        ),
        ToolDefinition(
            name="create_purchase_request_draft",
            description="Create a synthetic purchase request draft only.",
            tool_type=ToolType.STATE_CHANGING,
            input_model=CreatePurchaseRequestDraftInput,
            output_model=CreatePurchaseRequestDraftOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=create_purchase_request_draft,
        ),
    ]


def register_procurement_tools(registry: ToolRegistry) -> ToolRegistry:
    for definition in get_procurement_tool_definitions():
        registry.register(definition)
    return registry


def _find_catalog_item(item_id: str | None, item_name: str | None) -> CatalogItem | None:
    if item_id is not None:
        return CATALOG_ITEMS.get(item_id)
    if item_name is None:
        return None
    normalized_name = item_name.casefold()
    for item in CATALOG_ITEMS.values():
        if item.item_name.casefold() == normalized_name:
            return item
    return None
