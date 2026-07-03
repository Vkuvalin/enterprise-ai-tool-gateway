"""Access tool definitions backed by deterministic synthetic data."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel

from enterprise_ai_tool_gateway.access.schemas import (
    AccessLevel,
    AccessPolicyOutput,
    AccessTicketStatus,
    CreateAccessRequestDraftInput,
    CreateAccessRequestDraftOutput,
    EmployeeStatus,
    EmploymentType,
    GetEmployeeProfileInput,
    GetEmployeeProfileOutput,
    GetExistingAccessTicketsInput,
    GetExistingAccessTicketsOutput,
    GetSystemInfoInput,
    GetSystemInfoOutput,
    SearchAccessPolicyInput,
)
from enterprise_ai_tool_gateway.contracts.enums import RiskLevel, ToolType
from enterprise_ai_tool_gateway.demo_domain.access_data import (
    ACCESS_POLICY_RULES,
    EMPLOYEES,
    EXISTING_ACCESS_TICKETS,
    SYSTEMS,
)
from enterprise_ai_tool_gateway.tools.base import ToolDefinition
from enterprise_ai_tool_gateway.tools.registry import ToolRegistry

_OPEN_DUPLICATE_STATUSES = {
    AccessTicketStatus.OPEN,
    AccessTicketStatus.PENDING_APPROVAL,
}


def get_employee_profile(payload: BaseModel) -> GetEmployeeProfileOutput:
    request = cast(GetEmployeeProfileInput, payload)
    employee = EMPLOYEES.get(request.employee_id)
    if employee is None:
        return GetEmployeeProfileOutput(
            found=False,
            employee=None,
            reason_codes=["EMPLOYEE_NOT_FOUND"],
            safe_summary="Employee profile was not found in synthetic HR data.",
        )

    reason_codes: list[str] = []
    if employee.status is EmployeeStatus.INACTIVE:
        reason_codes.append("EMPLOYEE_INACTIVE")

    return GetEmployeeProfileOutput(
        found=True,
        employee=employee,
        reason_codes=reason_codes,
        safe_summary=f"Employee profile found for {employee.full_name}.",
    )


def get_system_info(payload: BaseModel) -> GetSystemInfoOutput:
    request = cast(GetSystemInfoInput, payload)
    system = SYSTEMS.get(request.system_id)
    if system is None:
        return GetSystemInfoOutput(
            found=False,
            system=None,
            reason_codes=["SYSTEM_NOT_FOUND"],
            safe_summary="System was not found in synthetic catalog data.",
        )

    return GetSystemInfoOutput(
        found=True,
        system=system,
        reason_codes=[],
        safe_summary=f"System information found for {system.name}.",
    )


def search_access_policy(payload: BaseModel) -> AccessPolicyOutput:
    request = cast(SearchAccessPolicyInput, payload)
    employee = EMPLOYEES.get(request.employee_id)

    if employee is not None and (
        employee.employment_type is EmploymentType.INTERN
        and request.access_level is AccessLevel.ADMIN
    ):
        return AccessPolicyOutput(
            allowed=False,
            forbidden=True,
            risk_level=RiskLevel.CRITICAL,
            requires_approval_by_default=False,
            required_approver_role=None,
            reason_codes=["INTERN_ADMIN_FORBIDDEN"],
            safe_summary="Intern admin access is forbidden.",
        )

    rule = ACCESS_POLICY_RULES.get((request.system_id, request.access_level))
    if rule is None:
        return AccessPolicyOutput(
            allowed=False,
            forbidden=True,
            risk_level=RiskLevel.CRITICAL,
            requires_approval_by_default=False,
            required_approver_role=None,
            reason_codes=["ACCESS_POLICY_NOT_FOUND"],
            safe_summary="No matching synthetic access policy rule was found.",
        )

    if request.duration_days > rule.max_duration_days:
        return AccessPolicyOutput(
            allowed=False,
            forbidden=True,
            risk_level=RiskLevel.CRITICAL,
            requires_approval_by_default=False,
            required_approver_role=None,
            reason_codes=["ACCESS_DURATION_EXCEEDS_MAX"],
            safe_summary="Requested access duration exceeds the allowed maximum.",
        )

    return AccessPolicyOutput(
        allowed=not rule.forbidden,
        forbidden=rule.forbidden,
        risk_level=rule.risk_level,
        requires_approval_by_default=rule.requires_approval_by_default,
        required_approver_role=rule.required_approver_role,
        reason_codes=list(rule.reason_codes),
        safe_summary="Synthetic access policy rule matched.",
    )


def get_existing_access_tickets(payload: BaseModel) -> GetExistingAccessTicketsOutput:
    request = cast(GetExistingAccessTicketsInput, payload)
    tickets = [
        ticket
        for ticket in EXISTING_ACCESS_TICKETS
        if ticket.employee_id == request.employee_id
        and ticket.system_id == request.system_id
        and ticket.access_level is request.access_level
    ]
    has_open_duplicate = any(ticket.status in _OPEN_DUPLICATE_STATUSES for ticket in tickets)

    return GetExistingAccessTicketsOutput(
        tickets=tickets,
        has_open_duplicate=has_open_duplicate,
        reason_codes=["OPEN_DUPLICATE_TICKET"] if has_open_duplicate else [],
        safe_summary=(
            "Open duplicate access ticket found."
            if has_open_duplicate
            else "No open duplicate access ticket found."
        ),
    )


def create_access_request_draft(payload: BaseModel) -> CreateAccessRequestDraftOutput:
    request = cast(CreateAccessRequestDraftInput, payload)
    employee = EMPLOYEES.get(request.employee_id)
    system = SYSTEMS.get(request.system_id)
    employee_name = employee.full_name if employee is not None else request.employee_id
    system_name = system.name if system is not None else request.system_id
    draft_id = (
        f"draft-{str(request.run_id)[:8]}-"
        f"{request.employee_id}-{request.system_id}-{request.access_level.value.lower()}"
    )

    return CreateAccessRequestDraftOutput(
        draft_id=draft_id,
        summary=(
            f"Access request draft created for {employee_name} to {system_name} "
            f"with {request.access_level.value} access for {request.duration_days} days."
        ),
        reason_codes=["SYNTHETIC_DRAFT_CREATED"],
    )


def get_access_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="get_employee_profile",
            description="Read a synthetic employee profile for access validation.",
            tool_type=ToolType.READ_ONLY,
            input_model=GetEmployeeProfileInput,
            output_model=GetEmployeeProfileOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=get_employee_profile,
        ),
        ToolDefinition(
            name="get_system_info",
            description="Read synthetic system catalog information.",
            tool_type=ToolType.READ_ONLY,
            input_model=GetSystemInfoInput,
            output_model=GetSystemInfoOutput,
            risk_level=RiskLevel.LOW,
            requires_approval_by_default=False,
            handler=get_system_info,
        ),
        ToolDefinition(
            name="search_access_policy",
            description="Find the synthetic access policy rule for a requested access level.",
            tool_type=ToolType.READ_ONLY,
            input_model=SearchAccessPolicyInput,
            output_model=AccessPolicyOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=search_access_policy,
        ),
        ToolDefinition(
            name="get_existing_access_tickets",
            description="Read synthetic existing access tickets for duplicate detection.",
            tool_type=ToolType.READ_ONLY,
            input_model=GetExistingAccessTicketsInput,
            output_model=GetExistingAccessTicketsOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=get_existing_access_tickets,
        ),
        ToolDefinition(
            name="create_access_request_draft",
            description="Create a synthetic access request draft without granting access.",
            tool_type=ToolType.STATE_CHANGING,
            input_model=CreateAccessRequestDraftInput,
            output_model=CreateAccessRequestDraftOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=create_access_request_draft,
        ),
    ]


def register_access_tools(registry: ToolRegistry) -> ToolRegistry:
    for definition in get_access_tool_definitions():
        registry.register(definition)
    return registry
