"""Maintenance workflow submit route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from enterprise_ai_tool_gateway.api.http.dependencies import get_maintenance_runtime
from enterprise_ai_tool_gateway.api.http.mappers import (
    to_maintenance_workflow_request,
    workflow_result_to_response,
)
from enterprise_ai_tool_gateway.api.http.schemas.workflows import (
    MaintenanceSubmitRequest,
    WorkflowResultResponse,
)
from enterprise_ai_tool_gateway.application import MaintenanceLiteWorkflowRuntime

router = APIRouter(tags=["workflows"])


@router.post("/maintenance-requests", response_model=WorkflowResultResponse)
async def submit_maintenance_request(
    request: MaintenanceSubmitRequest,
    runtime: MaintenanceLiteWorkflowRuntime = Depends(get_maintenance_runtime),
) -> WorkflowResultResponse:
    result = await runtime.submit_maintenance_request(to_maintenance_workflow_request(request))
    return workflow_result_to_response(result)
