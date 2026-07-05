"""FastAPI dependency wiring for DB sessions, repositories and runtimes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from enterprise_ai_tool_gateway.application import (
    AccessWorkflowRuntime,
    MaintenanceLiteWorkflowRuntime,
    ProcurementWorkflowRuntime,
)
from enterprise_ai_tool_gateway.db import GatewayRepository
from enterprise_ai_tool_gateway.llm import (
    MockLLMProvider,
    create_maintenance_demo_provider,
    create_procurement_demo_provider,
)


async def get_async_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = cast(
        async_sessionmaker[AsyncSession],
        request.app.state.session_factory,
    )
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_gateway_repository(
    session: AsyncSession = Depends(get_async_session),
) -> GatewayRepository:
    return GatewayRepository(session)


def get_access_runtime(
    session: AsyncSession = Depends(get_async_session),
) -> AccessWorkflowRuntime:
    return AccessWorkflowRuntime(session, provider=MockLLMProvider())


def get_procurement_runtime(
    session: AsyncSession = Depends(get_async_session),
) -> ProcurementWorkflowRuntime:
    return ProcurementWorkflowRuntime(
        session,
        provider=create_procurement_demo_provider(),
    )


def get_maintenance_runtime(
    session: AsyncSession = Depends(get_async_session),
) -> MaintenanceLiteWorkflowRuntime:
    return MaintenanceLiteWorkflowRuntime(
        session,
        provider=create_maintenance_demo_provider(),
    )
