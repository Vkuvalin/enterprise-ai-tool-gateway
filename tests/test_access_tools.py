from __future__ import annotations

from uuid import uuid4

import pytest

from enterprise_ai_tool_gateway.access import (
    AccessLevel,
    AccessPolicyOutput,
    GetEmployeeProfileOutput,
    GetExistingAccessTicketsOutput,
    GetSystemInfoOutput,
    get_access_tool_definitions,
    register_access_tools,
)
from enterprise_ai_tool_gateway.contracts.enums import RiskLevel, ToolCallStatus
from enterprise_ai_tool_gateway.tools import (
    ToolExecutionNotAuthorizedError,
    ToolExecutionRequest,
    ToolExecutor,
    ToolRegistry,
)


def _build_executor() -> ToolExecutor:
    return ToolExecutor(register_access_tools(ToolRegistry()))


def test_all_access_tool_definitions_register_successfully() -> None:
    registry = register_access_tools(ToolRegistry())

    assert [definition.name for definition in get_access_tool_definitions()] == [
        "get_employee_profile",
        "get_system_info",
        "search_access_policy",
        "get_existing_access_tickets",
        "create_access_request_draft",
    ]
    assert sorted(definition.name for definition in registry.list_tools()) == [
        "create_access_request_draft",
        "get_employee_profile",
        "get_existing_access_tickets",
        "get_system_info",
        "search_access_policy",
    ]


@pytest.mark.asyncio
async def test_get_employee_profile_found() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="get_employee_profile",
            input_payload={"employee_id": "emp-001"},
        )
    )
    output = GetEmployeeProfileOutput.model_validate(result.output_payload)

    assert result.status is ToolCallStatus.SUCCEEDED
    assert output.found is True
    assert output.employee is not None
    assert output.employee.full_name == "Ivan Ivanov"


@pytest.mark.asyncio
async def test_get_employee_profile_not_found() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="get_employee_profile",
            input_payload={"employee_id": "missing-employee"},
        )
    )
    output = GetEmployeeProfileOutput.model_validate(result.output_payload)

    assert output.found is False
    assert output.employee is None
    assert "EMPLOYEE_NOT_FOUND" in output.reason_codes


@pytest.mark.asyncio
async def test_get_system_info_found() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(tool_name="get_system_info", input_payload={"system_id": "crm"})
    )
    output = GetSystemInfoOutput.model_validate(result.output_payload)

    assert output.found is True
    assert output.system is not None
    assert output.system.name == "CRM"
    assert AccessLevel.ADMIN in output.system.available_access_levels


@pytest.mark.asyncio
async def test_get_system_info_not_found() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="get_system_info",
            input_payload={"system_id": "unknown-system"},
        )
    )
    output = GetSystemInfoOutput.model_validate(result.output_payload)

    assert output.found is False
    assert output.system is None
    assert "SYSTEM_NOT_FOUND" in output.reason_codes


@pytest.mark.asyncio
async def test_search_access_policy_medium_read_allowed() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="search_access_policy",
            input_payload={
                "employee_id": "emp-001",
                "system_id": "crm",
                "access_level": "READ",
                "duration_days": 30,
            },
        )
    )
    output = AccessPolicyOutput.model_validate(result.output_payload)

    assert output.allowed is True
    assert output.forbidden is False
    assert output.risk_level is RiskLevel.MEDIUM
    assert output.requires_approval_by_default is False


@pytest.mark.asyncio
async def test_search_access_policy_admin_high_approval_required() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="search_access_policy",
            input_payload={
                "employee_id": "emp-001",
                "system_id": "crm",
                "access_level": "ADMIN",
                "duration_days": 30,
            },
        )
    )
    output = AccessPolicyOutput.model_validate(result.output_payload)

    assert output.allowed is True
    assert output.forbidden is False
    assert output.risk_level is RiskLevel.HIGH
    assert output.requires_approval_by_default is True
    assert output.required_approver_role == "system_owner"


@pytest.mark.parametrize(
    ("input_payload", "expected_reason"),
    [
        (
            {
                "employee_id": "emp-intern-001",
                "system_id": "crm",
                "access_level": "ADMIN",
                "duration_days": 30,
            },
            "INTERN_ADMIN_FORBIDDEN",
        ),
        (
            {
                "employee_id": "emp-001",
                "system_id": "crm",
                "access_level": "READ",
                "duration_days": 31,
            },
            "ACCESS_DURATION_EXCEEDS_MAX",
        ),
    ],
)
@pytest.mark.asyncio
async def test_search_access_policy_forbidden_cases(
    input_payload: dict[str, object],
    expected_reason: str,
) -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(tool_name="search_access_policy", input_payload=input_payload)
    )
    output = AccessPolicyOutput.model_validate(result.output_payload)

    assert output.allowed is False
    assert output.forbidden is True
    assert output.risk_level is RiskLevel.CRITICAL
    assert expected_reason in output.reason_codes


@pytest.mark.asyncio
async def test_get_existing_access_tickets_detects_open_duplicate() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="get_existing_access_tickets",
            input_payload={
                "employee_id": "emp-duplicate-001",
                "system_id": "crm",
                "access_level": "READ",
            },
        )
    )
    output = GetExistingAccessTicketsOutput.model_validate(result.output_payload)

    assert output.has_open_duplicate is True
    assert "OPEN_DUPLICATE_TICKET" in output.reason_codes


@pytest.mark.asyncio
async def test_create_access_request_draft_returns_synthetic_draft() -> None:
    result = await _build_executor().execute(
        ToolExecutionRequest(
            tool_name="create_access_request_draft",
            input_payload={
                "run_id": str(uuid4()),
                "employee_id": "emp-001",
                "system_id": "crm",
                "access_level": "READ",
                "duration_days": 30,
                "justification": "Need customer lookup.",
            },
            execution_authorized=True,
        )
    )

    assert result.status is ToolCallStatus.SUCCEEDED
    assert result.output_payload is not None
    assert result.output_payload["status"] == "draft"
    assert "CRM" in str(result.output_payload["summary"])


@pytest.mark.asyncio
async def test_create_access_request_draft_blocked_without_execution_authorization() -> None:
    with pytest.raises(ToolExecutionNotAuthorizedError):
        await _build_executor().execute(
            ToolExecutionRequest(
                tool_name="create_access_request_draft",
                input_payload={
                    "run_id": str(uuid4()),
                    "employee_id": "emp-001",
                    "system_id": "crm",
                    "access_level": "READ",
                    "duration_days": 30,
                    "justification": None,
                },
            )
        )
