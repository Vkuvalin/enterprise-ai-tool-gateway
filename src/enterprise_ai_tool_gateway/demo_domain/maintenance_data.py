"""Synthetic maintenance data for the Stage 7 maintenance-lite demo template."""

from __future__ import annotations

from datetime import UTC, datetime

from enterprise_ai_tool_gateway.contracts.enums import RiskLevel
from enterprise_ai_tool_gateway.maintenance_lite.schemas import (
    AssetCriticality,
    AssetInfo,
    AssetStatus,
    ExistingMaintenanceTicket,
    MaintenancePolicyRule,
    MaintenanceRequesterProfile,
    MaintenanceRequesterStatus,
    MaintenanceSeverity,
    MaintenanceTicketStatus,
)

MAINTENANCE_REQUESTERS: dict[str, MaintenanceRequesterProfile] = {
    "maint-req-001": MaintenanceRequesterProfile(
        requester_id="maint-req-001",
        full_name="Alexey Morozov",
        status=MaintenanceRequesterStatus.ACTIVE,
        department="Facilities",
        manager_id="maint-mgr-001",
        risk_flags=[],
    ),
    "maint-req-inactive-001": MaintenanceRequesterProfile(
        requester_id="maint-req-inactive-001",
        full_name="Irina Fedorova",
        status=MaintenanceRequesterStatus.INACTIVE,
        department="Production",
        manager_id="maint-mgr-002",
        risk_flags=["INACTIVE_REQUESTER"],
    ),
}

ASSETS: dict[str, AssetInfo] = {
    "asset-pump-001": AssetInfo(
        asset_id="asset-pump-001",
        asset_name="Cooling pump 1",
        status=AssetStatus.ACTIVE,
        criticality=AssetCriticality.MEDIUM,
        location="Plant A",
        safety_sensitive=False,
    ),
    "asset-duplicate-001": AssetInfo(
        asset_id="asset-duplicate-001",
        asset_name="Packaging line 2",
        status=AssetStatus.ACTIVE,
        criticality=AssetCriticality.MEDIUM,
        location="Plant B",
        safety_sensitive=False,
    ),
    "asset-critical-001": AssetInfo(
        asset_id="asset-critical-001",
        asset_name="Boiler safety valve",
        status=AssetStatus.ACTIVE,
        criticality=AssetCriticality.CRITICAL,
        location="Boiler room",
        safety_sensitive=True,
    ),
    "asset-inactive-001": AssetInfo(
        asset_id="asset-inactive-001",
        asset_name="Inactive conveyor",
        status=AssetStatus.INACTIVE,
        criticality=AssetCriticality.LOW,
        location="Warehouse",
        safety_sensitive=False,
    ),
    "asset-decommissioned-001": AssetInfo(
        asset_id="asset-decommissioned-001",
        asset_name="Decommissioned press",
        status=AssetStatus.DECOMMISSIONED,
        criticality=AssetCriticality.HIGH,
        location="Storage",
        safety_sensitive=False,
    ),
}

MAINTENANCE_POLICY_RULES: tuple[MaintenancePolicyRule, ...] = (
    MaintenancePolicyRule(
        severity=MaintenanceSeverity.LOW,
        criticality=AssetCriticality.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
        requires_approval_by_default=False,
        manual_review=False,
        reason_codes=["LOW_SEVERITY_STANDARD"],
    ),
    MaintenancePolicyRule(
        severity=MaintenanceSeverity.MEDIUM,
        criticality=AssetCriticality.MEDIUM,
        risk_level=RiskLevel.MEDIUM,
        requires_approval_by_default=False,
        manual_review=False,
        reason_codes=["MEDIUM_SEVERITY_STANDARD"],
    ),
    MaintenancePolicyRule(
        severity=MaintenanceSeverity.HIGH,
        criticality=AssetCriticality.MEDIUM,
        risk_level=RiskLevel.HIGH,
        requires_approval_by_default=True,
        manual_review=False,
        reason_codes=["HIGH_SEVERITY_APPROVAL_REQUIRED"],
    ),
    MaintenancePolicyRule(
        severity=MaintenanceSeverity.HIGH,
        criticality=AssetCriticality.CRITICAL,
        risk_level=RiskLevel.CRITICAL,
        requires_approval_by_default=False,
        manual_review=True,
        reason_codes=["CRITICAL_ASSET_MANUAL_REVIEW"],
    ),
)

OPEN_MAINTENANCE_TICKETS: tuple[ExistingMaintenanceTicket, ...] = (
    ExistingMaintenanceTicket(
        ticket_id="wo-open-001",
        requester_id="maint-req-001",
        asset_id="asset-duplicate-001",
        asset_name="Packaging line 2",
        status=MaintenanceTicketStatus.OPEN,
        issue_summary="Existing vibration ticket.",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    ),
    ExistingMaintenanceTicket(
        ticket_id="wo-closed-001",
        requester_id="maint-req-001",
        asset_id="asset-pump-001",
        asset_name="Cooling pump 1",
        status=MaintenanceTicketStatus.CLOSED,
        issue_summary="Resolved low-pressure issue.",
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
    ),
)
