"""Run read endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from enterprise_ai_tool_gateway.api.http.dependencies import get_gateway_repository
from enterprise_ai_tool_gateway.api.http.errors import not_found
from enterprise_ai_tool_gateway.api.http.mappers import (
    approval_to_response,
    audit_event_to_response,
    run_detail_to_response,
    tool_call_to_response,
)
from enterprise_ai_tool_gateway.api.http.schemas.runs import (
    ApprovalResponse,
    AuditEventResponse,
    RunDetailResponse,
    ToolCallResponse,
)
from enterprise_ai_tool_gateway.db import GatewayRepository

router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run_detail(
    run_id: UUID,
    repo: GatewayRepository = Depends(get_gateway_repository),
) -> RunDetailResponse:
    run = await repo.get_agent_run(run_id)
    if run is None:
        raise not_found("run")
    approvals = await repo.list_approvals(run_id)
    tool_calls = await repo.list_tool_calls(run_id)
    audit_events = await repo.list_audit_events(run_id)
    return run_detail_to_response(
        run,
        approvals=approvals,
        tool_calls=tool_calls,
        audit_events=audit_events,
    )


@router.get("/runs/{run_id}/tool-calls", response_model=list[ToolCallResponse])
async def list_run_tool_calls(
    run_id: UUID,
    repo: GatewayRepository = Depends(get_gateway_repository),
) -> list[ToolCallResponse]:
    await _require_run(run_id, repo)
    return [tool_call_to_response(tool_call) for tool_call in await repo.list_tool_calls(run_id)]


@router.get("/runs/{run_id}/approvals", response_model=list[ApprovalResponse])
async def list_run_approvals(
    run_id: UUID,
    repo: GatewayRepository = Depends(get_gateway_repository),
) -> list[ApprovalResponse]:
    await _require_run(run_id, repo)
    return [approval_to_response(approval) for approval in await repo.list_approvals(run_id)]


@router.get("/runs/{run_id}/audit-events", response_model=list[AuditEventResponse])
async def list_run_audit_events(
    run_id: UUID,
    repo: GatewayRepository = Depends(get_gateway_repository),
) -> list[AuditEventResponse]:
    await _require_run(run_id, repo)
    return [audit_event_to_response(event) for event in await repo.list_audit_events(run_id)]


async def _require_run(run_id: UUID, repo: GatewayRepository) -> None:
    run = await repo.get_agent_run(run_id)
    if run is None:
        raise not_found("run")
