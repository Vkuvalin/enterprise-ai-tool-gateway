"""Capabilities response schemas."""

from __future__ import annotations

from enterprise_ai_tool_gateway.api.http.schemas.common import ApiModel


class ModelSelectionResponse(ApiModel):
    enabled: bool
    active_profile: str
    available_profiles: list[str]
    note: str


class CapabilitiesResponse(ApiModel):
    workflows: list[str]
    approval_modes: list[str]
    provider_mode: str
    model_selection: ModelSelectionResponse
