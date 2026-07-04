from __future__ import annotations

from uuid import uuid4

import pytest

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel, ToolCallStatus
from enterprise_ai_tool_gateway.procurement import (
    BudgetStatus,
    GetCatalogItemOutput,
    GetExistingPurchaseRequestsOutput,
    GetProcurementRequesterProfileOutput,
    GetVendorInfoOutput,
    ProcurementItemCategory,
    ProcurementPolicyOutput,
    RequesterStatus,
    VendorStatus,
    get_procurement_tool_definitions,
    register_procurement_tools,
)
from enterprise_ai_tool_gateway.tools import (
    ToolExecutionNotAuthorizedError,
    ToolExecutionRequest,
    ToolExecutor,
    ToolRegistry,
)


def _build_executor() -> ToolExecutor:
    return ToolExecutor(register_procurement_tools(ToolRegistry()))


def test_all_procurement_tool_definitions_register_successfully() -> None:
    registry = register_procurement_tools(ToolRegistry())

    assert [definition.name for definition in get_procurement_tool_definitions()] == [
        "get_procurement_requester_profile",
        "get_vendor_info",
        "get_catalog_item",
        "check_procurement_policy",
        "get_existing_purchase_requests",
        "create_purchase_request_draft",
    ]
    assert sorted(definition.name for definition in registry.list_tools()) == [
        "check_procurement_policy",
        "create_purchase_request_draft",
        "get_catalog_item",
        "get_existing_purchase_requests",
        "get_procurement_requester_profile",
        "get_vendor_info",
    ]


@pytest.mark.asyncio
async def test_get_procurement_requester_profile_variants() -> None:
    executor = _build_executor()

    found = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_procurement_requester_profile",
            input_payload={"requester_id": "req-001"},
        )
    )
    inactive = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_procurement_requester_profile",
            input_payload={"requester_id": "req-inactive-001"},
        )
    )
    no_permission = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_procurement_requester_profile",
            input_payload={"requester_id": "req-no-purchase-001"},
        )
    )
    missing = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_procurement_requester_profile",
            input_payload={"requester_id": "missing-requester"},
        )
    )

    found_output = GetProcurementRequesterProfileOutput.model_validate(found.output_payload)
    inactive_output = GetProcurementRequesterProfileOutput.model_validate(
        inactive.output_payload
    )
    no_permission_output = GetProcurementRequesterProfileOutput.model_validate(
        no_permission.output_payload
    )
    missing_output = GetProcurementRequesterProfileOutput.model_validate(missing.output_payload)

    assert found_output.found is True
    assert found_output.requester is not None
    assert found_output.requester.status is RequesterStatus.ACTIVE
    assert inactive_output.requester is not None
    assert inactive_output.requester.status is RequesterStatus.INACTIVE
    assert "REQUESTER_INACTIVE" in inactive_output.reason_codes
    assert no_permission_output.requester is not None
    assert no_permission_output.requester.can_purchase is False
    assert "PURCHASE_PERMISSION_MISSING" in no_permission_output.reason_codes
    assert missing_output.found is False
    assert "REQUESTER_NOT_FOUND" in missing_output.reason_codes


@pytest.mark.asyncio
async def test_get_vendor_info_approved_unknown_and_blocked() -> None:
    executor = _build_executor()

    approved = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_vendor_info",
            input_payload={"vendor_id": "vendor-approved-001"},
        )
    )
    unknown = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_vendor_info",
            input_payload={"vendor_id": "missing-vendor"},
        )
    )
    blocked = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_vendor_info",
            input_payload={"vendor_id": "vendor-blocked-001"},
        )
    )

    approved_output = GetVendorInfoOutput.model_validate(approved.output_payload)
    unknown_output = GetVendorInfoOutput.model_validate(unknown.output_payload)
    blocked_output = GetVendorInfoOutput.model_validate(blocked.output_payload)

    assert approved_output.vendor is not None
    assert approved_output.vendor.status is VendorStatus.APPROVED
    assert unknown_output.found is False
    assert "VENDOR_UNKNOWN" in unknown_output.reason_codes
    assert blocked_output.vendor is not None
    assert blocked_output.vendor.status is VendorStatus.BLOCKED
    assert "VENDOR_BLOCKED" in blocked_output.reason_codes


@pytest.mark.asyncio
async def test_get_catalog_item_found_unknown_and_restricted() -> None:
    executor = _build_executor()

    standard = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_catalog_item",
            input_payload={"item_id": "item-laptop", "item_name": None},
        )
    )
    unknown = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_catalog_item",
            input_payload={"item_id": "missing-item", "item_name": None},
        )
    )
    restricted = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_catalog_item",
            input_payload={"item_id": "item-restricted-001", "item_name": None},
        )
    )

    standard_output = GetCatalogItemOutput.model_validate(standard.output_payload)
    unknown_output = GetCatalogItemOutput.model_validate(unknown.output_payload)
    restricted_output = GetCatalogItemOutput.model_validate(restricted.output_payload)

    assert standard_output.item is not None
    assert standard_output.item.category is ProcurementItemCategory.HARDWARE
    assert unknown_output.found is False
    assert "CATALOG_ITEM_NOT_FOUND" in unknown_output.reason_codes
    assert restricted_output.item is not None
    assert restricted_output.item.category is ProcurementItemCategory.RESTRICTED
    assert "RESTRICTED_ITEM" in restricted_output.reason_codes


@pytest.mark.asyncio
async def test_check_procurement_policy_allowed_high_restricted_and_budget_cases() -> None:
    executor = _build_executor()

    standard = await executor.execute(
        ToolExecutionRequest(
            tool_name="check_procurement_policy",
            input_payload=_policy_payload(estimated_total=900.0),
        )
    )
    high_value = await executor.execute(
        ToolExecutionRequest(
            tool_name="check_procurement_policy",
            input_payload=_policy_payload(item_id="item-service", estimated_total=1500.0),
        )
    )
    restricted = await executor.execute(
        ToolExecutionRequest(
            tool_name="check_procurement_policy",
            input_payload=_policy_payload(item_id="item-restricted-001", estimated_total=2000.0),
        )
    )
    budget_exceeded = await executor.execute(
        ToolExecutionRequest(
            tool_name="check_procurement_policy",
            input_payload=_policy_payload(cost_center="cc-exceeded", estimated_total=900.0),
        )
    )

    standard_output = ProcurementPolicyOutput.model_validate(standard.output_payload)
    high_value_output = ProcurementPolicyOutput.model_validate(high_value.output_payload)
    restricted_output = ProcurementPolicyOutput.model_validate(restricted.output_payload)
    budget_output = ProcurementPolicyOutput.model_validate(budget_exceeded.output_payload)

    assert standard_output.allowed is True
    assert standard_output.risk_level is RiskLevel.MEDIUM
    assert standard_output.requires_approval_by_default is False
    assert high_value_output.allowed is True
    assert high_value_output.risk_level is RiskLevel.HIGH
    assert high_value_output.requires_approval_by_default is True
    assert restricted_output.forbidden is True
    assert restricted_output.risk_level is RiskLevel.CRITICAL
    assert "RESTRICTED_ITEM_FORBIDDEN" in restricted_output.reason_codes
    assert budget_output.manual_review is True
    assert budget_output.budget_status is BudgetStatus.EXCEEDED
    assert "BUDGET_EXCEEDED" in budget_output.reason_codes


@pytest.mark.asyncio
async def test_check_procurement_policy_requires_manual_review_for_total_mismatch() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="check_procurement_policy",
            input_payload=_policy_payload(quantity=2, estimated_total=900.0),
        )
    )
    output = ProcurementPolicyOutput.model_validate(result.output_payload)

    assert output.manual_review is True
    assert output.requires_approval_by_default is False
    assert "ESTIMATED_TOTAL_MISMATCH" in output.reason_codes


@pytest.mark.asyncio
async def test_check_procurement_policy_unknown_cost_center_needs_manual_review() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="check_procurement_policy",
            input_payload=_policy_payload(cost_center="missing-cost-center"),
        )
    )
    output = ProcurementPolicyOutput.model_validate(result.output_payload)

    assert output.manual_review is True
    assert output.allowed is False
    assert output.budget_status is BudgetStatus.UNKNOWN
    assert "COST_CENTER_UNKNOWN" in output.reason_codes


@pytest.mark.asyncio
async def test_check_procurement_policy_allows_no_preferred_vendor_when_valid() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="check_procurement_policy",
            input_payload=_policy_payload(preferred_vendor_id=None),
        )
    )
    output = ProcurementPolicyOutput.model_validate(result.output_payload)

    assert output.allowed is True
    assert output.manual_review is False
    assert output.requires_approval_by_default is False
    assert "NO_PREFERRED_VENDOR" in output.reason_codes


@pytest.mark.asyncio
async def test_check_procurement_policy_uses_computed_total_for_high_value() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="check_procurement_policy",
            input_payload=_policy_payload(quantity=2, estimated_total=1800.0),
        )
    )
    output = ProcurementPolicyOutput.model_validate(result.output_payload)

    assert output.allowed is True
    assert output.risk_level is RiskLevel.HIGH
    assert output.requires_approval_by_default is True
    assert "HIGH_VALUE_PURCHASE" in output.reason_codes


@pytest.mark.asyncio
async def test_check_procurement_policy_blocked_vendor_forbidden() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="check_procurement_policy",
            input_payload=_policy_payload(preferred_vendor_id="vendor-blocked-001"),
        )
    )
    output = ProcurementPolicyOutput.model_validate(result.output_payload)

    assert output.forbidden is True
    assert output.risk_level is RiskLevel.CRITICAL
    assert "BLOCKED_VENDOR_FORBIDDEN" in output.reason_codes


@pytest.mark.asyncio
async def test_get_existing_purchase_requests_detects_duplicate() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="get_existing_purchase_requests",
            input_payload={
                "requester_id": "req-duplicate-001",
                "item_id": "item-laptop",
                "item_name": None,
            },
        )
    )
    output = GetExistingPurchaseRequestsOutput.model_validate(result.output_payload)

    assert output.has_open_duplicate is True
    assert "OPEN_DUPLICATE_PURCHASE_REQUEST" in output.reason_codes


@pytest.mark.asyncio
async def test_create_purchase_request_draft_returns_synthetic_draft() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="create_purchase_request_draft",
            input_payload={
                "run_id": str(uuid4()),
                "requester_id": "req-001",
                "item_id": "item-laptop",
                "item_name": "Standard laptop",
                "vendor_id": "vendor-approved-001",
                "quantity": 1,
                "estimated_total": 900.0,
                "currency": "USD",
                "cost_center": "cc-ops",
                "justification": "Need equipment.",
                "reason_codes": ["STANDARD_PURCHASE"],
            },
            execution_authorized=True,
        )
    )

    assert result.status is ToolCallStatus.SUCCEEDED
    assert result.output_payload is not None
    assert result.output_payload["status"] == "draft"
    assert result.output_payload["requester_id"] == "req-001"
    reason_codes = result.output_payload["reason_codes"]
    assert isinstance(reason_codes, list)
    assert "SYNTHETIC_PURCHASE_DRAFT_CREATED" in reason_codes


@pytest.mark.asyncio
async def test_create_purchase_request_draft_blocked_without_authorization() -> None:
    with pytest.raises(ToolExecutionNotAuthorizedError):
        await _build_executor().execute(
            ToolExecutionRequest(
                tool_name="create_purchase_request_draft",
                input_payload={
                    "run_id": str(uuid4()),
                    "requester_id": "req-001",
                    "item_id": "item-laptop",
                    "item_name": "Standard laptop",
                    "vendor_id": None,
                    "quantity": 1,
                    "estimated_total": 900.0,
                    "currency": "USD",
                    "cost_center": "cc-ops",
                    "justification": "Need equipment.",
                    "reason_codes": [],
                },
            )
        )


def _policy_payload(
    *,
    item_id: str = "item-laptop",
    quantity: int = 1,
    estimated_total: float = 900.0,
    cost_center: str = "cc-ops",
    preferred_vendor_id: str | None = "vendor-approved-001",
) -> dict[str, object]:
    return {
        "requester_id": "req-001",
        "item_id": item_id,
        "item_name": None,
        "quantity": quantity,
        "estimated_total": estimated_total,
        "currency": "USD",
        "cost_center": cost_center,
        "preferred_vendor_id": preferred_vendor_id,
    }
