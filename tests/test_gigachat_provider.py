from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import httpx
import pytest

from enterprise_ai_tool_gateway.llm import LLMDecisionRequest
from enterprise_ai_tool_gateway.llm.base import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderSchemaValidationError,
    ProviderTransportError,
)
from enterprise_ai_tool_gateway.llm.gigachat import (
    DEFAULT_GIGACHAT_AUTH_URL,
    DEFAULT_GIGACHAT_BASE_URL,
    GigaChatProvider,
    GigaChatProviderConfig,
    MAX_GIGACHAT_MAX_RETRIES,
    MAX_GIGACHAT_TIMEOUT_SECONDS,
    build_chat_completion_payload,
    build_token_request,
    parse_structured_decision_response,
    safe_response_excerpt,
)


def _load_manual_gigachat_smoke() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "manual_gigachat_smoke.py"
    spec = importlib.util.spec_from_file_location("manual_gigachat_smoke_under_test", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("manual_gigachat_smoke.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


manual_gigachat_smoke = cast(Any, _load_manual_gigachat_smoke())


async def _no_sleep(_seconds: float) -> None:
    return None


def _decision_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "request_type": "UNKNOWN",
        "domain_template": "UNKNOWN",
        "confidence": 0.7,
        "risk_level": "LOW",
        "requires_approval": False,
        "missing_fields": [],
        "proposed_tool_calls": [],
        "user_facing_summary": "Safe summary.",
        "reason_codes": ["TEST"],
    }
    payload.update(overrides)
    return json.dumps(payload)


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _config(*, max_retries: int = 0) -> GigaChatProviderConfig:
    return GigaChatProviderConfig(
        authorization_key="authorization-key",
        model="GigaChat-2-Pro",
        max_retries=max_retries,
        timeout_seconds=5,
    )


def _provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 0,
) -> GigaChatProvider:
    return GigaChatProvider(
        config=_config(max_retries=max_retries),
        env_file=_enabled_env_file(),
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )


def _enabled_env_file() -> str:
    return "tests/fixtures/nonexistent-real-provider-smoke.env"


def test_config_from_explicit_values_builds_safe_request_shapes() -> None:
    config = _config(max_retries=1)

    token_request = build_token_request(config)
    payload = build_chat_completion_payload(
        LLMDecisionRequest(user_request="Need access to CRM."),
        config,
    )

    assert token_request["method"] == "POST"
    assert token_request["data"] == {"scope": "GIGACHAT_API_PERS"}
    assert token_request["headers"]["Authorization"].startswith("Basic ")
    assert "functions" not in payload
    assert "function_call" not in payload
    assert "response_format" not in payload
    assert payload["model"] == "GigaChat-2-Pro"


def test_config_from_env_uses_supported_gigachat_names() -> None:
    config = GigaChatProviderConfig.from_env(
        {
            "GIGACHAT_AUTHORIZATION_KEY": "authorization-key",
            "GIGACHAT_MODEL": "GigaChat-2-Max",
            "GIGACHAT_TIMEOUT_SECONDS": "12.5",
            "GIGACHAT_MAX_RETRIES": "2",
            "GIGACHAT_VERIFY_SSL": "false",
        }
    )

    assert config.authorization_key == "authorization-key"
    assert config.model == "GigaChat-2-Max"
    assert config.timeout_seconds == 12.5
    assert config.max_retries == 2
    assert config.verify_ssl is False


def test_config_from_env_accepts_bounded_timeout_and_retries() -> None:
    config = GigaChatProviderConfig.from_env(
        {
            "GIGACHAT_AUTHORIZATION_KEY": "authorization-key",
            "GIGACHAT_TIMEOUT_SECONDS": str(MAX_GIGACHAT_TIMEOUT_SECONDS),
            "GIGACHAT_MAX_RETRIES": str(MAX_GIGACHAT_MAX_RETRIES),
        }
    )

    assert config.timeout_seconds == MAX_GIGACHAT_TIMEOUT_SECONDS
    assert config.max_retries == MAX_GIGACHAT_MAX_RETRIES


def test_missing_authorization_key_fails_configuration() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        GigaChatProviderConfig.from_env({})

    assert exc_info.value.reason_code == "gigachat_config_missing_or_invalid"
    assert "authorization-key" not in str(exc_info.value).lower()


@pytest.mark.parametrize(
    ("env_name", "env"),
    [
        (
            "GIGACHAT_BASE_URL",
            {
                "GIGACHAT_AUTHORIZATION_KEY": "authorization-key",
                "GIGACHAT_BASE_URL": "change_me",
            },
        ),
        (
            "GIGACHAT_AUTH_URL",
            {
                "GIGACHAT_AUTHORIZATION_KEY": "authorization-key",
                "GIGACHAT_AUTH_URL": "change_me",
            },
        ),
    ],
)
def test_invalid_gigachat_urls_fail_configuration_with_safe_env_name(
    env_name: str,
    env: dict[str, str],
) -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        GigaChatProviderConfig.from_env(env)

    assert env_name in str(exc_info.value)
    assert "authorization-key" not in str(exc_info.value)


def test_invalid_base_url_reports_base_url_not_auth_url() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        GigaChatProviderConfig.from_env(
            {
                "GIGACHAT_AUTHORIZATION_KEY": "authorization-key",
                "GIGACHAT_BASE_URL": "change_me",
                "GIGACHAT_AUTH_URL": DEFAULT_GIGACHAT_AUTH_URL,
            }
        )

    error_text = str(exc_info.value)
    assert "GIGACHAT_BASE_URL" in error_text
    assert "GIGACHAT_AUTH_URL" not in error_text
    assert "authorization-key" not in error_text
    assert "authorization-key" not in str(exc_info.value.safe_context())


def test_valid_base_url_with_invalid_auth_url_reports_auth_url() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        GigaChatProviderConfig.from_env(
            {
                "GIGACHAT_AUTHORIZATION_KEY": "authorization-key",
                "GIGACHAT_BASE_URL": DEFAULT_GIGACHAT_BASE_URL,
                "GIGACHAT_AUTH_URL": "change_me",
            }
        )

    error_text = str(exc_info.value)
    assert "GIGACHAT_AUTH_URL" in error_text
    assert "GIGACHAT_BASE_URL" not in error_text
    assert "authorization-key" not in error_text
    assert "authorization-key" not in str(exc_info.value.safe_context())


def test_legacy_api_key_env_is_ignored_and_not_supported() -> None:
    legacy_key_name = "GIGACHAT_" + "API_KEY"

    with pytest.raises(ProviderConfigurationError) as exc_info:
        GigaChatProviderConfig.from_env({legacy_key_name: "legacy-key"})

    assert exc_info.value.reason_code == "gigachat_config_missing_or_invalid"


@pytest.mark.parametrize(
    "env",
    [
        {"GIGACHAT_AUTHORIZATION_KEY": "authorization-key", "GIGACHAT_TIMEOUT_SECONDS": "bad"},
        {"GIGACHAT_AUTHORIZATION_KEY": "authorization-key", "GIGACHAT_MAX_RETRIES": "-1"},
    ],
)
def test_invalid_timeout_and_retries_fail_safely(env: dict[str, str]) -> None:
    with pytest.raises(ProviderConfigurationError):
        GigaChatProviderConfig.from_env(env)


@pytest.mark.parametrize(
    ("env_name", "env"),
    [
        (
            "GIGACHAT_TIMEOUT_SECONDS",
            {
                "GIGACHAT_AUTHORIZATION_KEY": "authorization-key",
                "GIGACHAT_TIMEOUT_SECONDS": str(MAX_GIGACHAT_TIMEOUT_SECONDS + 1),
            },
        ),
        (
            "GIGACHAT_MAX_RETRIES",
            {
                "GIGACHAT_AUTHORIZATION_KEY": "authorization-key",
                "GIGACHAT_MAX_RETRIES": str(MAX_GIGACHAT_MAX_RETRIES + 1),
            },
        ),
    ],
)
def test_excessive_timeout_and_retries_fail_safely(
    env_name: str,
    env: dict[str, str],
) -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        GigaChatProviderConfig.from_env(env)

    assert env_name in str(exc_info.value)
    assert "authorization-key" not in str(exc_info.value)
    assert "authorization-key" not in str(exc_info.value.safe_context())


def test_env_example_uses_gigachat_transport_names() -> None:
    env_example = Path(__file__).resolve().parents[1] / ".env.example"
    content = env_example.read_text(encoding="utf-8")
    legacy_key_name = "GIGACHAT_" + "API_KEY"

    assert legacy_key_name not in content
    assert "GIGACHAT_TIMEOUT_SECONDS=30" in content
    assert "GIGACHAT_MAX_RETRIES=1" in content
    assert "GIGACHAT_VERIFY_SSL=true" in content
    assert "LLM_TIMEOUT_SECONDS" not in content
    assert "LLM_MAX_RETRIES" not in content


def test_safe_response_excerpt_redacts_secret_markers() -> None:
    assert safe_response_excerpt("plain provider error") == "plain provider error"
    assert safe_response_excerpt("access_token=secret") == (
        "[redacted: response contained sensitive markers]"
    )
    assert safe_response_excerpt("Authorization: Basic secret") == (
        "[redacted: response contained sensitive markers]"
    )


@pytest.mark.asyncio
async def test_auth_success_with_fake_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/oauth")
        return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})

    provider = _provider(handler)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        token = await provider.fetch_access_token(client)

    assert token == "token"


@pytest.mark.asyncio
async def test_token_is_cached_in_provider_instance(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ENABLE_REAL_PROVIDER_SMOKE=1", encoding="utf-8")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/oauth"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return _chat_response(_decision_json())

    provider = GigaChatProvider(
        config=_config(),
        env_file=env_file,
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )

    await provider.generate_structured_decision(LLMDecisionRequest(user_request="one"))
    await provider.generate_structured_decision(LLMDecisionRequest(user_request="two"))

    assert calls.count("/api/v2/oauth") == 1


@pytest.mark.asyncio
async def test_expired_token_refreshes(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ENABLE_REAL_PROVIDER_SMOKE=1", encoding="utf-8")
    auth_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal auth_count
        if request.url.path.endswith("/oauth"):
            auth_count += 1
            return httpx.Response(200, json={"access_token": f"token-{auth_count}", "expires_in": 1})
        return _chat_response(_decision_json())

    provider = GigaChatProvider(
        config=_config(),
        env_file=env_file,
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )

    await provider.generate_structured_decision(LLMDecisionRequest(user_request="one"))
    await provider.generate_structured_decision(LLMDecisionRequest(user_request="two"))

    assert auth_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_auth_401_403_maps_to_authentication_error_without_retry(status_code: int) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, text="auth failed")

    provider = _provider(handler, max_retries=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderAuthenticationError):
            await provider.fetch_access_token(client)

    assert calls == 1


@pytest.mark.asyncio
async def test_malformed_auth_response_maps_to_response_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"missing": "token"})

    provider = _provider(handler)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderResponseError) as exc_info:
            await provider.fetch_access_token(client)

    assert exc_info.value.reason_code == "gigachat_auth_response_malformed"


@pytest.mark.asyncio
async def test_timeout_maps_to_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=request)

    provider = _provider(handler)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderTransportError) as exc_info:
            await provider.fetch_access_token(client)

    assert exc_info.value.reason_code == "gigachat_timeout"


@pytest.mark.asyncio
async def test_http_429_retries_then_maps_to_rate_limit() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, text="rate limit")

    provider = _provider(handler, max_retries=1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderRateLimitError):
            await provider.fetch_access_token(client)

    assert calls == 2


@pytest.mark.asyncio
async def test_http_400_does_not_retry() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, text="bad request")

    provider = _provider(handler, max_retries=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderResponseError):
            await provider.fetch_access_token(client)

    assert calls == 1


@pytest.mark.asyncio
async def test_http_5xx_retries_with_bound() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, text="server error")

    provider = _provider(handler, max_retries=1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderTransportError) as exc_info:
            await provider.fetch_access_token(client)

    assert calls == 2
    assert exc_info.value.reason_code == "gigachat_server_error"


@pytest.mark.asyncio
async def test_metadata_records_retry_count_and_duration(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ENABLE_REAL_PROVIDER_SMOKE=1", encoding="utf-8")
    chat_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        if request.url.path.endswith("/oauth"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        chat_calls += 1
        if chat_calls == 1:
            return httpx.Response(500, text="transient")
        return _chat_response(_decision_json())

    provider = GigaChatProvider(
        config=_config(max_retries=1),
        env_file=env_file,
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )

    await provider.generate_structured_decision(LLMDecisionRequest(user_request="Need access."))

    assert provider.last_metadata is not None
    assert provider.last_metadata.retry_count == 1
    assert provider.last_metadata.duration_ms >= 0
    assert provider.last_metadata.structured_output_valid is True


def test_parse_structured_decision_response_rejects_malformed_chat_shape() -> None:
    with pytest.raises(ProviderResponseError):
        parse_structured_decision_response({"choices": []})


def test_parse_structured_decision_response_rejects_schema_invalid_content() -> None:
    raw_response = {"choices": [{"message": {"content": '{"request_type":"UNKNOWN"}'}}]}

    with pytest.raises(ProviderSchemaValidationError):
        parse_structured_decision_response(raw_response)


def test_parse_structured_decision_response_schema_error_has_gigachat_context() -> None:
    raw_response = {"choices": [{"message": {"content": '{"request_type":"UNKNOWN"}'}}]}

    with pytest.raises(ProviderSchemaValidationError) as exc_info:
        parse_structured_decision_response(raw_response, model_name="GigaChat-2-Max")

    assert exc_info.value.reason_code == "llm_decision_schema_invalid"
    assert exc_info.value.safe_context()["provider_name"] == "gigachat"
    assert exc_info.value.safe_context()["model_name"] == "GigaChat-2-Max"


def test_parse_structured_decision_response_accepts_text_wrapped_json() -> None:
    raw_response = {
        "choices": [
            {
                "message": {
                    "content": f"model explanation before {_decision_json()} after",
                }
            }
        ]
    }

    parsed = parse_structured_decision_response(raw_response)

    assert parsed.request_type == "UNKNOWN"
    assert parsed.model_dump(mode="json")["domain_template"] == "UNKNOWN"


def test_default_base_url_is_stable_for_manual_provider() -> None:
    assert _config().base_url == DEFAULT_GIGACHAT_BASE_URL


@pytest.mark.asyncio
async def test_manual_gigachat_smoke_without_live_skips_even_when_env_flag_is_set(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ENABLE_REAL_PROVIDER_SMOKE=1\n", encoding="utf-8")

    def fail_from_env(*_args: object, **_kwargs: object) -> GigaChatProviderConfig:
        raise AssertionError("live provider config should not be loaded without --live")

    monkeypatch.setattr(manual_gigachat_smoke.GigaChatProviderConfig, "from_env", fail_from_env)

    status = await manual_gigachat_smoke._run(
        argparse.Namespace(env_file=str(env_file), matrix="lite", live=False)
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "SKIPPED: live GigaChat smoke не запускался" in output


@pytest.mark.asyncio
async def test_manual_gigachat_smoke_with_live_but_without_env_flag_skips(
    tmp_path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    def fail_from_env(*_args: object, **_kwargs: object) -> GigaChatProviderConfig:
        raise AssertionError("live provider config should not be loaded without env flag")

    monkeypatch.setattr(manual_gigachat_smoke.GigaChatProviderConfig, "from_env", fail_from_env)

    status = await manual_gigachat_smoke._run(
        argparse.Namespace(env_file=str(env_file), matrix="lite", live=True)
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "SKIPPED: live GigaChat smoke не запускался" in output
    assert "ENABLE_REAL_PROVIDER_SMOKE=1" in output
