"""Approval resolution endpoint."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from enterprise_ai_tool_gateway.api.http.dependencies import (
    get_access_runtime,
    get_gateway_repository,
    get_maintenance_runtime,
    get_procurement_runtime,
)
from enterprise_ai_tool_gateway.api.http.errors import conflict, not_found
from enterprise_ai_tool_gateway.api.http.mappers import (
    to_access_approval_request,
    to_maintenance_approval_request,
    to_procurement_approval_request,
    workflow_result_to_response,
)
from enterprise_ai_tool_gateway.api.http.schemas.approvals import ApprovalResolveRequest
from enterprise_ai_tool_gateway.api.http.schemas.workflows import WorkflowResultResponse
from enterprise_ai_tool_gateway.application import (
    AccessWorkflowRuntime,
    MaintenanceLiteWorkflowRuntime,
    ProcurementWorkflowRuntime,
)
from enterprise_ai_tool_gateway.contracts.enums import (
    AgentRunStatus,
    ApprovalStatus,
    DomainTemplate,
    RequestType,
)
from enterprise_ai_tool_gateway.db import GatewayRepository

router = APIRouter(tags=["approvals"])


@router.post("/approvals/{approval_id}/resolve", response_model=WorkflowResultResponse)
async def resolve_approval(
    approval_id: UUID,
    request: ApprovalResolveRequest,
    repo: GatewayRepository = Depends(get_gateway_repository),
    access_runtime: AccessWorkflowRuntime = Depends(get_access_runtime),
    procurement_runtime: ProcurementWorkflowRuntime = Depends(get_procurement_runtime),
    maintenance_runtime: MaintenanceLiteWorkflowRuntime = Depends(get_maintenance_runtime),
) -> WorkflowResultResponse:
    approval = await repo.get_approval(approval_id)
    if approval is None:
        raise not_found("approval")
    if approval.run_id != request.run_id:
        raise conflict("Approval does not belong to the requested run.")
    if approval.status is not ApprovalStatus.PENDING:
        raise conflict("Approval is already resolved.")

    run = await repo.get_agent_run(request.run_id)
    if run is None:
        raise not_found("run")
    if run.status is not AgentRunStatus.WAITING_FOR_APPROVAL:
        raise conflict("Run is not waiting for approval.")

    if run.request_type is RequestType.ACCESS_REQUEST and run.domain_template is DomainTemplate.ACCESS:
        result = await access_runtime.resolve_access_approval(
            to_access_approval_request(approval_id, request)
        )
    elif (
        run.request_type is RequestType.PROCUREMENT_REQUEST
        and run.domain_template is DomainTemplate.PROCUREMENT
    ):
        result = await procurement_runtime.resolve_procurement_approval(
            to_procurement_approval_request(approval_id, request)
        )
    elif (
        run.request_type is RequestType.MAINTENANCE_REQUEST
        and run.domain_template is DomainTemplate.MAINTENANCE_LITE
    ):
        result = await maintenance_runtime.resolve_maintenance_approval(
            to_maintenance_approval_request(approval_id, request)
        )
    else:
        raise conflict("Approval dispatch is unsupported for this run.")

    return workflow_result_to_response(result)
