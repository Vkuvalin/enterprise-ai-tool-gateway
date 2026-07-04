from __future__ import annotations

from uuid import uuid4

import pytest

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel, ToolCallStatus
from enterprise_ai_tool_gateway.maintenance_lite import (
    AssetCriticality,
    AssetStatus,
    ClassifyMaintenanceSeverityOutput,
    GetAssetInfoOutput,
    GetMaintenanceRequesterProfileOutput,
    GetOpenMaintenanceTicketsOutput,
    MaintenancePolicyOutput,
    MaintenanceRequesterStatus,
    MaintenanceSeverity,
    get_maintenance_tool_definitions,
    register_maintenance_tools,
)
from enterprise_ai_tool_gateway.tools import (
    ToolExecutionNotAuthorizedError,
    ToolExecutionRequest,
    ToolExecutor,
    ToolRegistry,
)


def _build_executor() -> ToolExecutor:
    return ToolExecutor(register_maintenance_tools(ToolRegistry()))


def test_all_maintenance_tool_definitions_register_successfully() -> None:
    registry = register_maintenance_tools(ToolRegistry())

    assert [definition.name for definition in get_maintenance_tool_definitions()] == [
        "get_maintenance_requester_profile",
        "get_asset_info",
        "classify_maintenance_severity",
        "get_open_maintenance_tickets",
        "check_maintenance_policy",
        "create_work_order_draft",
    ]
    assert sorted(definition.name for definition in registry.list_tools()) == [
        "check_maintenance_policy",
        "classify_maintenance_severity",
        "create_work_order_draft",
        "get_asset_info",
        "get_maintenance_requester_profile",
        "get_open_maintenance_tickets",
    ]


@pytest.mark.asyncio
async def test_get_maintenance_requester_profile_found_missing_and_inactive() -> None:
    executor = _build_executor()

    found = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_maintenance_requester_profile",
            input_payload={"requester_id": "maint-req-001"},
        )
    )
    inactive = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_maintenance_requester_profile",
            input_payload={"requester_id": "maint-req-inactive-001"},
        )
    )
    missing = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_maintenance_requester_profile",
            input_payload={"requester_id": "missing-requester"},
        )
    )

    found_output = GetMaintenanceRequesterProfileOutput.model_validate(found.output_payload)
    inactive_output = GetMaintenanceRequesterProfileOutput.model_validate(
        inactive.output_payload
    )
    missing_output = GetMaintenanceRequesterProfileOutput.model_validate(missing.output_payload)

    assert found_output.requester is not None
    assert found_output.requester.status is MaintenanceRequesterStatus.ACTIVE
    assert inactive_output.requester is not None
    assert inactive_output.requester.status is MaintenanceRequesterStatus.INACTIVE
    assert "MAINTENANCE_REQUESTER_INACTIVE" in inactive_output.reason_codes
    assert missing_output.found is False
    assert "MAINTENANCE_REQUESTER_NOT_FOUND" in missing_output.reason_codes


@pytest.mark.asyncio
async def test_get_asset_info_found_missing_inactive_decommissioned_and_critical() -> None:
    executor = _build_executor()

    normal = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_asset_info",
            input_payload={"asset_id": "asset-pump-001", "asset_name": None},
        )
    )
    missing = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_asset_info",
            input_payload={"asset_id": "missing-asset", "asset_name": None},
        )
    )
    inactive = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_asset_info",
            input_payload={"asset_id": "asset-inactive-001", "asset_name": None},
        )
    )
    decommissioned = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_asset_info",
            input_payload={"asset_id": "asset-decommissioned-001", "asset_name": None},
        )
    )
    critical = await executor.execute(
        ToolExecutionRequest(
            tool_name="get_asset_info",
            input_payload={"asset_id": "asset-critical-001", "asset_name": None},
        )
    )

    normal_output = GetAssetInfoOutput.model_validate(normal.output_payload)
    missing_output = GetAssetInfoOutput.model_validate(missing.output_payload)
    inactive_output = GetAssetInfoOutput.model_validate(inactive.output_payload)
    decommissioned_output = GetAssetInfoOutput.model_validate(decommissioned.output_payload)
    critical_output = GetAssetInfoOutput.model_validate(critical.output_payload)

    assert normal_output.asset is not None
    assert normal_output.asset.status is AssetStatus.ACTIVE
    assert missing_output.found is False
    assert "ASSET_NOT_FOUND" in missing_output.reason_codes
    assert inactive_output.asset is not None
    assert inactive_output.asset.status is AssetStatus.INACTIVE
    assert "ASSET_INACTIVE" in inactive_output.reason_codes
    assert decommissioned_output.asset is not None
    assert decommissioned_output.asset.status is AssetStatus.DECOMMISSIONED
    assert "ASSET_DECOMMISSIONED" in decommissioned_output.reason_codes
    assert critical_output.asset is not None
    assert critical_output.asset.criticality is AssetCriticality.CRITICAL
    assert "SAFETY_SENSITIVE_ASSET" in critical_output.reason_codes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("issue_description", "expected_severity"),
    [
        ("Routine inspection needed.", MaintenanceSeverity.LOW),
        ("Pump has vibration and noise.", MaintenanceSeverity.MEDIUM),
        ("Line stopped after failure.", MaintenanceSeverity.HIGH),
        ("Smoke near the panel.", MaintenanceSeverity.CRITICAL),
    ],
)
async def test_classify_maintenance_severity_variants(
    issue_description: str,
    expected_severity: MaintenanceSeverity,
) -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="classify_maintenance_severity",
            input_payload={
                "issue_description": issue_description,
                "observed_severity": None,
                "safety_concern": False,
            },
        )
    )
    output = ClassifyMaintenanceSeverityOutput.model_validate(result.output_payload)

    assert output.severity is expected_severity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("issue_description", "expected_severity", "expected_reason_code"),
    [
        ("Smoke near the panel.", MaintenanceSeverity.CRITICAL, "SEVERITY_ESCALATED_BY_KEYWORD"),
        (
            "Line stopped after failure.",
            MaintenanceSeverity.HIGH,
            "SEVERITY_ESCALATED_BY_KEYWORD",
        ),
    ],
)
async def test_classify_maintenance_severity_does_not_downgrade_text_signals(
    issue_description: str,
    expected_severity: MaintenanceSeverity,
    expected_reason_code: str,
) -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="classify_maintenance_severity",
            input_payload={
                "issue_description": issue_description,
                "observed_severity": "LOW",
                "safety_concern": False,
            },
        )
    )
    output = ClassifyMaintenanceSeverityOutput.model_validate(result.output_payload)

    assert output.severity is expected_severity
    assert "OBSERVED_SEVERITY_USED" in output.reason_codes
    assert expected_reason_code in output.reason_codes


@pytest.mark.asyncio
async def test_classify_maintenance_severity_safety_concern_overrides_observed_low() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="classify_maintenance_severity",
            input_payload={
                "issue_description": "Routine inspection needed.",
                "observed_severity": "LOW",
                "safety_concern": True,
            },
        )
    )
    output = ClassifyMaintenanceSeverityOutput.model_validate(result.output_payload)

    assert output.severity is MaintenanceSeverity.CRITICAL
    assert "SAFETY_CONCERN_REPORTED" in output.reason_codes
    assert "OBSERVED_SEVERITY_USED" in output.reason_codes
    assert "SEVERITY_ESCALATED_BY_SAFETY_SIGNAL" in output.reason_codes


@pytest.mark.asyncio
async def test_check_maintenance_policy_allowed_approval_manual_and_forbidden_cases() -> None:
    executor = _build_executor()

    low = await executor.execute(
        ToolExecutionRequest(tool_name="check_maintenance_policy", input_payload=_policy_payload())
    )
    high = await executor.execute(
        ToolExecutionRequest(
            tool_name="check_maintenance_policy",
            input_payload=_policy_payload(severity="HIGH"),
        )
    )
    safety = await executor.execute(
        ToolExecutionRequest(
            tool_name="check_maintenance_policy",
            input_payload=_policy_payload(safety_concern=True),
        )
    )
    critical_asset = await executor.execute(
        ToolExecutionRequest(
            tool_name="check_maintenance_policy",
            input_payload=_policy_payload(asset_id="asset-critical-001", severity="HIGH"),
        )
    )
    forbidden = await executor.execute(
        ToolExecutionRequest(
            tool_name="check_maintenance_policy",
            input_payload=_policy_payload(issue_description="Please bypass lockout."),
        )
    )

    low_output = MaintenancePolicyOutput.model_validate(low.output_payload)
    high_output = MaintenancePolicyOutput.model_validate(high.output_payload)
    safety_output = MaintenancePolicyOutput.model_validate(safety.output_payload)
    critical_output = MaintenancePolicyOutput.model_validate(critical_asset.output_payload)
    forbidden_output = MaintenancePolicyOutput.model_validate(forbidden.output_payload)

    assert low_output.allowed is True
    assert low_output.risk_level is RiskLevel.MEDIUM
    assert low_output.requires_approval_by_default is False
    assert high_output.allowed is True
    assert high_output.risk_level is RiskLevel.HIGH
    assert high_output.requires_approval_by_default is True
    assert safety_output.manual_review is True
    assert "SAFETY_CONCERN_MANUAL_REVIEW" in safety_output.reason_codes
    assert critical_output.manual_review is True
    assert "CRITICAL_ASSET_MANUAL_REVIEW" in critical_output.reason_codes
    assert forbidden_output.forbidden is True
    assert "FORBIDDEN_MAINTENANCE_REQUEST" in forbidden_output.reason_codes


@pytest.mark.asyncio
async def test_get_open_maintenance_tickets_detects_duplicate() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="get_open_maintenance_tickets",
            input_payload={"asset_id": "asset-duplicate-001", "asset_name": None},
        )
    )
    output = GetOpenMaintenanceTicketsOutput.model_validate(result.output_payload)

    assert output.has_open_duplicate is True
    assert "OPEN_DUPLICATE_MAINTENANCE_TICKET" in output.reason_codes


@pytest.mark.asyncio
async def test_create_work_order_draft_returns_synthetic_draft() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="create_work_order_draft",
            input_payload={
                "run_id": str(uuid4()),
                "requester_id": "maint-req-001",
                "asset_id": "asset-pump-001",
                "asset_name": "Cooling pump 1",
                "severity": "LOW",
                "location": "Plant A",
                "issue_description": "Routine inspection needed.",
                "safety_concern": False,
                "reason_codes": ["LOW_SEVERITY_STANDARD"],
            },
            execution_authorized=True,
        )
    )

    assert result.status is ToolCallStatus.SUCCEEDED
    assert result.output_payload is not None
    assert result.output_payload["status"] == "draft"
    assert result.output_payload["asset_id"] == "asset-pump-001"
    reason_codes = result.output_payload["reason_codes"]
    assert isinstance(reason_codes, list)
    assert "SYNTHETIC_WORK_ORDER_DRAFT_CREATED" in reason_codes


@pytest.mark.asyncio
async def test_create_work_order_draft_blocked_without_authorization() -> None:
    with pytest.raises(ToolExecutionNotAuthorizedError):
        await _build_executor().execute(
            ToolExecutionRequest(
                tool_name="create_work_order_draft",
                input_payload={
                    "run_id": str(uuid4()),
                    "requester_id": "maint-req-001",
                    "asset_id": "asset-pump-001",
                    "asset_name": "Cooling pump 1",
                    "severity": "LOW",
                    "location": "Plant A",
                    "issue_description": "Routine inspection needed.",
                    "safety_concern": False,
                    "reason_codes": [],
                },
            )
        )


def _policy_payload(
    *,
    asset_id: str = "asset-pump-001",
    issue_description: str = "Routine inspection needed.",
    severity: str = "LOW",
    safety_concern: bool = False,
) -> dict[str, object]:
    return {
        "requester_id": "maint-req-001",
        "asset_id": asset_id,
        "asset_name": None,
        "issue_description": issue_description,
        "severity": severity,
        "safety_concern": safety_concern,
    }
