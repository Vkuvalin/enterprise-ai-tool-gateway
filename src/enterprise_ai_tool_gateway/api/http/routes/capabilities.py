"""Capabilities endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from enterprise_ai_tool_gateway.api.http.schemas.capabilities import (
    CapabilitiesResponse,
    ModelSelectionResponse,
)
from enterprise_ai_tool_gateway.contracts.enums import ApprovalMode, RequestType

router = APIRouter(tags=["capabilities"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities() -> CapabilitiesResponse:
    return CapabilitiesResponse(
        workflows=[
            RequestType.ACCESS_REQUEST.value,
            RequestType.PROCUREMENT_REQUEST.value,
            RequestType.MAINTENANCE_REQUEST.value,
        ],
        approval_modes=[mode.value for mode in ApprovalMode],
        provider_mode="mock",
        model_selection=ModelSelectionResponse(
            enabled=False,
            active_profile="mock",
            available_profiles=["mock"],
            note="Model/provider selection is deferred.",
        ),
    )
