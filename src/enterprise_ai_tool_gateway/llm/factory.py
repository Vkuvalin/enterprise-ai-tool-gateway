"""Minimal provider selector for explicit local/manual use."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from enterprise_ai_tool_gateway.llm.base import LLMProviderPort, ProviderConfigurationError
from enterprise_ai_tool_gateway.llm.gigachat import GigaChatProvider, GigaChatProviderConfig
from enterprise_ai_tool_gateway.llm.mock import MockLLMProvider

_SUPPORTED_PROVIDER_NAMES = frozenset({"mock", "gigachat"})


def create_llm_provider_from_env(
    env: Mapping[str, str] | None = None,
    *,
    env_file: Path | str | None = None,
) -> LLMProviderPort:
    """Create the explicitly configured provider.

    The default is always the deterministic mock provider. There is no automatic
    fallback from a failed real provider to mock.
    """

    provider_name = (env.get("LLM_PROVIDER") if env is not None else os.environ.get("LLM_PROVIDER"))
    normalized = (provider_name or "mock").strip().lower()
    if normalized not in _SUPPORTED_PROVIDER_NAMES:
        raise ProviderConfigurationError(
            "Unsupported LLM provider.",
            reason_code="unsupported_llm_provider",
            provider_name=normalized or "unknown",
        )
    if normalized == "mock":
        return MockLLMProvider()
    return GigaChatProvider(config=GigaChatProviderConfig.from_env(env, env_file=env_file))
