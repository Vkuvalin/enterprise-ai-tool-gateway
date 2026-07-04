from __future__ import annotations

import pytest

from enterprise_ai_tool_gateway.llm import (
    LLMDecisionRequest,
    MockLLMProvider,
    ProviderConfigurationError,
    create_llm_provider_from_env,
)
from enterprise_ai_tool_gateway.llm.base import (
    is_real_provider_smoke_enabled,
    require_real_provider_smoke_enabled,
)
from enterprise_ai_tool_gateway.llm.gigachat import GigaChatProvider
from enterprise_ai_tool_gateway.llm.yandex import YandexGptSettings


@pytest.mark.asyncio
async def test_mock_provider_is_deterministic_for_access_request() -> None:
    provider = MockLLMProvider()
    request = LLMDecisionRequest(
        request_id="req-1",
        user_request="Нужен доступ к CRM.",
    )

    first = await provider.generate_structured_decision(request)
    second = await provider.generate_structured_decision(request)

    assert first == second
    assert first.request_type == "ACCESS_REQUEST"
    assert first.requires_approval is True
    assert first.proposed_tool_calls[0].name == "create_access_request_draft"


@pytest.mark.asyncio
async def test_mock_provider_classifies_russian_access_keyword() -> None:
    provider = MockLLMProvider()

    decision = await provider.generate_structured_decision(
        LLMDecisionRequest(
            request_id="req-russian",
            user_request="Нужен доступ к CRM для сотрудника emp-001 на 30 дней.",
        )
    )

    assert decision.request_type == "ACCESS_REQUEST"


def test_real_provider_smoke_requires_explicit_flag() -> None:
    assert is_real_provider_smoke_enabled({"ENABLE_REAL_PROVIDER_SMOKE": "0"}) is False
    assert is_real_provider_smoke_enabled({"ENABLE_REAL_PROVIDER_SMOKE": "1"}) is True

    with pytest.raises(ProviderConfigurationError) as exc_info:
        require_real_provider_smoke_enabled({"ENABLE_REAL_PROVIDER_SMOKE": "0"})

    assert exc_info.value.reason_code == "real_provider_smoke_not_enabled"


def test_factory_defaults_to_mock_provider() -> None:
    provider = create_llm_provider_from_env({})

    assert isinstance(provider, MockLLMProvider)


def test_factory_creates_gigachat_only_when_explicitly_configured() -> None:
    provider = create_llm_provider_from_env(
        {
            "LLM_PROVIDER": "gigachat",
            "GIGACHAT_AUTHORIZATION_KEY": "authorization-key",
        }
    )

    assert isinstance(provider, GigaChatProvider)


def test_factory_rejects_unsupported_provider() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        create_llm_provider_from_env({"LLM_PROVIDER": "unknown"})

    assert exc_info.value.reason_code == "unsupported_llm_provider"


def test_factory_does_not_fallback_to_mock_when_gigachat_config_is_missing() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        create_llm_provider_from_env({"LLM_PROVIDER": "gigachat"})

    assert exc_info.value.reason_code == "gigachat_config_missing_or_invalid"


def test_yandex_rejects_placeholder_credentials() -> None:
    settings = YandexGptSettings(
        api_key="change_me",
        folder_id="change_me",
        model="yandexgpt",
    )

    with pytest.raises(ProviderConfigurationError):
        settings.validate_for_real_call()
