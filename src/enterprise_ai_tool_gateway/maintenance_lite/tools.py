"""Maintenance-lite tool definitions backed by deterministic synthetic data."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel, ToolType
from enterprise_ai_tool_gateway.demo_domain.maintenance_data import (
    ASSETS,
    MAINTENANCE_REQUESTERS,
    OPEN_MAINTENANCE_TICKETS,
)
from enterprise_ai_tool_gateway.maintenance_lite.schemas import (
    AssetCriticality,
    AssetInfo,
    AssetStatus,
    CheckMaintenancePolicyInput,
    ClassifyMaintenanceSeverityInput,
    ClassifyMaintenanceSeverityOutput,
    CreateWorkOrderDraftInput,
    CreateWorkOrderDraftOutput,
    GetAssetInfoInput,
    GetAssetInfoOutput,
    GetMaintenanceRequesterProfileInput,
    GetMaintenanceRequesterProfileOutput,
    GetOpenMaintenanceTicketsInput,
    GetOpenMaintenanceTicketsOutput,
    MaintenancePolicyOutput,
    MaintenanceRequesterStatus,
    MaintenanceSeverity,
    MaintenanceTicketStatus,
)
from enterprise_ai_tool_gateway.tools.base import ToolDefinition
from enterprise_ai_tool_gateway.tools.registry import ToolRegistry

_OPEN_DUPLICATE_STATUSES = {
    MaintenanceTicketStatus.OPEN,
    MaintenanceTicketStatus.PENDING_REVIEW,
    MaintenanceTicketStatus.IN_PROGRESS,
}
_FORBIDDEN_TEXT_MARKERS = (
    "bypass",
    "disable safety",
    "ignore lockout",
    "turn off alarm",
)
_SEVERITY_RANK = {
    MaintenanceSeverity.LOW: 0,
    MaintenanceSeverity.MEDIUM: 1,
    MaintenanceSeverity.HIGH: 2,
    MaintenanceSeverity.CRITICAL: 3,
}


def get_maintenance_requester_profile(
    payload: BaseModel,
) -> GetMaintenanceRequesterProfileOutput:
    request = cast(GetMaintenanceRequesterProfileInput, payload)
    requester = MAINTENANCE_REQUESTERS.get(request.requester_id)
    if requester is None:
        return GetMaintenanceRequesterProfileOutput(
            found=False,
            requester=None,
            reason_codes=["MAINTENANCE_REQUESTER_NOT_FOUND"],
            safe_summary="Requester profile was not found in synthetic maintenance data.",
        )

    reason_codes: list[str] = []
    if requester.status is MaintenanceRequesterStatus.INACTIVE:
        reason_codes.append("MAINTENANCE_REQUESTER_INACTIVE")

    return GetMaintenanceRequesterProfileOutput(
        found=True,
        requester=requester,
        reason_codes=reason_codes,
        safe_summary=f"Maintenance requester profile found for {requester.full_name}.",
    )


def get_asset_info(payload: BaseModel) -> GetAssetInfoOutput:
    request = cast(GetAssetInfoInput, payload)
    asset = _find_asset(request.asset_id, request.asset_name)
    if asset is None:
        return GetAssetInfoOutput(
            found=False,
            asset=None,
            reason_codes=["ASSET_NOT_FOUND"],
            safe_summary="Asset was not found in synthetic maintenance data.",
        )

    reason_codes: list[str] = []
    if asset.status is AssetStatus.INACTIVE:
        reason_codes.append("ASSET_INACTIVE")
    if asset.status is AssetStatus.DECOMMISSIONED:
        reason_codes.append("ASSET_DECOMMISSIONED")
    if asset.criticality is AssetCriticality.CRITICAL or asset.safety_sensitive:
        reason_codes.append("SAFETY_SENSITIVE_ASSET")

    return GetAssetInfoOutput(
        found=True,
        asset=asset,
        reason_codes=reason_codes,
        safe_summary=f"Asset information found for {asset.asset_name}.",
    )


def classify_maintenance_severity(
    payload: BaseModel,
) -> ClassifyMaintenanceSeverityOutput:
    request = cast(ClassifyMaintenanceSeverityInput, payload)
    inferred_severity, reason_codes, inferred_summary = _infer_maintenance_severity(
        request.issue_description, bool(request.safety_concern)
    )
    if request.observed_severity is None:
        return ClassifyMaintenanceSeverityOutput(
            severity=inferred_severity,
            reason_codes=reason_codes,
            safe_summary=inferred_summary,
        )

    observed_severity = request.observed_severity
    reason_codes.append("OBSERVED_SEVERITY_USED")
    if _severity_rank(observed_severity) > _severity_rank(inferred_severity):
        return ClassifyMaintenanceSeverityOutput(
            severity=observed_severity,
            reason_codes=reason_codes,
            safe_summary=f"Observed severity {observed_severity.value} was used.",
        )

    if _severity_rank(inferred_severity) > _severity_rank(observed_severity):
        if bool(request.safety_concern):
            reason_codes.append("SEVERITY_ESCALATED_BY_SAFETY_SIGNAL")
        else:
            reason_codes.append("SEVERITY_ESCALATED_BY_KEYWORD")

    return ClassifyMaintenanceSeverityOutput(
        severity=inferred_severity,
        reason_codes=reason_codes,
        safe_summary=(
            f"Inferred severity {inferred_severity.value} was used for maintenance policy."
        ),
    )


def _infer_maintenance_severity(
    issue_description: str, safety_concern: bool
) -> tuple[MaintenanceSeverity, list[str], str]:
    normalized = issue_description.casefold()
    if safety_concern:
        return (
            MaintenanceSeverity.CRITICAL,
            ["SAFETY_CONCERN_REPORTED"],
            "Safety concern was classified as critical severity.",
        )
    if any(marker in normalized for marker in ("fire", "smoke", "gas", "critical")):
        return (
            MaintenanceSeverity.CRITICAL,
            ["CRITICAL_KEYWORD_MATCH"],
            "Issue text was classified as critical severity.",
        )
    if any(marker in normalized for marker in ("stopped", "shutdown", "failure", "broken")):
        return (
            MaintenanceSeverity.HIGH,
            ["HIGH_SEVERITY_KEYWORD_MATCH"],
            "Issue text was classified as high severity.",
        )
    if any(marker in normalized for marker in ("noise", "vibration", "slow", "warning")):
        return (
            MaintenanceSeverity.MEDIUM,
            ["MEDIUM_SEVERITY_KEYWORD_MATCH"],
            "Issue text was classified as medium severity.",
        )
    return (
        MaintenanceSeverity.LOW,
        ["LOW_SEVERITY_DEFAULT"],
        "Issue text was classified as low severity.",
    )


def _severity_rank(severity: MaintenanceSeverity) -> int:
    return _SEVERITY_RANK[severity]


def get_open_maintenance_tickets(payload: BaseModel) -> GetOpenMaintenanceTicketsOutput:
    request = cast(GetOpenMaintenanceTicketsInput, payload)
    asset_name = (request.asset_name or "").casefold()
    tickets = [
        ticket
        for ticket in OPEN_MAINTENANCE_TICKETS
        if (request.asset_id is not None and ticket.asset_id == request.asset_id)
        or (
            request.asset_id is None
            and asset_name
            and ticket.asset_name.casefold() == asset_name
        )
    ]
    has_open_duplicate = any(ticket.status in _OPEN_DUPLICATE_STATUSES for ticket in tickets)

    return GetOpenMaintenanceTicketsOutput(
        tickets=tickets,
        has_open_duplicate=has_open_duplicate,
        reason_codes=["OPEN_DUPLICATE_MAINTENANCE_TICKET"] if has_open_duplicate else [],
        safe_summary=(
            "Open duplicate maintenance ticket found."
            if has_open_duplicate
            else "No open duplicate maintenance ticket found."
        ),
    )


def check_maintenance_policy(payload: BaseModel) -> MaintenancePolicyOutput:
    request = cast(CheckMaintenancePolicyInput, payload)
    asset = _find_asset(request.asset_id, request.asset_name)
    requester = MAINTENANCE_REQUESTERS.get(request.requester_id)

    if _contains_forbidden_text(request.issue_description):
        return MaintenancePolicyOutput(
            allowed=False,
            forbidden=True,
            manual_review=False,
            risk_level=RiskLevel.CRITICAL,
            requires_approval_by_default=False,
            required_approver_role=None,
            reason_codes=["FORBIDDEN_MAINTENANCE_REQUEST"],
            safe_summary="Maintenance request contains a forbidden unsafe instruction.",
        )

    reason_codes: list[str] = []
    if requester is None:
        reason_codes.append("MAINTENANCE_REQUESTER_NOT_FOUND")
    elif requester.status is MaintenanceRequesterStatus.INACTIVE:
        reason_codes.append("MAINTENANCE_REQUESTER_INACTIVE")

    if asset is None:
        reason_codes.append("ASSET_NOT_FOUND")
    elif asset.status is AssetStatus.INACTIVE:
        reason_codes.append("ASSET_INACTIVE")
    elif asset.status is AssetStatus.DECOMMISSIONED:
        reason_codes.append("ASSET_DECOMMISSIONED")

    if reason_codes:
        return MaintenancePolicyOutput(
            allowed=False,
            forbidden=False,
            manual_review=True,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            required_approver_role="maintenance_review",
            reason_codes=reason_codes,
            safe_summary="Maintenance request needs manual review before draft creation.",
        )

    if asset is None:
        return MaintenancePolicyOutput(
            allowed=False,
            forbidden=False,
            manual_review=True,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            required_approver_role="maintenance_review",
            reason_codes=["MAINTENANCE_POLICY_INPUT_INCOMPLETE"],
            safe_summary="Maintenance policy input was incomplete.",
        )

    if request.safety_concern:
        return MaintenancePolicyOutput(
            allowed=False,
            forbidden=False,
            manual_review=True,
            risk_level=RiskLevel.CRITICAL,
            requires_approval_by_default=False,
            required_approver_role="safety_review",
            reason_codes=["SAFETY_CONCERN_MANUAL_REVIEW"],
            safe_summary="Safety concern requires manual review.",
        )

    if (
        asset.criticality is AssetCriticality.CRITICAL
        and request.severity in {MaintenanceSeverity.HIGH, MaintenanceSeverity.CRITICAL}
    ):
        return MaintenancePolicyOutput(
            allowed=False,
            forbidden=False,
            manual_review=True,
            risk_level=RiskLevel.CRITICAL,
            requires_approval_by_default=False,
            required_approver_role="safety_review",
            reason_codes=["CRITICAL_ASSET_MANUAL_REVIEW"],
            safe_summary="Critical asset issue requires manual review.",
        )

    if request.severity is MaintenanceSeverity.CRITICAL:
        return MaintenancePolicyOutput(
            allowed=False,
            forbidden=False,
            manual_review=True,
            risk_level=RiskLevel.CRITICAL,
            requires_approval_by_default=False,
            required_approver_role="maintenance_review",
            reason_codes=["CRITICAL_SEVERITY_MANUAL_REVIEW"],
            safe_summary="Critical severity requires manual review.",
        )

    if request.severity is MaintenanceSeverity.HIGH:
        return MaintenancePolicyOutput(
            allowed=True,
            forbidden=False,
            manual_review=False,
            risk_level=RiskLevel.HIGH,
            requires_approval_by_default=True,
            required_approver_role="maintenance_supervisor",
            reason_codes=["HIGH_SEVERITY_APPROVAL_REQUIRED"],
            safe_summary="High severity maintenance request requires approval.",
        )

    return MaintenancePolicyOutput(
        allowed=True,
        forbidden=False,
        manual_review=False,
        risk_level=RiskLevel.MEDIUM,
        requires_approval_by_default=False,
        required_approver_role=None,
        reason_codes=[f"{request.severity.value}_SEVERITY_STANDARD"],
        safe_summary="Synthetic maintenance policy allows draft processing.",
    )


def create_work_order_draft(payload: BaseModel) -> CreateWorkOrderDraftOutput:
    request = cast(CreateWorkOrderDraftInput, payload)
    draft_id = f"draft-{str(request.run_id)[:8]}-{request.asset_id}"

    return CreateWorkOrderDraftOutput(
        draft_id=draft_id,
        requester_id=request.requester_id,
        asset_id=request.asset_id,
        asset_name=request.asset_name,
        severity=request.severity,
        location=request.location,
        issue_summary=request.issue_description,
        safety_concern=request.safety_concern,
        reason_codes=["SYNTHETIC_WORK_ORDER_DRAFT_CREATED", *request.reason_codes],
    )


def get_maintenance_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="get_maintenance_requester_profile",
            description="Read a synthetic maintenance requester profile.",
            tool_type=ToolType.READ_ONLY,
            input_model=GetMaintenanceRequesterProfileInput,
            output_model=GetMaintenanceRequesterProfileOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=get_maintenance_requester_profile,
        ),
        ToolDefinition(
            name="get_asset_info",
            description="Read synthetic maintenance asset information.",
            tool_type=ToolType.READ_ONLY,
            input_model=GetAssetInfoInput,
            output_model=GetAssetInfoOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=get_asset_info,
        ),
        ToolDefinition(
            name="classify_maintenance_severity",
            description="Classify synthetic maintenance issue severity.",
            tool_type=ToolType.READ_ONLY,
            input_model=ClassifyMaintenanceSeverityInput,
            output_model=ClassifyMaintenanceSeverityOutput,
            risk_level=RiskLevel.LOW,
            requires_approval_by_default=False,
            handler=classify_maintenance_severity,
        ),
        ToolDefinition(
            name="get_open_maintenance_tickets",
            description="Read synthetic maintenance tickets for duplicate detection.",
            tool_type=ToolType.READ_ONLY,
            input_model=GetOpenMaintenanceTicketsInput,
            output_model=GetOpenMaintenanceTicketsOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=get_open_maintenance_tickets,
        ),
        ToolDefinition(
            name="check_maintenance_policy",
            description="Evaluate deterministic synthetic maintenance policy.",
            tool_type=ToolType.READ_ONLY,
            input_model=CheckMaintenancePolicyInput,
            output_model=MaintenancePolicyOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=check_maintenance_policy,
        ),
        ToolDefinition(
            name="create_work_order_draft",
            description="Create a synthetic work order draft only.",
            tool_type=ToolType.STATE_CHANGING,
            input_model=CreateWorkOrderDraftInput,
            output_model=CreateWorkOrderDraftOutput,
            risk_level=RiskLevel.MEDIUM,
            requires_approval_by_default=False,
            handler=create_work_order_draft,
        ),
    ]


def register_maintenance_tools(registry: ToolRegistry) -> ToolRegistry:
    for definition in get_maintenance_tool_definitions():
        registry.register(definition)
    return registry


def _find_asset(asset_id: str | None, asset_name: str | None) -> AssetInfo | None:
    if asset_id is not None:
        return ASSETS.get(asset_id)
    if asset_name is None:
        return None
    normalized_name = asset_name.casefold()
    for asset in ASSETS.values():
        if asset.asset_name.casefold() == normalized_name:
            return asset
    return None


def _contains_forbidden_text(issue_description: str) -> bool:
    normalized = issue_description.casefold()
    return any(marker in normalized for marker in _FORBIDDEN_TEXT_MARKERS)
