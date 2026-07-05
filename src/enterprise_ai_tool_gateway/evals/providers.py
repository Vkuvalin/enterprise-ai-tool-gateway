"""Eval-only provider override helpers for deterministic API acceptance cases."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_ai_tool_gateway.api.http.dependencies import (
    get_access_runtime,
    get_async_session,
    get_maintenance_runtime,
    get_procurement_runtime,
)
from enterprise_ai_tool_gateway.application import (
    AccessWorkflowRuntime,
    MaintenanceLiteWorkflowRuntime,
    ProcurementWorkflowRuntime,
)
from enterprise_ai_tool_gateway.llm import LLMProviderPort

ACCESS_PROVIDER_KEY = "access"
PROCUREMENT_PROVIDER_KEY = "procurement"
MAINTENANCE_PROVIDER_KEY = "maintenance"

ProviderOverrides = Mapping[str, LLMProviderPort]


def install_provider_dependency_overrides(
    app: FastAPI,
    overrides: ProviderOverrides,
) -> None:
    unknown_keys = set(overrides) - {
        ACCESS_PROVIDER_KEY,
        PROCUREMENT_PROVIDER_KEY,
        MAINTENANCE_PROVIDER_KEY,
    }
    if unknown_keys:
        raise ValueError(f"Unknown provider override keys: {sorted(unknown_keys)}")

    access_provider = overrides.get(ACCESS_PROVIDER_KEY)
    if access_provider is not None:
        app.dependency_overrides[get_access_runtime] = _access_runtime_dependency(
            access_provider
        )

    procurement_provider = overrides.get(PROCUREMENT_PROVIDER_KEY)
    if procurement_provider is not None:
        app.dependency_overrides[get_procurement_runtime] = _procurement_runtime_dependency(
            procurement_provider
        )

    maintenance_provider = overrides.get(MAINTENANCE_PROVIDER_KEY)
    if maintenance_provider is not None:
        app.dependency_overrides[get_maintenance_runtime] = _maintenance_runtime_dependency(
            maintenance_provider
        )


def _access_runtime_dependency(
    provider: LLMProviderPort,
) -> Callable[..., AccessWorkflowRuntime]:
    def _get_access_runtime(
        session: AsyncSession = Depends(get_async_session),
    ) -> AccessWorkflowRuntime:
        return AccessWorkflowRuntime(session, provider=provider)

    return _get_access_runtime


def _procurement_runtime_dependency(
    provider: LLMProviderPort,
) -> Callable[..., ProcurementWorkflowRuntime]:
    def _get_procurement_runtime(
        session: AsyncSession = Depends(get_async_session),
    ) -> ProcurementWorkflowRuntime:
        return ProcurementWorkflowRuntime(session, provider=provider)

    return _get_procurement_runtime


def _maintenance_runtime_dependency(
    provider: LLMProviderPort,
) -> Callable[..., MaintenanceLiteWorkflowRuntime]:
    def _get_maintenance_runtime(
        session: AsyncSession = Depends(get_async_session),
    ) -> MaintenanceLiteWorkflowRuntime:
        return MaintenanceLiteWorkflowRuntime(session, provider=provider)

    return _get_maintenance_runtime
