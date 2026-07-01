"""Manual phased GigaChat smoke script.

Disabled by default. Run only with ENABLE_REAL_PROVIDER_SMOKE=1 and real
GigaChat credentials in the project-root `.env`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import truststore

from enterprise_ai_tool_gateway.llm.base import (
    LLMDecisionRequest,
    ProviderConfigurationError,
    ProviderErrorCategory,
    ProviderRuntimeError,
    is_real_provider_smoke_enabled,
)
from enterprise_ai_tool_gateway.llm.gigachat import (
    GigaChatProvider,
    GigaChatSettings,
    build_chat_completion_payload,
    extract_safe_response_summary,
    map_gigachat_status,
    parse_structured_decision_response,
    safe_response_excerpt,
)


@dataclass
class SmokeContext:
    env_file: Path
    settings: GigaChatSettings | None = None
    access_token: str | None = None
    successful_phases: list[str] = field(default_factory=list)


def _project_env_file() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def _enable_local_os_trust_store() -> None:
    # Helps local Windows setups use OS root certificates for GigaChat TLS.
    truststore.inject_into_ssl()


def _require_settings(context: SmokeContext) -> GigaChatSettings:
    if context.settings is None:
        raise ProviderConfigurationError("GigaChat settings were not loaded")
    return context.settings


def _require_access_token(context: SmokeContext) -> str:
    if context.access_token is None:
        raise ProviderConfigurationError("GigaChat access token was not acquired")
    return context.access_token


def _auth_headers(context: SmokeContext) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_require_access_token(context)}",
        "Content-Type": "application/json",
    }


def _raise_for_http_error(phase: str, response: httpx.Response) -> None:
    if response.status_code == 200:
        return
    category = map_gigachat_status(response.status_code)
    raise ProviderRuntimeError(
        category,
        f"{phase} failed: {category}",
        http_status_code=response.status_code,
        safe_response_excerpt=safe_response_excerpt(response.text),
    )


def _response_json(response: httpx.Response, phase: str) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderRuntimeError(
            ProviderErrorCategory.INVALID_RESPONSE,
            f"{phase} response was not valid JSON",
            http_status_code=response.status_code,
            safe_response_excerpt=safe_response_excerpt(response.text),
        ) from exc


def _format_result(result: dict[str, object]) -> str:
    parts = [f"{key}={value}" for key, value in result.items()]
    return "; ".join(parts)


async def _phase_settings_precheck(context: SmokeContext) -> dict[str, object]:
    settings = GigaChatSettings.from_env(env_file=context.env_file)
    settings.validate_for_real_call()
    context.settings = settings
    return {
        "env_file": context.env_file,
        "authorization_key": "present",
        "auth_url": settings.auth_url,
        "base_url": settings.base_url,
        "scope": settings.scope,
        "model": settings.model,
    }


async def _phase_token_acquisition(context: SmokeContext) -> dict[str, object]:
    settings = _require_settings(context)
    provider = GigaChatProvider(settings=settings)
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
        context.access_token = await provider.fetch_access_token(client)
    return {"token": "acquired"}


async def _phase_models_request(context: SmokeContext) -> dict[str, object]:
    settings = _require_settings(context)
    url = f"{settings.base_url.rstrip('/')}/models"
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
        response = await client.get(url, headers=_auth_headers(context))
    _raise_for_http_error("GET models", response)
    payload = _response_json(response, "GET models")
    models = payload.get("data") if isinstance(payload, dict) else None
    return {
        "http_status": response.status_code,
        "models_count": len(models) if isinstance(models, list) else "unknown",
    }


async def _phase_simple_chat(context: SmokeContext) -> dict[str, object]:
    settings = _require_settings(context)
    request = LLMDecisionRequest(
        request_id="manual-gigachat-simple-chat",
        user_request="Ответь одним коротким предложением: проверка связи.",
    )
    payload = build_chat_completion_payload(
        request,
        settings,
        include_response_format=False,
        include_functions=False,
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
        response = await client.post(
            f"{settings.base_url.rstrip('/')}/chat/completions",
            headers=_auth_headers(context),
            json=payload,
        )
    _raise_for_http_error("simple chat completion", response)
    summary = extract_safe_response_summary(_response_json(response, "simple chat completion"))
    return {"http_status": response.status_code, **summary}


async def _phase_structured_json(context: SmokeContext) -> dict[str, object]:
    settings = _require_settings(context)
    request = LLMDecisionRequest(
        request_id="manual-gigachat-structured-json",
        user_request="Нужен доступ к CRM для нового сотрудника.",
    )
    payload = build_chat_completion_payload(
        request,
        settings,
        include_response_format=True,
        include_functions=False,
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
        response = await client.post(
            f"{settings.base_url.rstrip('/')}/chat/completions",
            headers=_auth_headers(context),
            json=payload,
    )
    _raise_for_http_error("structured JSON completion", response)
    try:
        decision = parse_structured_decision_response(
            _response_json(response, "structured JSON completion")
        )
    except ProviderRuntimeError as exc:
        raise ProviderRuntimeError(
            exc.category,
            str(exc),
            http_status_code=response.status_code,
            safe_response_excerpt=safe_response_excerpt(response.text),
        ) from exc
    return {
        "http_status": response.status_code,
        "request_type": decision.request_type,
        "risk_level": decision.risk_level,
        "requires_approval": decision.requires_approval,
    }


async def _phase_function_calling(context: SmokeContext) -> dict[str, object]:
    settings = _require_settings(context)
    request = LLMDecisionRequest(
        request_id="manual-gigachat-function-calling",
        user_request="Сформируй черновик заявки на доступ к CRM.",
    )
    payload = build_chat_completion_payload(
        request,
        settings,
        include_response_format=False,
        include_functions=True,
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.timeout_seconds)) as client:
        response = await client.post(
            f"{settings.base_url.rstrip('/')}/chat/completions",
            headers=_auth_headers(context),
            json=payload,
        )
    _raise_for_http_error("function-calling completion", response)
    summary = extract_safe_response_summary(
        _response_json(response, "function-calling completion")
    )
    return {"http_status": response.status_code, **summary}


Phase = tuple[str, Callable[[SmokeContext], Awaitable[dict[str, object]]]]


async def _run(env_file: Path) -> int:
    _enable_local_os_trust_store()
    context = SmokeContext(env_file=env_file)
    phases: list[Phase] = [
        ("phase 1: credential/settings precheck", _phase_settings_precheck),
        ("phase 2: token acquisition", _phase_token_acquisition),
        ("phase 3: GET models", _phase_models_request),
        ("phase 4: simple chat completion", _phase_simple_chat),
        ("phase 5: structured JSON response", _phase_structured_json),
        ("phase 6: function-calling response", _phase_function_calling),
    ]

    for phase_name, phase in phases:
        print(phase_name)
        try:
            result = await phase(context)
        except ProviderConfigurationError as exc:
            print(f"FAILED: precondition={exc}")
            _print_success_summary(context)
            return 2
        except ProviderRuntimeError as exc:
            print(f"FAILED: category={exc.category}")
            if exc.http_status_code is not None:
                print(f"HTTP status: {exc.http_status_code}")
            if exc.safe_response_excerpt:
                print(f"response_excerpt: {exc.safe_response_excerpt}")
            _print_success_summary(context)
            return 3
        except httpx.TimeoutException:
            print(f"FAILED: category={ProviderErrorCategory.TIMEOUT}")
            _print_success_summary(context)
            return 3
        except httpx.HTTPError:
            print(f"FAILED: category={ProviderErrorCategory.UNAVAILABLE}")
            _print_success_summary(context)
            return 3
        except Exception as exc:
            print(f"FAILED: unexpected_error={type(exc).__name__}")
            _print_success_summary(context)
            return 4
        print(f"OK: {_format_result(result)}")
        context.successful_phases.append(phase_name)

    _print_success_summary(context)
    return 0


def _print_success_summary(context: SmokeContext) -> None:
    if not context.successful_phases:
        print("Successful phases: none")
        return
    print("Successful phases:")
    for phase_name in context.successful_phases:
        print(f"- {phase_name}")


def main() -> int:
    env_file = _project_env_file()
    if not is_real_provider_smoke_enabled(env_file=env_file):
        print(
            "GigaChat smoke skipped: "
            f"ENABLE_REAL_PROVIDER_SMOKE=1 is not set in {env_file}."
        )
        return 0
    return asyncio.run(_run(env_file))


if __name__ == "__main__":
    raise SystemExit(main())
