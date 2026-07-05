"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from enterprise_ai_tool_gateway.api.http.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    return HealthResponse(status="ok")
