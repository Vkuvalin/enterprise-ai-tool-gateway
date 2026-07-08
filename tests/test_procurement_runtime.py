from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from enterprise_ai_tool_gateway.application import (
    ProcurementApprovalResolutionRequest,
    ProcurementWorkflowRequest,
    ProcurementWorkflowResult,
    ProcurementWorkflowRuntime,
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
) -> tuple[ProcurementWorkflowRuntime, AsyncEngine, AsyncSession]:
    engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
    await create_database_schema(engine)
    session_factory = create_async_session_factory(engine)
    session = session_factory()
    return (
        ProcurementWorkflowRuntime(session, provider=provider or ProcurementDecisionProvider()),
        engine,
        session,
    )


async def _close_runtime(engine: AsyncEngine, session: AsyncSession) -> None:
    await session.close()
    await engine.dispose()


def _request(
    *,
    requester_id: str | None = "req-001",
    item_id: str | None = "item-laptop",
    item_name: str | None = None,
    quantity: int | None = 1,
    estimated_total: float | None = 900.0,
    cost_center: str | None = "cc-ops",
    justification: str | None = "Need equipment.",
    preferred_vendor_id: str | None = "vendor-approved-001",
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY,
) -> ProcurementWorkflowRequest:
    return ProcurementWorkflowRequest(
        user_id="user-1",
        request_text="Need to buy equipment.",
        requester_id=requester_id,
        item_id=item_id,
        item_name=item_name,
        quantity=quantity,
        estimated_total=estimated_total,
        currency="USD",
        cost_center=cost_center,
        justification=justification,
        preferred_vendor_id=preferred_vendor_id,
        approval_mode=approval_mode,
    )


async def _with_runtime(
    callback: Callable[[ProcurementWorkflowRuntime], Awaitable[None]],
    *,
    provider: LLMProviderPort | None = None,
) -> None:
    runtime, engine, session = await _build_runtime(provider)
    try:
        await callback(runtime)
    finally:
        await _close_runtime(engine, session)


@pytest.mark.asyncio
async def test_low_medium_procurement_completes_without_approval_and_persists_draft() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(_request())

        assert result.run.status is AgentRunStatus.COMPLETED
        assert result.run.risk_level is RiskLevel.MEDIUM
        assert result.requires_approval is False
        assert result.approval is None
        assert _tool_status(result, "create_purchase_request_draft") is ToolCallStatus.SUCCEEDED
        draft_call = _tool_call(result, "create_purchase_request_draft")
        assert draft_call.output_payload is not None
        assert draft_call.output_payload["status"] == "draft"
        assert draft_call.output_payload["requester_id"] == "req-001"
        assert {
            AuditEventType.RUN_CREATED,
            AuditEventType.PROVIDER_SELECTED,
            AuditEventType.DECISION_VALIDATED,
            AuditEventType.POLICY_CHECKED,
            AuditEventType.RUN_COMPLETED,
        } <= _event_types(result)

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_high_value_high_risk_only_waits_then_approved_resolution_completes() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        submitted = await runtime.submit_procurement_request(
            _request(item_id="item-service", estimated_total=1500.0)
        )

        assert submitted.run.status is AgentRunStatus.WAITING_FOR_APPROVAL
        assert submitted.approval is not None
        assert submitted.approval.status is ApprovalStatus.PENDING
        assert submitted.approval.required_approver_role == "procurement_manager"
        assert _tool_status(submitted, "create_purchase_request_draft") is (
            ToolCallStatus.WAITING_FOR_APPROVAL
        )

        resolved = await runtime.resolve_procurement_approval(
            ProcurementApprovalResolutionRequest(
                run_id=submitted.run.id,
                approval_id=submitted.approval.id,
                status=ApprovalStatus.APPROVED,
                decided_by="procurement-manager-1",
                decision_comment="Approved for demo.",
            )
        )

        assert resolved.run.status is AgentRunStatus.COMPLETED
        assert resolved.approval is not None
        assert resolved.approval.status is ApprovalStatus.APPROVED
        assert _tool_status(resolved, "create_purchase_request_draft") is ToolCallStatus.SUCCEEDED
        assert {AuditEventType.APPROVAL_DECIDED, AuditEventType.RUN_COMPLETED} <= _event_types(
            resolved
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_low_medium_auto_approve_completes_without_approval() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(
            _request(approval_mode=ApprovalMode.AUTO_APPROVE)
        )

        assert result.run.status is AgentRunStatus.COMPLETED
        assert result.approval is None
        assert _tool_status(result, "create_purchase_request_draft") is ToolCallStatus.SUCCEEDED

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_high_value_auto_approve_waits_for_approval_without_draft() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(
            _request(
                item_id="item-service",
                estimated_total=1500.0,
                approval_mode=ApprovalMode.AUTO_APPROVE,
            )
        )

        assert result.run.status is AgentRunStatus.WAITING_FOR_APPROVAL
        assert result.approval is not None
        assert result.requires_approval is True
        assert _tool_status(result, "create_purchase_request_draft") is (
            ToolCallStatus.WAITING_FOR_APPROVAL
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_low_medium_always_require_waits_for_approval() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(
            _request(approval_mode=ApprovalMode.ALWAYS_REQUIRE)
        )

        assert result.run.status is AgentRunStatus.WAITING_FOR_APPROVAL
        assert result.approval is not None
        assert _tool_status(result, "create_purchase_request_draft") is (
            ToolCallStatus.WAITING_FOR_APPROVAL
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_total_mismatch_needs_manual_review_without_draft() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(
            _request(quantity=2, estimated_total=900.0)
        )

        assert result.run.status is AgentRunStatus.NEEDS_MANUAL_REVIEW
        assert "create_purchase_request_draft" not in _tool_names(result)
        assert "ESTIMATED_TOTAL_MISMATCH" in _last_reason_codes(
            result, AuditEventType.MANUAL_REVIEW_REQUIRED
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_unknown_cost_center_needs_manual_review_without_draft() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(
            _request(cost_center="missing-cost-center")
        )

        assert result.run.status is AgentRunStatus.NEEDS_MANUAL_REVIEW
        assert "create_purchase_request_draft" not in _tool_names(result)
        assert "COST_CENTER_UNKNOWN" in _last_reason_codes(
            result, AuditEventType.MANUAL_REVIEW_REQUIRED
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_no_preferred_vendor_low_medium_procurement_completes_with_draft() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(_request(preferred_vendor_id=None))

        assert result.run.status is AgentRunStatus.COMPLETED
        assert result.requires_approval is False
        draft_call = _tool_call(result, "create_purchase_request_draft")
        assert draft_call.status is ToolCallStatus.SUCCEEDED
        assert draft_call.output_payload is not None
        assert draft_call.output_payload["vendor_id"] is None
        reason_codes = draft_call.output_payload["reason_codes"]
        assert isinstance(reason_codes, list)
        assert "NO_PREFERRED_VENDOR" in reason_codes

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_computed_total_high_value_waits_for_approval() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(
            _request(quantity=2, estimated_total=1800.0)
        )

        assert result.run.status is AgentRunStatus.WAITING_FOR_APPROVAL
        assert result.approval is not None
        assert _tool_status(result, "create_purchase_request_draft") is (
            ToolCallStatus.WAITING_FOR_APPROVAL
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_missing_input_needs_user_input_without_tool_execution() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(
            _request(requester_id=None, item_id=None, item_name=None, quantity=None)
        )

        assert result.run.status is AgentRunStatus.NEEDS_USER_INPUT
        assert result.tool_calls == []
        assert AuditEventType.USER_INPUT_REQUIRED in _event_types(result)

    await _with_runtime(run_case)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "workflow_request",
    [
        _request(requester_id="missing-requester"),
        _request(preferred_vendor_id="missing-vendor"),
        _request(item_id="missing-item"),
        _request(requester_id="req-inactive-001"),
        _request(requester_id="req-no-purchase-001"),
        _request(cost_center="cc-exceeded", estimated_total=900.0),
        _request(requester_id="req-duplicate-001"),
    ],
)
async def test_manual_review_procurement_variants_stop_without_draft(
    workflow_request: ProcurementWorkflowRequest,
) -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(workflow_request)

        assert result.run.status is AgentRunStatus.NEEDS_MANUAL_REVIEW
        assert "create_purchase_request_draft" not in _tool_names(result)
        assert AuditEventType.MANUAL_REVIEW_REQUIRED in _event_types(result)

    await _with_runtime(run_case)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "workflow_request",
    [
        _request(item_id="item-restricted-001", estimated_total=2000.0),
        _request(preferred_vendor_id="vendor-blocked-001"),
    ],
)
async def test_forbidden_procurement_variants_reject_without_draft(
    workflow_request: ProcurementWorkflowRequest,
) -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(workflow_request)

        assert result.run.status is AgentRunStatus.REJECTED
        assert "create_purchase_request_draft" not in _tool_names(result)
        assert {AuditEventType.POLICY_CHECKED, AuditEventType.RUN_REJECTED} <= _event_types(
            result
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_approval_rejected_rejects_without_draft() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        submitted = await runtime.submit_procurement_request(
            _request(quantity=2, estimated_total=1800.0)
        )
        assert submitted.approval is not None

        resolved = await runtime.resolve_procurement_approval(
            ProcurementApprovalResolutionRequest(
                run_id=submitted.run.id,
                approval_id=submitted.approval.id,
                status=ApprovalStatus.REJECTED,
                decided_by="procurement-manager-1",
                decision_comment="Rejected for demo.",
            )
        )

        assert resolved.run.status is AgentRunStatus.REJECTED
        assert resolved.approval is not None
        assert resolved.approval.status is ApprovalStatus.REJECTED
        action_call = _tool_call(resolved, "create_purchase_request_draft")
        assert action_call.status is ToolCallStatus.REJECTED
        assert action_call.output_payload is None
        assert AuditEventType.RUN_REJECTED in _event_types(resolved)

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_approval_cancelled_rejects_without_draft() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        submitted = await runtime.submit_procurement_request(
            _request(quantity=2, estimated_total=1800.0)
        )
        assert submitted.approval is not None

        resolved = await runtime.resolve_procurement_approval(
            ProcurementApprovalResolutionRequest(
                run_id=submitted.run.id,
                approval_id=submitted.approval.id,
                status=ApprovalStatus.CANCELLED,
                decided_by="procurement-manager-1",
                decision_comment="Cancelled for demo.",
            )
        )

        assert resolved.run.status is AgentRunStatus.REJECTED
        assert resolved.approval is not None
        assert resolved.approval.status is ApprovalStatus.CANCELLED
        action_call = _tool_call(resolved, "create_purchase_request_draft")
        assert action_call.status is ToolCallStatus.REJECTED
        assert action_call.output_payload is None
        assert AuditEventType.RUN_REJECTED in _event_types(resolved)

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_unknown_tool_proposal_failed_validation_without_tool_execution() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(_request())

        assert result.run.status is AgentRunStatus.FAILED_VALIDATION
        assert result.tool_calls == []
        assert AuditEventType.RUN_FAILED in _event_types(result)
        assert "UNKNOWN_TOOL_PROPOSAL" in _last_reason_codes(result, AuditEventType.RUN_FAILED)

    await _with_runtime(run_case, provider=ProcurementDecisionProvider("delete_purchase_order"))


@pytest.mark.asyncio
async def test_request_type_mismatch_failed_validation_without_tool_execution() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(_request())

        assert result.run.status is AgentRunStatus.FAILED_VALIDATION
        assert result.tool_calls == []
        assert "REQUEST_TYPE_MISMATCH" in _last_reason_codes(result, AuditEventType.RUN_FAILED)

    await _with_runtime(
        run_case,
        provider=ProcurementDecisionProvider(request_type=RequestType.ACCESS_REQUEST),
    )


@pytest.mark.asyncio
async def test_domain_template_mismatch_failed_validation_without_tool_execution() -> None:
    async def run_case(runtime: ProcurementWorkflowRuntime) -> None:
        result = await runtime.submit_procurement_request(_request())

        assert result.run.status is AgentRunStatus.FAILED_VALIDATION
        assert result.tool_calls == []
        assert "DOMAIN_TEMPLATE_MISMATCH" in _last_reason_codes(result, AuditEventType.RUN_FAILED)

    await _with_runtime(
        run_case,
        provider=ProcurementDecisionProvider(domain_template=DomainTemplate.ACCESS),
    )


class ProcurementDecisionProvider:
    def __init__(
        self,
        proposed_tool_name: str = "create_purchase_request_draft",
        *,
        request_type: RequestType = RequestType.PROCUREMENT_REQUEST,
        domain_template: DomainTemplate = DomainTemplate.PROCUREMENT,
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
            user_facing_summary="Procurement request classified.",
            reason_codes=["TEST_PROCUREMENT"],
        )


def _tool_names(result: ProcurementWorkflowResult) -> set[str]:
    return {tool_call.tool_name for tool_call in result.tool_calls}


def _tool_call(result: ProcurementWorkflowResult, tool_name: str):
    for tool_call in result.tool_calls:
        if tool_call.tool_name == tool_name:
            return tool_call
    raise AssertionError(f"Tool call {tool_name!r} not found")


def _tool_status(result: ProcurementWorkflowResult, tool_name: str) -> ToolCallStatus:
    return _tool_call(result, tool_name).status


def _event_types(result: ProcurementWorkflowResult) -> set[AuditEventType]:
    return {event.event_type for event in result.audit_events}


def _events_of_type(
    result: ProcurementWorkflowResult,
    event_type: AuditEventType,
) -> list[AuditEventRead]:
    return [event for event in result.audit_events if event.event_type is event_type]


def _last_reason_codes(
    result: ProcurementWorkflowResult,
    event_type: AuditEventType,
) -> list[str]:
    events = _events_of_type(result, event_type)
    assert events
    reason_codes = events[-1].payload["reason_codes"]
    assert isinstance(reason_codes, list)
    return [str(reason_code) for reason_code in reason_codes]
