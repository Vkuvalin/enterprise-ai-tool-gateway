from __future__ import annotations

import pytest

from enterprise_ai_tool_gateway.llm import (
    LLMDecisionRequest,
    MockLLMProvider,
    ProviderConfigurationError,
)
from enterprise_ai_tool_gateway.llm.base import (
    is_real_provider_smoke_enabled,
    require_real_provider_smoke_enabled,
)
from enterprise_ai_tool_gateway.llm.gigachat import (
    GigaChatSettings,
    build_chat_completion_payload,
    build_token_request,
    parse_structured_decision_response,
    safe_response_excerpt,
)
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


def test_real_provider_smoke_requires_explicit_flag() -> None:
    assert is_real_provider_smoke_enabled({"ENABLE_REAL_PROVIDER_SMOKE": "0"}) is False
    assert is_real_provider_smoke_enabled({"ENABLE_REAL_PROVIDER_SMOKE": "1"}) is True

    with pytest.raises(ProviderConfigurationError):
        require_real_provider_smoke_enabled({"ENABLE_REAL_PROVIDER_SMOKE": "0"})


def test_real_provider_smoke_flag_can_load_explicit_env_file(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "ENABLE_REAL_PROVIDER_SMOKE=1",
                "GIGACHAT_AUTHORIZATION_KEY=env-key",
                "GIGACHAT_SCOPE=GIGACHAT_API_PERS",
            ]
        ),
        encoding="utf-8",
    )
    other_cwd = tmp_path / "other"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    settings = GigaChatSettings.from_env(env_file=env_file)

    assert is_real_provider_smoke_enabled(env_file=env_file) is True
    assert settings.authorization_key == "env-key"
    assert settings.scope == "GIGACHAT_API_PERS"


def test_gigachat_rejects_placeholder_credentials() -> None:
    settings = GigaChatSettings(
        authorization_key="change_me",
        model="GigaChat-2-Pro",
        base_url="https://gigachat.devices.sberbank.ru/api/v1",
        auth_url="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        scope="GIGACHAT_API_PERS",
    )

    with pytest.raises(ProviderConfigurationError):
        settings.validate_for_real_call()


def test_gigachat_builds_token_and_structured_payload_shape() -> None:
    settings = GigaChatSettings(
        authorization_key="not-a-real-secret",
        model="GigaChat-2-Pro",
        base_url="https://gigachat.devices.sberbank.ru/api/v1",
        auth_url="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        scope="GIGACHAT_API_PERS",
    )
    token_request = build_token_request(settings)
    payload = build_chat_completion_payload(
        LLMDecisionRequest(user_request="Need access to CRM."),
        settings,
    )

    assert token_request["method"] == "POST"
    assert token_request["data"] == {"scope": "GIGACHAT_API_PERS"}
    assert token_request["headers"]["Authorization"].startswith("Basic ")
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["strict"] is True
    assert payload["function_call"] == "auto"
    assert payload["functions"][0]["name"] == "create_access_request_draft"


def test_gigachat_payload_modes_are_separable() -> None:
    settings = GigaChatSettings(authorization_key="key")
    request = LLMDecisionRequest(user_request="Need access to CRM.")

    simple_payload = build_chat_completion_payload(
        request,
        settings,
        include_response_format=False,
        include_functions=False,
    )
    structured_payload = build_chat_completion_payload(
        request,
        settings,
        include_response_format=True,
        include_functions=False,
    )
    functions_payload = build_chat_completion_payload(
        request,
        settings,
        include_response_format=False,
        include_functions=True,
    )

    assert "response_format" not in simple_payload
    assert "functions" not in simple_payload
    assert "response_format" in structured_payload
    assert "functions" not in structured_payload
    assert "response_format" not in functions_payload
    assert functions_payload["function_call"] == "auto"


def test_gigachat_authorization_key_env_prefers_clear_name() -> None:
    settings = GigaChatSettings.from_env(
        {
            "GIGACHAT_AUTHORIZATION_KEY": "new-key",
            "GIGACHAT_API_KEY": "legacy-key",
        }
    )
    legacy_settings = GigaChatSettings.from_env({"GIGACHAT_API_KEY": "legacy-key"})

    assert settings.authorization_key == "new-key"
    assert legacy_settings.authorization_key == "legacy-key"
    assert settings.base_url == "https://gigachat.devices.sberbank.ru/api/v1"


def test_safe_response_excerpt_redacts_secret_markers() -> None:
    assert safe_response_excerpt("plain provider error") == "plain provider error"
    assert safe_response_excerpt("access_token=secret") == (
        "[redacted: response contained sensitive markers]"
    )


def test_gigachat_parses_valid_structured_response() -> None:
    raw_response = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"request_type":"UNKNOWN","domain_template":"UNKNOWN",'
                        '"confidence":0.7,"risk_level":"LOW","requires_approval":false,'
                        '"missing_fields":[],"proposed_tool_calls":[],'
                        '"user_facing_summary":"Safe summary","reason_codes":["SMOKE"]}'
                    )
                }
            }
        ]
    }

    parsed = parse_structured_decision_response(raw_response)

    assert parsed.request_type == "UNKNOWN"
    assert parsed.reason_codes == ["SMOKE"]


def test_yandex_rejects_placeholder_credentials() -> None:
    settings = YandexGptSettings(
        api_key="change_me",
        folder_id="change_me",
        model="yandexgpt",
    )

    with pytest.raises(ProviderConfigurationError):
        settings.validate_for_real_call()
