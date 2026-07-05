"""Access workflow submit route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from enterprise_ai_tool_gateway.api.http.dependencies import get_access_runtime
from enterprise_ai_tool_gateway.api.http.mappers import (
    to_access_workflow_request,
    workflow_result_to_response,
)
from enterprise_ai_tool_gateway.api.http.schemas.workflows import (
    AccessSubmitRequest,
    WorkflowResultResponse,
)
from enterprise_ai_tool_gateway.application import AccessWorkflowRuntime

router = APIRouter(tags=["workflows"])


@router.post("/access-requests", response_model=WorkflowResultResponse)
async def submit_access_request(
    request: AccessSubmitRequest,
    runtime: AccessWorkflowRuntime = Depends(get_access_runtime),
) -> WorkflowResultResponse:
    result = await runtime.submit_access_request(to_access_workflow_request(request))
    return workflow_result_to_response(result)
