"""Stage 8 deterministic acceptance cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from enterprise_ai_tool_gateway.evals.providers import (
    ACCESS_PROVIDER_KEY,
    MAINTENANCE_PROVIDER_KEY,
    PROCUREMENT_PROVIDER_KEY,
)
from enterprise_ai_tool_gateway.contracts.enums import DomainTemplate, RequestType
from enterprise_ai_tool_gateway.llm import LLMProviderPort, StaticDecisionProvider


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    workflow: str
    description: str
    submit_path: str
    request_body: dict[str, Any]
    expected_http_status: int
    expected_status: str
    expected_requires_approval: bool
    expected_draft_created: bool
    approval_decision: str | None
    expected_status_after_approval: str | None
    expected_audit_events: tuple[str, ...]
    expected_reason_codes_any: tuple[str, ...]
    provider_overrides: dict[str, LLMProviderPort] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    check_second_resolve_conflict: bool = False


def acceptance_cases() -> tuple[EvalCase, ...]:
    return (
        EvalCase(
            case_id="access_completed",
            workflow="ACCESS_REQUEST",
            description="Low/medium access request completes and creates a draft.",
            submit_path="/api/v1/access-requests",
            request_body=_access_body(),
            expected_http_status=200,
            expected_status="COMPLETED",
            expected_requires_approval=False,
            expected_draft_created=True,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("RUN_CREATED", "POLICY_CHECKED", "RUN_COMPLETED"),
            expected_reason_codes_any=("STANDARD_ACCESS", "SYNTHETIC_DRAFT_CREATED"),
        ),
        EvalCase(
            case_id="access_approval_approved",
            workflow="ACCESS_REQUEST",
            description="High-risk access request waits and completes after approval.",
            submit_path="/api/v1/access-requests",
            request_body=_access_body(access_level="ADMIN"),
            expected_http_status=200,
            expected_status="WAITING_FOR_APPROVAL",
            expected_requires_approval=True,
            expected_draft_created=True,
            approval_decision="APPROVED",
            expected_status_after_approval="COMPLETED",
            expected_audit_events=(
                "APPROVAL_REQUESTED",
                "APPROVAL_DECIDED",
                "RUN_COMPLETED",
            ),
            expected_reason_codes_any=("TOOL_REQUIRES_APPROVAL_BY_DEFAULT", "CRM_ADMIN_HIGH_RISK"),
            check_second_resolve_conflict=True,
        ),
        EvalCase(
            case_id="access_approval_rejected",
            workflow="ACCESS_REQUEST",
            description="High-risk access request rejects cleanly after denial.",
            submit_path="/api/v1/access-requests",
            request_body=_access_body(access_level="ADMIN"),
            expected_http_status=200,
            expected_status="WAITING_FOR_APPROVAL",
            expected_requires_approval=True,
            expected_draft_created=False,
            approval_decision="REJECTED",
            expected_status_after_approval="REJECTED",
            expected_audit_events=(
                "APPROVAL_REQUESTED",
                "APPROVAL_DECIDED",
                "RUN_REJECTED",
            ),
            expected_reason_codes_any=("TOOL_REQUIRES_APPROVAL_BY_DEFAULT", "CRM_ADMIN_HIGH_RISK"),
            check_second_resolve_conflict=True,
        ),
        EvalCase(
            case_id="access_missing_input",
            workflow="ACCESS_REQUEST",
            description="Access request with missing fields needs user input.",
            submit_path="/api/v1/access-requests",
            request_body=_access_body(employee_id=None, duration_days=None),
            expected_http_status=200,
            expected_status="NEEDS_USER_INPUT",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("USER_INPUT_REQUIRED",),
            expected_reason_codes_any=(),
        ),
        EvalCase(
            case_id="access_manual_review_unknown_system",
            workflow="ACCESS_REQUEST",
            description="Unknown system stops access request for manual review.",
            submit_path="/api/v1/access-requests",
            request_body=_access_body(system_id="missing-system"),
            expected_http_status=200,
            expected_status="NEEDS_MANUAL_REVIEW",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("MANUAL_REVIEW_REQUIRED",),
            expected_reason_codes_any=("SYSTEM_NOT_FOUND",),
        ),
        EvalCase(
            case_id="access_rejected_forbidden",
            workflow="ACCESS_REQUEST",
            description="Forbidden intern admin access is rejected without draft.",
            submit_path="/api/v1/access-requests",
            request_body=_access_body(employee_id="emp-intern-001", access_level="ADMIN"),
            expected_http_status=200,
            expected_status="REJECTED",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("POLICY_CHECKED", "RUN_REJECTED"),
            expected_reason_codes_any=("INTERN_ADMIN_FORBIDDEN",),
        ),
        EvalCase(
            case_id="access_failed_validation_unknown_tool",
            workflow="ACCESS_REQUEST",
            description="Unknown access tool proposal fails validation.",
            submit_path="/api/v1/access-requests",
            request_body=_access_body(),
            expected_http_status=200,
            expected_status="FAILED_VALIDATION",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("RUN_FAILED",),
            expected_reason_codes_any=("UNKNOWN_TOOL_PROPOSAL",),
            provider_overrides={
                ACCESS_PROVIDER_KEY: _unknown_tool_provider(
                    RequestType.ACCESS_REQUEST,
                    DomainTemplate.ACCESS,
                    "delete_access_grant",
                )
            },
        ),
        EvalCase(
            case_id="procurement_completed",
            workflow="PROCUREMENT_REQUEST",
            description="Standard procurement request completes and creates a draft.",
            submit_path="/api/v1/procurement-requests",
            request_body=_procurement_body(),
            expected_http_status=200,
            expected_status="COMPLETED",
            expected_requires_approval=False,
            expected_draft_created=True,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("RUN_CREATED", "POLICY_CHECKED", "RUN_COMPLETED"),
            expected_reason_codes_any=("STANDARD_PURCHASE", "APPROVED_VENDOR"),
        ),
        EvalCase(
            case_id="procurement_approval_approved",
            workflow="PROCUREMENT_REQUEST",
            description="High-value procurement request completes after approval.",
            submit_path="/api/v1/procurement-requests",
            request_body=_procurement_body(item_id="item-service", estimated_total=1500.0),
            expected_http_status=200,
            expected_status="WAITING_FOR_APPROVAL",
            expected_requires_approval=True,
            expected_draft_created=True,
            approval_decision="APPROVED",
            expected_status_after_approval="COMPLETED",
            expected_audit_events=(
                "APPROVAL_REQUESTED",
                "APPROVAL_DECIDED",
                "RUN_COMPLETED",
            ),
            expected_reason_codes_any=("HIGH_VALUE_PURCHASE",),
            check_second_resolve_conflict=True,
        ),
        EvalCase(
            case_id="procurement_approval_rejected",
            workflow="PROCUREMENT_REQUEST",
            description="High-value procurement request rejects after denial.",
            submit_path="/api/v1/procurement-requests",
            request_body=_procurement_body(item_id="item-service", estimated_total=1500.0),
            expected_http_status=200,
            expected_status="WAITING_FOR_APPROVAL",
            expected_requires_approval=True,
            expected_draft_created=False,
            approval_decision="REJECTED",
            expected_status_after_approval="REJECTED",
            expected_audit_events=(
                "APPROVAL_REQUESTED",
                "APPROVAL_DECIDED",
                "RUN_REJECTED",
            ),
            expected_reason_codes_any=("HIGH_VALUE_PURCHASE",),
            check_second_resolve_conflict=True,
        ),
        EvalCase(
            case_id="procurement_missing_input",
            workflow="PROCUREMENT_REQUEST",
            description="Procurement request with missing fields needs user input.",
            submit_path="/api/v1/procurement-requests",
            request_body=_procurement_body(requester_id=None, item_id=None, quantity=None),
            expected_http_status=200,
            expected_status="NEEDS_USER_INPUT",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("USER_INPUT_REQUIRED",),
            expected_reason_codes_any=(),
        ),
        EvalCase(
            case_id="procurement_manual_review_total_mismatch_or_budget",
            workflow="PROCUREMENT_REQUEST",
            description="Estimated total mismatch stops procurement for manual review.",
            submit_path="/api/v1/procurement-requests",
            request_body=_procurement_body(quantity=2, estimated_total=900.0),
            expected_http_status=200,
            expected_status="NEEDS_MANUAL_REVIEW",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("MANUAL_REVIEW_REQUIRED",),
            expected_reason_codes_any=("ESTIMATED_TOTAL_MISMATCH", "BUDGET_EXCEEDED"),
        ),
        EvalCase(
            case_id="procurement_rejected_blocked_vendor_or_restricted_item",
            workflow="PROCUREMENT_REQUEST",
            description="Blocked vendor procurement is rejected without draft.",
            submit_path="/api/v1/procurement-requests",
            request_body=_procurement_body(preferred_vendor_id="vendor-blocked-001"),
            expected_http_status=200,
            expected_status="REJECTED",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("POLICY_CHECKED", "RUN_REJECTED"),
            expected_reason_codes_any=("BLOCKED_VENDOR_FORBIDDEN",),
        ),
        EvalCase(
            case_id="procurement_failed_validation_unknown_tool",
            workflow="PROCUREMENT_REQUEST",
            description="Unknown procurement tool proposal fails validation.",
            submit_path="/api/v1/procurement-requests",
            request_body=_procurement_body(),
            expected_http_status=200,
            expected_status="FAILED_VALIDATION",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("RUN_FAILED",),
            expected_reason_codes_any=("UNKNOWN_TOOL_PROPOSAL",),
            provider_overrides={
                PROCUREMENT_PROVIDER_KEY: _unknown_tool_provider(
                    RequestType.PROCUREMENT_REQUEST,
                    DomainTemplate.PROCUREMENT,
                    "delete_purchase_order",
                )
            },
        ),
        EvalCase(
            case_id="maintenance_completed",
            workflow="MAINTENANCE_REQUEST",
            description="Standard maintenance request completes and creates a draft.",
            submit_path="/api/v1/maintenance-requests",
            request_body=_maintenance_body(),
            expected_http_status=200,
            expected_status="COMPLETED",
            expected_requires_approval=False,
            expected_draft_created=True,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("RUN_CREATED", "POLICY_CHECKED", "RUN_COMPLETED"),
            expected_reason_codes_any=("LOW_SEVERITY_STANDARD",),
        ),
        EvalCase(
            case_id="maintenance_approval_approved",
            workflow="MAINTENANCE_REQUEST",
            description="High severity maintenance request completes after approval.",
            submit_path="/api/v1/maintenance-requests",
            request_body=_maintenance_body(issue_description="Line stopped after failure."),
            expected_http_status=200,
            expected_status="WAITING_FOR_APPROVAL",
            expected_requires_approval=True,
            expected_draft_created=True,
            approval_decision="APPROVED",
            expected_status_after_approval="COMPLETED",
            expected_audit_events=(
                "APPROVAL_REQUESTED",
                "APPROVAL_DECIDED",
                "RUN_COMPLETED",
            ),
            expected_reason_codes_any=("HIGH_SEVERITY_APPROVAL_REQUIRED",),
            check_second_resolve_conflict=True,
        ),
        EvalCase(
            case_id="maintenance_approval_rejected",
            workflow="MAINTENANCE_REQUEST",
            description="High severity maintenance request rejects after denial.",
            submit_path="/api/v1/maintenance-requests",
            request_body=_maintenance_body(issue_description="Line stopped after failure."),
            expected_http_status=200,
            expected_status="WAITING_FOR_APPROVAL",
            expected_requires_approval=True,
            expected_draft_created=False,
            approval_decision="REJECTED",
            expected_status_after_approval="REJECTED",
            expected_audit_events=(
                "APPROVAL_REQUESTED",
                "APPROVAL_DECIDED",
                "RUN_REJECTED",
            ),
            expected_reason_codes_any=("HIGH_SEVERITY_APPROVAL_REQUIRED",),
            check_second_resolve_conflict=True,
        ),
        EvalCase(
            case_id="maintenance_missing_input",
            workflow="MAINTENANCE_REQUEST",
            description="Maintenance request with missing fields needs user input.",
            submit_path="/api/v1/maintenance-requests",
            request_body=_maintenance_body(requester_id=None, asset_id=None),
            expected_http_status=200,
            expected_status="NEEDS_USER_INPUT",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("USER_INPUT_REQUIRED",),
            expected_reason_codes_any=(),
        ),
        EvalCase(
            case_id="maintenance_manual_review_safety_or_critical_asset",
            workflow="MAINTENANCE_REQUEST",
            description="Safety concern stops maintenance request for manual review.",
            submit_path="/api/v1/maintenance-requests",
            request_body=_maintenance_body(safety_concern=True),
            expected_http_status=200,
            expected_status="NEEDS_MANUAL_REVIEW",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("MANUAL_REVIEW_REQUIRED",),
            expected_reason_codes_any=("SAFETY_CONCERN_MANUAL_REVIEW",),
        ),
        EvalCase(
            case_id="maintenance_rejected_forbidden",
            workflow="MAINTENANCE_REQUEST",
            description="Forbidden maintenance instruction is rejected without draft.",
            submit_path="/api/v1/maintenance-requests",
            request_body=_maintenance_body(
                issue_description="Please bypass lockout on this asset."
            ),
            expected_http_status=200,
            expected_status="REJECTED",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("POLICY_CHECKED", "RUN_REJECTED"),
            expected_reason_codes_any=("FORBIDDEN_MAINTENANCE_REQUEST",),
        ),
        EvalCase(
            case_id="maintenance_failed_validation_unknown_tool",
            workflow="MAINTENANCE_REQUEST",
            description="Unknown maintenance tool proposal fails validation.",
            submit_path="/api/v1/maintenance-requests",
            request_body=_maintenance_body(),
            expected_http_status=200,
            expected_status="FAILED_VALIDATION",
            expected_requires_approval=False,
            expected_draft_created=False,
            approval_decision=None,
            expected_status_after_approval=None,
            expected_audit_events=("RUN_FAILED",),
            expected_reason_codes_any=("UNKNOWN_TOOL_PROPOSAL",),
            provider_overrides={
                MAINTENANCE_PROVIDER_KEY: _unknown_tool_provider(
                    RequestType.MAINTENANCE_REQUEST,
                    DomainTemplate.MAINTENANCE_LITE,
                    "dispatch_technician",
                )
            },
        ),
    )


def _access_body(
    *,
    employee_id: str | None = "emp-001",
    system_id: str | None = "crm",
    access_level: str | None = "READ",
    duration_days: int | None = 30,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "user_id": "user-1",
        "request_text": "Need access to CRM.",
        "system_id": system_id,
        "access_level": access_level,
        "justification": "Need access for routine work.",
        "approval_mode": "HIGH_RISK_ONLY",
    }
    if employee_id is not None:
        body["employee_id"] = employee_id
    if duration_days is not None:
        body["duration_days"] = duration_days
    return body


def _procurement_body(
    *,
    requester_id: str | None = "req-001",
    item_id: str | None = "item-laptop",
    quantity: int | None = 1,
    estimated_total: float | None = 900.0,
    cost_center: str | None = "cc-ops",
    preferred_vendor_id: str | None = "vendor-approved-001",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "user_id": "user-1",
        "request_text": "Need to buy equipment.",
        "item_id": item_id,
        "estimated_total": estimated_total,
        "currency": "USD",
        "cost_center": cost_center,
        "justification": "Need equipment.",
        "preferred_vendor_id": preferred_vendor_id,
        "approval_mode": "HIGH_RISK_ONLY",
    }
    if requester_id is not None:
        body["requester_id"] = requester_id
    if quantity is not None:
        body["quantity"] = quantity
    return body


def _maintenance_body(
    *,
    requester_id: str | None = "maint-req-001",
    asset_id: str | None = "asset-pump-001",
    issue_description: str | None = "Routine inspection needed.",
    safety_concern: bool | None = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "user_id": "user-1",
        "request_text": "Maintenance request.",
        "issue_description": issue_description,
        "location": "Plant A",
        "safety_concern": safety_concern,
        "approval_mode": "HIGH_RISK_ONLY",
    }
    if requester_id is not None:
        body["requester_id"] = requester_id
    if asset_id is not None:
        body["asset_id"] = asset_id
    return body


def _unknown_tool_provider(
    request_type: RequestType,
    domain_template: DomainTemplate,
    proposed_tool_name: str,
) -> StaticDecisionProvider:
    return StaticDecisionProvider(
        request_type=request_type,
        domain_template=domain_template,
        proposed_tool_name=proposed_tool_name,
        reason_code="API_UNKNOWN_TOOL_TEST",
        requires_approval=True,
    )
