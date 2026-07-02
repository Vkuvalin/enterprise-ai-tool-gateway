from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeAlias
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from enterprise_ai_tool_gateway.contracts import (
    AgentRunCreate,
    AgentRunStatus,
    ApprovalCreate,
    ApprovalStatus,
    AuditEventCreate,
    AuditEventType,
    DomainTemplate,
    LLMDecisionCreate,
    ProviderName,
    RequestType,
    RiskLevel,
    ToolCallCreate,
    ToolCallStatus,
    ToolType,
)
from enterprise_ai_tool_gateway.db import (
    GatewayRepository,
    create_async_engine_from_url,
    create_async_session_factory,
    create_database_schema,
)
from enterprise_ai_tool_gateway.db.models import (
    ApprovalModel,
    LLMDecisionModel,
    ToolCallModel,
)

MissingRunInsert: TypeAlias = Callable[[GatewayRepository], Awaitable[object]]


async def _build_repository() -> tuple[GatewayRepository, AsyncEngine, AsyncSession]:
    engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
    await create_database_schema(engine)
    session_factory = create_async_session_factory(engine)
    session = session_factory()
    return GatewayRepository(session), engine, session


async def _close_repository(engine: AsyncEngine, session: AsyncSession) -> None:
    await session.close()
    await engine.dispose()


async def _add_llm_decision_with_missing_run(repo: GatewayRepository) -> object:
    return await repo.add_llm_decision(
        LLMDecisionCreate(
            run_id=uuid4(),
            validated_payload={"request_type": RequestType.UNKNOWN.value},
            schema_valid=True,
        )
    )


async def _add_tool_call_with_missing_run(repo: GatewayRepository) -> object:
    return await repo.add_tool_call(
        ToolCallCreate(
            run_id=uuid4(),
            tool_name="fake_policy_lookup",
            tool_type=ToolType.READ_ONLY,
            input_payload={"request_type": RequestType.UNKNOWN.value},
            requires_approval=False,
        )
    )


async def _add_approval_with_missing_run(repo: GatewayRepository) -> object:
    return await repo.add_approval(
        ApprovalCreate(
            run_id=uuid4(),
            required_approver_role="manager",
            summary="Approve action.",
        )
    )


async def _add_audit_event_with_missing_run(repo: GatewayRepository) -> object:
    return await repo.add_audit_event(
        AuditEventCreate(
            run_id=uuid4(),
            event_type=AuditEventType.RUN_CREATED,
            payload={"status": AgentRunStatus.CREATED.value},
        )
    )


@pytest.mark.asyncio
async def test_create_async_engine_session_and_schema() -> None:
    repo, engine, session = await _build_repository()

    try:
        run = await repo.create_agent_run(
            AgentRunCreate(user_id="user-1", request_text="Need access."),
            request_type=RequestType.ACCESS_REQUEST,
            domain_template=DomainTemplate.ACCESS,
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
            provider_name=ProviderName.MOCK,
            model_name="mock-model",
        )
        read_run = await repo.get_agent_run(run.id)

        assert read_run == run
        assert read_run is not None
        assert read_run.model_name == "mock-model"
    finally:
        await _close_repository(engine, session)


@pytest.mark.asyncio
async def test_repository_adds_and_reads_foundation_records() -> None:
    repo, engine, session = await _build_repository()

    try:
        run = await repo.create_agent_run(
            AgentRunCreate(user_id="user-1", request_text="Need access.")
        )
        decision = await repo.add_llm_decision(
            LLMDecisionCreate(
                run_id=run.id,
                validated_payload={"request_type": RequestType.UNKNOWN.value},
                schema_valid=True,
                confidence=0.8,
            )
        )
        tool_call = await repo.add_tool_call(
            ToolCallCreate(
                run_id=run.id,
                tool_name="fake_policy_lookup",
                tool_type=ToolType.READ_ONLY,
                status=ToolCallStatus.SUCCEEDED,
                input_payload={"request_type": RequestType.UNKNOWN.value},
                output_payload={"requires_approval": False},
                requires_approval=False,
            )
        )
        approval = await repo.add_approval(
            ApprovalCreate(
                run_id=run.id,
                tool_call_id=tool_call.id,
                status=ApprovalStatus.PENDING,
                required_approver_role="manager",
                summary="Approve action.",
            )
        )
        event = await repo.add_audit_event(
            AuditEventCreate(
                run_id=run.id,
                event_type=AuditEventType.RUN_CREATED,
                payload={"status": AgentRunStatus.CREATED.value},
            )
        )
        audit_events = await repo.list_audit_events(run.id)
        persisted_decision = await session.scalar(
            select(LLMDecisionModel).where(LLMDecisionModel.id == str(decision.id))
        )
        persisted_tool_call = await session.scalar(
            select(ToolCallModel).where(ToolCallModel.id == str(tool_call.id))
        )
        persisted_approval = await session.scalar(
            select(ApprovalModel).where(ApprovalModel.id == str(approval.id))
        )

        assert decision.run_id == run.id
        assert decision.validated_payload == {"request_type": "UNKNOWN"}
        assert tool_call.output_payload == {"requires_approval": False}
        assert approval.tool_call_id == tool_call.id
        assert audit_events == [event]
        assert persisted_decision is not None
        assert persisted_decision.run_id == str(run.id)
        assert persisted_tool_call is not None
        assert persisted_tool_call.run_id == str(run.id)
        assert persisted_approval is not None
        assert persisted_approval.run_id == str(run.id)
    finally:
        await _close_repository(engine, session)


@pytest.mark.asyncio
async def test_update_status_persists_without_validating_transition() -> None:
    repo, engine, session = await _build_repository()

    try:
        run = await repo.create_agent_run(
            AgentRunCreate(user_id="user-1", request_text="Need access.")
        )

        updated = await repo.update_agent_run_status(run.id, AgentRunStatus.COMPLETED)
        read_run = await repo.get_agent_run(run.id)

        assert updated.status is AgentRunStatus.COMPLETED
        assert read_run is not None
        assert read_run.status is AgentRunStatus.COMPLETED
    finally:
        await _close_repository(engine, session)


@pytest.mark.parametrize(
    "insert_invalid_child",
    [
        _add_llm_decision_with_missing_run,
        _add_tool_call_with_missing_run,
        _add_approval_with_missing_run,
        _add_audit_event_with_missing_run,
    ],
)
@pytest.mark.asyncio
async def test_sqlite_foreign_key_enforcement_rejects_missing_parent_run(
    insert_invalid_child: MissingRunInsert,
) -> None:
    repo, engine, session = await _build_repository()

    try:
        with pytest.raises(IntegrityError):
            await insert_invalid_child(repo)
    finally:
        await _close_repository(engine, session)


@pytest.mark.asyncio
async def test_sqlite_foreign_key_enforcement_rejects_missing_approval_tool_call() -> None:
    repo, engine, session = await _build_repository()

    try:
        run = await repo.create_agent_run(
            AgentRunCreate(user_id="user-1", request_text="Need access.")
        )

        with pytest.raises(IntegrityError):
            await repo.add_approval(
                ApprovalCreate(
                    run_id=run.id,
                    tool_call_id=uuid4(),
                    required_approver_role="manager",
                    summary="Approve action.",
                )
            )
    finally:
        await _close_repository(engine, session)
