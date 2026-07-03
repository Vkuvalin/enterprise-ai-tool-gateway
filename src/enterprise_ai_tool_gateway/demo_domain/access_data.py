"""Synthetic access data used by the Stage 5 access tools."""

from __future__ import annotations

from datetime import UTC, datetime

from enterprise_ai_tool_gateway.access.schemas import (
    AccessLevel,
    AccessPolicyRule,
    AccessTicketStatus,
    EmployeeProfile,
    EmployeeStatus,
    EmploymentType,
    ExistingAccessTicket,
    SystemInfo,
    SystemSensitivity,
)
from enterprise_ai_tool_gateway.contracts.enums import RiskLevel

EMPLOYEES: dict[str, EmployeeProfile] = {
    "emp-001": EmployeeProfile(
        employee_id="emp-001",
        full_name="Ivan Ivanov",
        status=EmployeeStatus.ACTIVE,
        department="Sales",
        role="sales_specialist",
        manager_id="mgr-001",
        employment_type=EmploymentType.EMPLOYEE,
        risk_flags=[],
    ),
    "emp-intern-001": EmployeeProfile(
        employee_id="emp-intern-001",
        full_name="Petr Petrov",
        status=EmployeeStatus.ACTIVE,
        department="Analytics",
        role="trainee",
        manager_id="mgr-002",
        employment_type=EmploymentType.INTERN,
        risk_flags=["TRAINEE"],
    ),
    "emp-inactive-001": EmployeeProfile(
        employee_id="emp-inactive-001",
        full_name="Olga Sidorova",
        status=EmployeeStatus.INACTIVE,
        department="Finance",
        role="accountant",
        manager_id="mgr-003",
        employment_type=EmploymentType.EMPLOYEE,
        risk_flags=["INACTIVE_ACCOUNT"],
    ),
    "emp-duplicate-001": EmployeeProfile(
        employee_id="emp-duplicate-001",
        full_name="Anna Kuznetsova",
        status=EmployeeStatus.ACTIVE,
        department="Support",
        role="support_specialist",
        manager_id="mgr-004",
        employment_type=EmploymentType.EMPLOYEE,
        risk_flags=[],
    ),
}

SYSTEMS: dict[str, SystemInfo] = {
    "crm": SystemInfo(
        system_id="crm",
        name="CRM",
        description="Synthetic customer relationship management system.",
        sensitivity=SystemSensitivity.MEDIUM,
        available_access_levels=[AccessLevel.READ, AccessLevel.WRITE, AccessLevel.ADMIN],
        owner_role="system_owner",
    ),
    "bi": SystemInfo(
        system_id="bi",
        name="BI Dashboard",
        description="Synthetic analytics dashboard for business metrics.",
        sensitivity=SystemSensitivity.HIGH,
        available_access_levels=[AccessLevel.READ, AccessLevel.WRITE],
        owner_role="analytics_owner",
    ),
    "erp": SystemInfo(
        system_id="erp",
        name="ERP",
        description="Synthetic enterprise resource planning system.",
        sensitivity=SystemSensitivity.CRITICAL,
        available_access_levels=[AccessLevel.READ, AccessLevel.ADMIN],
        owner_role="system_owner",
    ),
}

ACCESS_POLICY_RULES: dict[tuple[str, AccessLevel], AccessPolicyRule] = {
    ("crm", AccessLevel.READ): AccessPolicyRule(
        system_id="crm",
        access_level=AccessLevel.READ,
        max_duration_days=30,
        risk_level=RiskLevel.MEDIUM,
        requires_approval_by_default=False,
        forbidden=False,
        required_approver_role=None,
        reason_codes=["CRM_READ_STANDARD"],
    ),
    ("crm", AccessLevel.WRITE): AccessPolicyRule(
        system_id="crm",
        access_level=AccessLevel.WRITE,
        max_duration_days=30,
        risk_level=RiskLevel.MEDIUM,
        requires_approval_by_default=False,
        forbidden=False,
        required_approver_role=None,
        reason_codes=["CRM_WRITE_STANDARD"],
    ),
    ("crm", AccessLevel.ADMIN): AccessPolicyRule(
        system_id="crm",
        access_level=AccessLevel.ADMIN,
        max_duration_days=30,
        risk_level=RiskLevel.HIGH,
        requires_approval_by_default=True,
        forbidden=False,
        required_approver_role="system_owner",
        reason_codes=["CRM_ADMIN_HIGH_RISK"],
    ),
    ("bi", AccessLevel.READ): AccessPolicyRule(
        system_id="bi",
        access_level=AccessLevel.READ,
        max_duration_days=30,
        risk_level=RiskLevel.MEDIUM,
        requires_approval_by_default=False,
        forbidden=False,
        required_approver_role=None,
        reason_codes=["BI_READ_STANDARD"],
    ),
    ("erp", AccessLevel.READ): AccessPolicyRule(
        system_id="erp",
        access_level=AccessLevel.READ,
        max_duration_days=14,
        risk_level=RiskLevel.HIGH,
        requires_approval_by_default=True,
        forbidden=False,
        required_approver_role="system_owner",
        reason_codes=["ERP_READ_HIGH_RISK"],
    ),
    ("erp", AccessLevel.ADMIN): AccessPolicyRule(
        system_id="erp",
        access_level=AccessLevel.ADMIN,
        max_duration_days=7,
        risk_level=RiskLevel.HIGH,
        requires_approval_by_default=True,
        forbidden=False,
        required_approver_role="system_owner",
        reason_codes=["ERP_ADMIN_HIGH_RISK"],
    ),
}

EXISTING_ACCESS_TICKETS: tuple[ExistingAccessTicket, ...] = (
    ExistingAccessTicket(
        ticket_id="ticket-open-001",
        employee_id="emp-duplicate-001",
        system_id="crm",
        access_level=AccessLevel.READ,
        status=AccessTicketStatus.OPEN,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    ),
    ExistingAccessTicket(
        ticket_id="ticket-closed-001",
        employee_id="emp-001",
        system_id="crm",
        access_level=AccessLevel.READ,
        status=AccessTicketStatus.CLOSED,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    ),
)
