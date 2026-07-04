from __future__ import annotations

from uuid import uuid4

import pytest

from enterprise_ai_tool_gateway.application.demo_workflow import (
    ToolPlanItem,
    apply_approval_decision,
    collect_runtime_records,
    create_pending_approval,
    create_safe_failed_result,
    execute_tool_and_persist,
    find_missing_fields,
    map_policy_decision_to_runtime_step,
    validate_allowed_tool_names,
)
from enterprise_ai_tool_gateway.contracts import (
    AgentRunCreate,
    AgentRunStatus,
    ApprovalMode,
    ApprovalStatus,
    AuditEventType,
    DomainTemplate,
    LLMDecisionPayload,
    PolicyDecisionStatus,
    ProposedToolCall,
    ProviderName,
    RequestType,
    RiskLevel,
    ToolCallStatus,
    ToolType,
)
from enterprise_ai_tool_gateway.db import (
    GatewayRepository,
    create_async_engine_from_url,
    create_async_session_factory,
    create_database_schema,
)
from enterprise_ai_tool_gateway.policy import PolicyDecision
from enterprise_ai_tool_gateway.tools import ToolExecutor, ToolRegistry
from enterprise_ai_tool_gateway.workflow import WorkflowEventType


def test_find_missing_fields_supports_alternative_groups() -> None:
    assert find_missing_fields(
        {
            "requester_id": "req-001",
            "item_id": None,
            "item_name": " ",
            "quantity": 1,
            "justification": None,
        },
        ["requester_id", ("item_id", "item_name"), "quantity", "justification"],
    ) == ["item_id/item_name", "justification"]


def test_validate_allowed_tool_names_rejects_unknown_provider_proposals() -> None:
    registry = ToolRegistry()
    decision = LLMDecisionPayload(
        request_type=RequestType.PROCUREMENT_REQUEST,
        domain_template=DomainTemplate.PROCUREMENT,
        confidence=0.95,
        risk_level=RiskLevel.MEDIUM,
        requires_approval=False,
        proposed_tool_calls=[
            ProposedToolCall(name="known_tool", arguments={}, requires_approval=False),
            ProposedToolCall(name="unknown_tool", arguments={}, requires_approval=False),
        ],
        user_facing_summary="Decision.",
    )

    assert validate_allowed_tool_names(decision, {"known_tool"}, registry) == [
        "known_tool",
        "unknown_tool",
    ]


@pytest.mark.parametrize(
    ("status", "expected_event"),
    [
        (PolicyDecisionStatus.ALLOWED, WorkflowEventType.POLICY_ALLOWED_ACTION),
        (PolicyDecisionStatus.REQUIRES_APPROVAL, WorkflowEventType.POLICY_REQUIRES_APPROVAL),
        (PolicyDecisionStatus.NEEDS_MANUAL_REVIEW, WorkflowEventType.POLICY_MANUAL_REVIEW),
        (PolicyDecisionStatus.DENIED, WorkflowEventType.POLICY_REJECTED),
    ],
)
def test_map_policy_decision_to_runtime_step_is_exhaustive_for_known_statuses(
    status: PolicyDecisionStatus,
    expected_event: WorkflowEventType,
) -> None:
    decision = PolicyDecision(
        status=status,
        risk_level=RiskLevel.MEDIUM,
        reasons=[f"TEST_{status.value}"],
        requires_approval=status is PolicyDecisionStatus.REQUIRES_APPROVAL,
        required_approver_role="manager"
        if status is PolicyDecisionStatus.REQUIRES_APPROVAL
        else None,
        safe_summary="Test policy decision.",
    )

    assert map_policy_decision_to_runtime_step(decision) is expected_event


@pytest.mark.asyncio
async def test_execute_tool_and_persist_maps_unknown_tool_to_safe_failed_record() -> None:
    engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
    await create_database_schema(engine)
    session = create_async_session_factory(engine)()
    try:
        repo = GatewayRepository(session)
        run = await repo.create_agent_run(
            AgentRunCreate(
                user_id="user-1",
                request_text="Procurement request.",
                approval_mode=ApprovalMode.HIGH_RISK_ONLY,
            )
        )

        tool_call = await execute_tool_and_persist(
            repo,
            ToolExecutor(ToolRegistry()),
            ToolRegistry(),
            run.id,
            ToolPlanItem("missing_tool", {"id": "x"}),
            lambda _tool_name: ToolType.READ_ONLY,
        )
        records = await collect_runtime_records(repo, run)

        assert tool_call.status is ToolCallStatus.FAILED
        assert tool_call.error_message == "Tool boundary failure was handled safely."
        assert AuditEventType.TOOL_EXECUTED in {
            event.event_type for event in records.audit_events
        }
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_pending_approval_and_apply_decision_updates_records() -> None:
    engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
    await create_database_schema(engine)
    session = create_async_session_factory(engine)()
    try:
        repo = GatewayRepository(session)
        run = await repo.create_agent_run(
            AgentRunCreate(
                user_id="user-1",
                request_text="Maintenance request.",
                approval_mode=ApprovalMode.HIGH_RISK_ONLY,
            )
        )
        approval = await create_pending_approval(
            repo,
            run_id=run.id,
            action_tool_name="create_demo_draft",
            action_input_payload={"run_id": str(uuid4())},
            risk_level=RiskLevel.HIGH,
            approver_role="manager",
            summary="Needs approval.",
            reason_codes=["HIGH_RISK"],
        )

        decision, updated_approval = await apply_approval_decision(
            repo,
            approval,
            status=ApprovalStatus.APPROVED,
            decided_by="manager-1",
            decision_comment="Approved.",
        )
        records = await collect_runtime_records(repo, run, updated_approval)

        assert decision.status is ApprovalStatus.APPROVED
        assert updated_approval.status is ApprovalStatus.APPROVED
        assert records.approval is not None
        assert records.approval.status is ApprovalStatus.APPROVED
        assert records.tool_calls[0].status is ToolCallStatus.WAITING_FOR_APPROVAL
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_safe_failed_result_updates_run_and_audit() -> None:
    engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
    await create_database_schema(engine)
    session = create_async_session_factory(engine)()
    try:
        repo = GatewayRepository(session)
        run = await repo.create_agent_run(
            AgentRunCreate(
                user_id="user-1",
                request_text="Procurement request.",
                approval_mode=ApprovalMode.HIGH_RISK_ONLY,
            )
        )

        failed_run = await create_safe_failed_result(
            repo,
            run_id=run.id,
            status=AgentRunStatus.FAILED_VALIDATION,
            request_type=RequestType.PROCUREMENT_REQUEST,
            domain_template=DomainTemplate.PROCUREMENT,
            provider_name=ProviderName.MOCK,
            model_name="mock-provider",
            final_summary="Failed safely.",
            error_type="TEST_ERROR",
            error_message="Safe test error.",
            audit_payload={"status": AgentRunStatus.FAILED_VALIDATION.value},
        )
        records = await collect_runtime_records(repo, failed_run)

        assert failed_run.status is AgentRunStatus.FAILED_VALIDATION
        assert failed_run.error_type == "TEST_ERROR"
        assert AuditEventType.RUN_FAILED in {event.event_type for event in records.audit_events}
    finally:
        await session.close()
        await engine.dispose()
