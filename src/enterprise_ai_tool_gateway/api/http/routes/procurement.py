"""Procurement workflow submit route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from enterprise_ai_tool_gateway.api.http.dependencies import get_procurement_runtime
from enterprise_ai_tool_gateway.api.http.mappers import (
    to_procurement_workflow_request,
    workflow_result_to_response,
)
from enterprise_ai_tool_gateway.api.http.schemas.workflows import (
    ProcurementSubmitRequest,
    WorkflowResultResponse,
)
from enterprise_ai_tool_gateway.application import ProcurementWorkflowRuntime

router = APIRouter(tags=["workflows"])


@router.post("/procurement-requests", response_model=WorkflowResultResponse)
async def submit_procurement_request(
    request: ProcurementSubmitRequest,
    runtime: ProcurementWorkflowRuntime = Depends(get_procurement_runtime),
) -> WorkflowResultResponse:
    result = await runtime.submit_procurement_request(to_procurement_workflow_request(request))
    return workflow_result_to_response(result)
