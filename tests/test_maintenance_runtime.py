from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from enterprise_ai_tool_gateway.application import (
    MaintenanceApprovalResolutionRequest,
    MaintenanceLiteWorkflowRuntime,
    MaintenanceWorkflowRequest,
    MaintenanceWorkflowResult,
)
from enterprise_ai_tool_gateway.contracts import (
    AgentRunStatus,
    ApprovalMode,
    ApprovalStatus,
    AuditEventRead,
    AuditEventType,
    DomainTemplate,
    ProposedToolCall,
    RequestType,
    RiskLevel,
    ToolCallStatus,
)
from enterprise_ai_tool_gateway.db import (
    create_async_engine_from_url,
    create_async_session_factory,
    create_database_schema,
)
from enterprise_ai_tool_gateway.llm import LLMDecisionRequest, LLMDecisionResponse, LLMProviderPort


async def _build_runtime(
    provider: LLMProviderPort | None = None,
) -> tuple[MaintenanceLiteWorkflowRuntime, AsyncEngine, AsyncSession]:
    engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
    await create_database_schema(engine)
    session_factory = create_async_session_factory(engine)
    session = session_factory()
    return (
        MaintenanceLiteWorkflowRuntime(
            session, provider=provider or MaintenanceDecisionProvider()
        ),
        engine,
        session,
    )


async def _close_runtime(engine: AsyncEngine, session: AsyncSession) -> None:
    await session.close()
    await engine.dispose()


def _request(
    *,
    requester_id: str | None = "maint-req-001",
    asset_id: str | None = "asset-pump-001",
    asset_name: str | None = None,
    issue_description: str | None = "Routine inspection needed.",
    observed_severity: str | None = None,
    safety_concern: bool | None = False,
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY,
) -> MaintenanceWorkflowRequest:
    return MaintenanceWorkflowRequest(
        user_id="user-1",
        request_text="Maintenance request.",
        requester_id=requester_id,
        asset_id=asset_id,
        asset_name=asset_name,
        issue_description=issue_description,
        location="Plant A",
        observed_severity=observed_severity,
        safety_concern=safety_concern,
        approval_mode=approval_mode,
    )


async def _with_runtime(
    callback: Callable[[MaintenanceLiteWorkflowRuntime], Awaitable[None]],
    *,
    provider: LLMProviderPort | None = None,
) -> None:
    runtime, engine, session = await _build_runtime(provider)
    try:
        await callback(runtime)
    finally:
        await _close_runtime(engine, session)


@pytest.mark.asyncio
async def test_low_medium_maintenance_completes_without_approval_and_persists_draft() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(_request())

        assert result.run.status is AgentRunStatus.COMPLETED
        assert result.run.risk_level is RiskLevel.MEDIUM
        assert result.approval is None
        assert _tool_status(result, "create_work_order_draft") is ToolCallStatus.SUCCEEDED
        draft_call = _tool_call(result, "create_work_order_draft")
        assert draft_call.output_payload is not None
        assert draft_call.output_payload["status"] == "draft"
        assert draft_call.output_payload["asset_id"] == "asset-pump-001"
        assert result.final_summary == (
            "Maintenance work order draft created for Cooling pump 1 with LOW severity."
        )
        assert result.final_summary != "Routine inspection needed."
        assert draft_call.output_payload["issue_summary"] == "Routine inspection needed."
        assert {
            AuditEventType.RUN_CREATED,
            AuditEventType.PROVIDER_SELECTED,
            AuditEventType.DECISION_VALIDATED,
            AuditEventType.POLICY_CHECKED,
            AuditEventType.RUN_COMPLETED,
        } <= _event_types(result)

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_high_severity_high_risk_only_waits_then_approved_resolution_completes() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        submitted = await runtime.submit_maintenance_request(
            _request(issue_description="Line stopped after failure.")
        )

        assert submitted.run.status is AgentRunStatus.WAITING_FOR_APPROVAL
        assert submitted.approval is not None
        assert submitted.approval.status is ApprovalStatus.PENDING
        assert submitted.approval.required_approver_role == "maintenance_supervisor"
        assert _tool_status(submitted, "create_work_order_draft") is (
            ToolCallStatus.WAITING_FOR_APPROVAL
        )

        resolved = await runtime.resolve_maintenance_approval(
            MaintenanceApprovalResolutionRequest(
                run_id=submitted.run.id,
                approval_id=submitted.approval.id,
                status=ApprovalStatus.APPROVED,
                decided_by="maintenance-supervisor-1",
                decision_comment="Approved for demo.",
            )
        )

        assert resolved.run.status is AgentRunStatus.COMPLETED
        assert resolved.approval is not None
        assert resolved.approval.status is ApprovalStatus.APPROVED
        assert _tool_status(resolved, "create_work_order_draft") is ToolCallStatus.SUCCEEDED
        assert resolved.final_summary == (
            "Maintenance work order draft created for Cooling pump 1 with HIGH severity."
        )
        assert resolved.final_summary != "Line stopped after failure."
        assert {AuditEventType.APPROVAL_DECIDED, AuditEventType.RUN_COMPLETED} <= _event_types(
            resolved
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_high_severity_auto_approve_completes_without_approval() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(
            _request(
                issue_description="Line stopped after failure.",
                approval_mode=ApprovalMode.AUTO_APPROVE,
            )
        )

        assert result.run.status is AgentRunStatus.COMPLETED
        assert result.approval is None
        assert _tool_status(result, "create_work_order_draft") is ToolCallStatus.SUCCEEDED

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_low_medium_always_require_waits_for_approval() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(
            _request(approval_mode=ApprovalMode.ALWAYS_REQUIRE)
        )

        assert result.run.status is AgentRunStatus.WAITING_FOR_APPROVAL
        assert result.approval is not None
        assert _tool_status(result, "create_work_order_draft") is (
            ToolCallStatus.WAITING_FOR_APPROVAL
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_smoke_text_cannot_be_downgraded_by_observed_low_severity() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(
            _request(issue_description="Smoke near the panel.", observed_severity="LOW")
        )

        assert result.run.status is AgentRunStatus.NEEDS_MANUAL_REVIEW
        assert "create_work_order_draft" not in _tool_names(result)
        severity_call = _tool_call(result, "classify_maintenance_severity")
        assert severity_call.output_payload is not None
        assert severity_call.output_payload["severity"] == "CRITICAL"

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_failure_text_escalates_to_high_despite_observed_low_severity() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(
            _request(
                issue_description="Line stopped after failure.",
                observed_severity="LOW",
            )
        )

        assert result.run.status is AgentRunStatus.WAITING_FOR_APPROVAL
        assert result.approval is not None
        severity_call = _tool_call(result, "classify_maintenance_severity")
        assert severity_call.output_payload is not None
        assert severity_call.output_payload["severity"] == "HIGH"
        assert _tool_status(result, "create_work_order_draft") is (
            ToolCallStatus.WAITING_FOR_APPROVAL
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_missing_input_needs_user_input_without_tool_execution() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(
            _request(requester_id=None, asset_id=None, asset_name=None)
        )

        assert result.run.status is AgentRunStatus.NEEDS_USER_INPUT
        assert result.tool_calls == []
        assert AuditEventType.USER_INPUT_REQUIRED in _event_types(result)

    await _with_runtime(run_case)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "workflow_request",
    [
        _request(asset_id="missing-asset"),
        _request(asset_id="asset-inactive-001"),
        _request(asset_id="asset-decommissioned-001"),
        _request(asset_id="asset-critical-001", issue_description="Line stopped after failure."),
        _request(safety_concern=True),
        _request(asset_id="asset-duplicate-001"),
    ],
)
async def test_manual_review_maintenance_variants_stop_without_draft(
    workflow_request: MaintenanceWorkflowRequest,
) -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(workflow_request)

        assert result.run.status is AgentRunStatus.NEEDS_MANUAL_REVIEW
        assert "create_work_order_draft" not in _tool_names(result)
        assert AuditEventType.MANUAL_REVIEW_REQUIRED in _event_types(result)

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_forbidden_maintenance_request_rejects_without_draft() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(
            _request(issue_description="Please bypass lockout on this asset.")
        )

        assert result.run.status is AgentRunStatus.REJECTED
        assert "create_work_order_draft" not in _tool_names(result)
        assert {AuditEventType.POLICY_CHECKED, AuditEventType.RUN_REJECTED} <= _event_types(
            result
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_approval_rejected_rejects_without_draft() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        submitted = await runtime.submit_maintenance_request(
            _request(issue_description="Line stopped after failure.")
        )
        assert submitted.approval is not None

        resolved = await runtime.resolve_maintenance_approval(
            MaintenanceApprovalResolutionRequest(
                run_id=submitted.run.id,
                approval_id=submitted.approval.id,
                status=ApprovalStatus.REJECTED,
                decided_by="maintenance-supervisor-1",
                decision_comment="Rejected for demo.",
            )
        )

        assert resolved.run.status is AgentRunStatus.REJECTED
        assert resolved.approval is not None
        assert resolved.approval.status is ApprovalStatus.REJECTED
        action_call = _tool_call(resolved, "create_work_order_draft")
        assert action_call.status is ToolCallStatus.REJECTED
        assert action_call.output_payload is None
        assert AuditEventType.RUN_REJECTED in _event_types(resolved)

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_unknown_tool_proposal_failed_validation_without_tool_execution() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(_request())

        assert result.run.status is AgentRunStatus.FAILED_VALIDATION
        assert result.tool_calls == []
        assert AuditEventType.RUN_FAILED in _event_types(result)
        assert "UNKNOWN_TOOL_PROPOSAL" in _last_reason_codes(result, AuditEventType.RUN_FAILED)

    await _with_runtime(run_case, provider=MaintenanceDecisionProvider("dispatch_technician"))


@pytest.mark.asyncio
async def test_request_type_mismatch_failed_validation_without_tool_execution() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(_request())

        assert result.run.status is AgentRunStatus.FAILED_VALIDATION
        assert result.tool_calls == []
        assert "REQUEST_TYPE_MISMATCH" in _last_reason_codes(result, AuditEventType.RUN_FAILED)

    await _with_runtime(
        run_case,
        provider=MaintenanceDecisionProvider(request_type=RequestType.ACCESS_REQUEST),
    )


@pytest.mark.asyncio
async def test_domain_template_mismatch_failed_validation_without_tool_execution() -> None:
    async def run_case(runtime: MaintenanceLiteWorkflowRuntime) -> None:
        result = await runtime.submit_maintenance_request(_request())

        assert result.run.status is AgentRunStatus.FAILED_VALIDATION
        assert result.tool_calls == []
        assert "DOMAIN_TEMPLATE_MISMATCH" in _last_reason_codes(result, AuditEventType.RUN_FAILED)

    await _with_runtime(
        run_case,
        provider=MaintenanceDecisionProvider(domain_template=DomainTemplate.ACCESS),
    )


class MaintenanceDecisionProvider:
    def __init__(
        self,
        proposed_tool_name: str = "create_work_order_draft",
        *,
        request_type: RequestType = RequestType.MAINTENANCE_REQUEST,
        domain_template: DomainTemplate = DomainTemplate.MAINTENANCE_LITE,
    ) -> None:
        self._proposed_tool_name = proposed_tool_name
        self._request_type = request_type
        self._domain_template = domain_template

    async def generate_structured_decision(
        self,
        request: LLMDecisionRequest,
    ) -> LLMDecisionResponse:
        _ = request
        return LLMDecisionResponse(
            request_type=self._request_type,
            domain_template=self._domain_template,
            confidence=0.95,
            risk_level=RiskLevel.MEDIUM,
            requires_approval=False,
            missing_fields=[],
            proposed_tool_calls=[
                ProposedToolCall(
                    name=self._proposed_tool_name,
                    arguments={},
                    requires_approval=False,
                )
            ],
            user_facing_summary="Maintenance request classified.",
            reason_codes=["TEST_MAINTENANCE"],
        )


def _tool_names(result: MaintenanceWorkflowResult) -> set[str]:
    return {tool_call.tool_name for tool_call in result.tool_calls}


def _tool_call(result: MaintenanceWorkflowResult, tool_name: str):
    for tool_call in result.tool_calls:
        if tool_call.tool_name == tool_name:
            return tool_call
    raise AssertionError(f"Tool call {tool_name!r} not found")


def _tool_status(result: MaintenanceWorkflowResult, tool_name: str) -> ToolCallStatus:
    return _tool_call(result, tool_name).status


def _event_types(result: MaintenanceWorkflowResult) -> set[AuditEventType]:
    return {event.event_type for event in result.audit_events}


def _events_of_type(
    result: MaintenanceWorkflowResult,
    event_type: AuditEventType,
) -> list[AuditEventRead]:
    return [event for event in result.audit_events if event.event_type is event_type]


def _last_reason_codes(
    result: MaintenanceWorkflowResult,
    event_type: AuditEventType,
) -> list[str]:
    events = _events_of_type(result, event_type)
    assert events
    reason_codes = events[-1].payload["reason_codes"]
    assert isinstance(reason_codes, list)
    return [str(reason_code) for reason_code in reason_codes]
