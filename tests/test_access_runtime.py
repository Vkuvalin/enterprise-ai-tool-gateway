from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from enterprise_ai_tool_gateway.access import AccessLevel, get_access_tool_definitions
from enterprise_ai_tool_gateway.application import (
    AccessApprovalResolutionRequest,
    AccessWorkflowRequest,
    AccessWorkflowResult,
    AccessWorkflowRuntime,
)
from enterprise_ai_tool_gateway.contracts import (
    AgentRunStatus,
    ApprovalMode,
    ApprovalStatus,
    AuditEventType,
    AuditEventRead,
    DomainTemplate,
    PolicyDecisionStatus,
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
from enterprise_ai_tool_gateway.policy import PolicyCheckRequest, PolicyDecision
from enterprise_ai_tool_gateway.tools import ToolRegistry


async def _build_runtime(
    provider: LLMProviderPort | None = None,
    registry: ToolRegistry | None = None,
    policy_evaluator: Callable[[PolicyCheckRequest], PolicyDecision] | None = None,
) -> tuple[AccessWorkflowRuntime, AsyncEngine, AsyncSession]:
    engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
    await create_database_schema(engine)
    session_factory = create_async_session_factory(engine)
    session = session_factory()
    return (
        AccessWorkflowRuntime(
            session,
            provider=provider,
            registry=registry,
            policy_evaluator=policy_evaluator,
        ),
        engine,
        session,
    )


async def _close_runtime(engine: AsyncEngine, session: AsyncSession) -> None:
    await session.close()
    await engine.dispose()


def _request(
    *,
    employee_id: str | None = "emp-001",
    system_id: str | None = "crm",
    access_level: AccessLevel | None = AccessLevel.READ,
    duration_days: int | None = 30,
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY,
) -> AccessWorkflowRequest:
    return AccessWorkflowRequest(
        user_id="user-1",
        request_text="Need access to CRM.",
        employee_id=employee_id,
        system_id=system_id,
        access_level=access_level,
        duration_days=duration_days,
        justification="Need access for routine work.",
        approval_mode=approval_mode,
    )


async def _with_runtime(
    callback: Callable[[AccessWorkflowRuntime], Awaitable[None]],
    *,
    provider: LLMProviderPort | None = None,
    registry: ToolRegistry | None = None,
    policy_evaluator: Callable[[PolicyCheckRequest], PolicyDecision] | None = None,
) -> None:
    runtime, engine, session = await _build_runtime(provider, registry, policy_evaluator)
    try:
        await callback(runtime)
    finally:
        await _close_runtime(engine, session)


@pytest.mark.asyncio
async def test_low_medium_high_risk_only_completes_without_approval() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(_request())

        assert result.run.status is AgentRunStatus.COMPLETED
        assert result.run.approval_mode is ApprovalMode.HIGH_RISK_ONLY
        assert result.run.risk_level is RiskLevel.MEDIUM
        assert result.approval is None
        assert result.requires_approval is False
        assert _tool_status(result, "create_access_request_draft") is ToolCallStatus.SUCCEEDED
        assert result.final_summary is not None
        assert "Ivan Ivanov" in result.final_summary

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_high_risk_high_risk_only_waits_then_approved_resolution_completes() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        submitted = await runtime.submit_access_request(
            _request(access_level=AccessLevel.ADMIN, approval_mode=ApprovalMode.HIGH_RISK_ONLY)
        )

        assert submitted.run.status is AgentRunStatus.WAITING_FOR_APPROVAL
        assert submitted.run.risk_level is RiskLevel.HIGH
        assert submitted.approval is not None
        assert submitted.approval.status is ApprovalStatus.PENDING
        assert submitted.approval.required_approver_role == "system_owner"
        assert _tool_status(submitted, "create_access_request_draft") is (
            ToolCallStatus.WAITING_FOR_APPROVAL
        )

        resolved = await runtime.resolve_access_approval(
            AccessApprovalResolutionRequest(
                run_id=submitted.run.id,
                approval_id=submitted.approval.id,
                status=ApprovalStatus.APPROVED,
                decided_by="system-owner-1",
                decision_comment="Approved for demo.",
            )
        )

        assert resolved.run.status is AgentRunStatus.COMPLETED
        assert resolved.approval is not None
        assert resolved.approval.status is ApprovalStatus.APPROVED
        assert _tool_status(resolved, "create_access_request_draft") is ToolCallStatus.SUCCEEDED
        assert resolved.final_summary is not None
        assert "ADMIN access" in resolved.final_summary
        assert _event_types(submitted) >= {
            AuditEventType.POLICY_CHECKED,
            AuditEventType.APPROVAL_REQUESTED,
        }
        assert _event_types(resolved) >= {
            AuditEventType.APPROVAL_DECIDED,
            AuditEventType.TOOL_EXECUTED,
            AuditEventType.RUN_COMPLETED,
        }

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_high_risk_auto_approve_completes_without_approval() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(
            _request(access_level=AccessLevel.ADMIN, approval_mode=ApprovalMode.AUTO_APPROVE)
        )

        assert result.run.status is AgentRunStatus.COMPLETED
        assert result.approval is None
        assert _tool_status(result, "create_access_request_draft") is ToolCallStatus.SUCCEEDED

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_low_medium_always_require_waits_for_approval() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(
            _request(approval_mode=ApprovalMode.ALWAYS_REQUIRE)
        )

        assert result.run.status is AgentRunStatus.WAITING_FOR_APPROVAL
        assert result.approval is not None
        assert result.approval.status is ApprovalStatus.PENDING
        assert _tool_status(result, "create_access_request_draft") is (
            ToolCallStatus.WAITING_FOR_APPROVAL
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_missing_input_needs_user_input_without_state_changing_execution() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(
            _request(employee_id=None, duration_days=None)
        )

        assert result.run.status is AgentRunStatus.NEEDS_USER_INPUT
        assert result.tool_calls == []
        assert result.final_summary == (
            "Access request is missing required fields: employee_id, duration_days."
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_unknown_employee_needs_manual_review_without_draft() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(_request(employee_id="missing-employee"))

        assert result.run.status is AgentRunStatus.NEEDS_MANUAL_REVIEW
        assert _tool_names(result) == {
            "get_employee_profile",
            "get_existing_access_tickets",
            "get_system_info",
            "search_access_policy",
        }
        assert "create_access_request_draft" not in _tool_names(result)
        assert AuditEventType.MANUAL_REVIEW_REQUIRED in _event_types(result)

    await _with_runtime(run_case)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("employee_id", "system_id", "expected_reason_code"),
    [
        ("emp-001", "missing-system", "SYSTEM_NOT_FOUND"),
        ("emp-inactive-001", "crm", "EMPLOYEE_INACTIVE"),
        ("emp-duplicate-001", "crm", "OPEN_DUPLICATE_TICKET"),
    ],
)
async def test_manual_review_variants_stop_without_draft(
    employee_id: str,
    system_id: str,
    expected_reason_code: str,
) -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(
            _request(employee_id=employee_id, system_id=system_id)
        )

        assert result.run.status is AgentRunStatus.NEEDS_MANUAL_REVIEW
        assert "create_access_request_draft" not in _tool_names(result)
        manual_review_events = _events_of_type(result, AuditEventType.MANUAL_REVIEW_REQUIRED)
        assert manual_review_events
        reason_codes = manual_review_events[-1].payload["reason_codes"]
        assert isinstance(reason_codes, list)
        assert expected_reason_code in reason_codes

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_forbidden_access_rejected_without_draft() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(
            _request(employee_id="emp-intern-001", access_level=AccessLevel.ADMIN)
        )

        assert result.run.status is AgentRunStatus.REJECTED
        assert "create_access_request_draft" not in _tool_names(result)
        assert result.final_summary == (
            "Access request rejected by policy: intern admin access is forbidden."
        )
        assert {AuditEventType.POLICY_CHECKED, AuditEventType.RUN_REJECTED} <= _event_types(
            result
        )

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_generic_policy_manual_review_status_stops_without_draft() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(_request())

        assert result.run.status is AgentRunStatus.NEEDS_MANUAL_REVIEW
        assert "create_access_request_draft" not in _tool_names(result)
        assert AuditEventType.MANUAL_REVIEW_REQUIRED in _event_types(result)
        policy_events = _events_of_type(result, AuditEventType.POLICY_CHECKED)
        assert policy_events[-1].payload["status"] == PolicyDecisionStatus.NEEDS_MANUAL_REVIEW

    await _with_runtime(
        run_case,
        policy_evaluator=_fixed_policy_evaluator(PolicyDecisionStatus.NEEDS_MANUAL_REVIEW),
    )


@pytest.mark.asyncio
async def test_generic_policy_denied_status_rejects_without_draft() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(_request())

        assert result.run.status is AgentRunStatus.REJECTED
        assert "create_access_request_draft" not in _tool_names(result)
        assert AuditEventType.RUN_REJECTED in _event_types(result)
        policy_events = _events_of_type(result, AuditEventType.POLICY_CHECKED)
        assert policy_events[-1].payload["status"] == PolicyDecisionStatus.DENIED

    await _with_runtime(
        run_case,
        policy_evaluator=_fixed_policy_evaluator(PolicyDecisionStatus.DENIED),
    )


@pytest.mark.asyncio
async def test_approval_rejected_rejects_without_draft() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        submitted = await runtime.submit_access_request(_request(access_level=AccessLevel.ADMIN))
        assert submitted.approval is not None

        resolved = await runtime.resolve_access_approval(
            AccessApprovalResolutionRequest(
                run_id=submitted.run.id,
                approval_id=submitted.approval.id,
                status=ApprovalStatus.REJECTED,
                decided_by="system-owner-1",
                decision_comment="Rejected for demo.",
            )
        )

        assert resolved.run.status is AgentRunStatus.REJECTED
        assert resolved.approval is not None
        assert resolved.approval.status is ApprovalStatus.REJECTED
        action_call = _tool_call(resolved, "create_access_request_draft")
        assert action_call.status is ToolCallStatus.REJECTED
        assert action_call.output_payload is None

    await _with_runtime(run_case)


@pytest.mark.asyncio
async def test_unknown_tool_proposal_failed_validation_without_tool_execution() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(_request())

        assert result.run.status is AgentRunStatus.FAILED_VALIDATION
        assert result.tool_calls == []
        assert AuditEventType.RUN_FAILED in _event_types(result)

    await _with_runtime(run_case, provider=UnknownToolProvider())


@pytest.mark.asyncio
async def test_action_tool_boundary_failure_is_persisted_safely_without_raw_exception() -> None:
    async def run_case(runtime: AccessWorkflowRuntime) -> None:
        result = await runtime.submit_access_request(_request())

        assert result.run.status is AgentRunStatus.FAILED_TOOL
        assert result.run.error_type == "TOOL_EXECUTION_FAILED"
        assert result.run.error_message == "Draft tool execution failed safely."
        action_call = _tool_call(result, "create_access_request_draft")
        assert action_call.status is ToolCallStatus.FAILED
        assert action_call.output_payload is None
        assert action_call.error_message == "Tool boundary failure was handled safely."
        assert AuditEventType.RUN_FAILED in _event_types(result)

    await _with_runtime(run_case, registry=_registry_with_invalid_action_output())


class UnknownToolProvider:
    async def generate_structured_decision(
        self,
        request: LLMDecisionRequest,
    ) -> LLMDecisionResponse:
        _ = request
        return LLMDecisionResponse(
            request_type=RequestType.ACCESS_REQUEST,
            domain_template=DomainTemplate.ACCESS,
            confidence=0.95,
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
            missing_fields=[],
            proposed_tool_calls=[
                ProposedToolCall(
                    name="delete_access_grant",
                    arguments={"employee_id": "emp-001"},
                    requires_approval=True,
                )
            ],
            user_facing_summary="Access request classified.",
            reason_codes=["TEST_UNKNOWN_TOOL"],
        )


def _fixed_policy_evaluator(
    status: PolicyDecisionStatus,
) -> Callable[[PolicyCheckRequest], PolicyDecision]:
    def evaluate(request: PolicyCheckRequest) -> PolicyDecision:
        return PolicyDecision(
            status=status,
            risk_level=request.risk_level,
            reasons=[f"TEST_POLICY_{status.value}"],
            requires_approval=False,
            required_approver_role=None,
            safe_summary=f"Test policy returned {status.value}.",
        )

    return evaluate


def _registry_with_invalid_action_output() -> ToolRegistry:
    registry = ToolRegistry()
    for definition in get_access_tool_definitions():
        if definition.name == "create_access_request_draft":
            registry.register(definition.model_copy(update={"handler": _invalid_action_output}))
        else:
            registry.register(definition)
    return registry


def _invalid_action_output(payload: BaseModel) -> dict[str, object]:
    _ = payload
    return {"status": "draft"}


def _tool_names(result: AccessWorkflowResult) -> set[str]:
    return {tool_call.tool_name for tool_call in result.tool_calls}


def _tool_call(result: AccessWorkflowResult, tool_name: str):
    for tool_call in result.tool_calls:
        if tool_call.tool_name == tool_name:
            return tool_call
    raise AssertionError(f"Tool call {tool_name!r} not found")


def _tool_status(result: AccessWorkflowResult, tool_name: str) -> ToolCallStatus:
    return _tool_call(result, tool_name).status


def _event_types(result: AccessWorkflowResult) -> set[AuditEventType]:
    return {event.event_type for event in result.audit_events}


def _events_of_type(
    result: AccessWorkflowResult,
    event_type: AuditEventType,
) -> list[AuditEventRead]:
    return [event for event in result.audit_events if event.event_type is event_type]
