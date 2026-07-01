"""GigaChat technical spike adapter skeleton.

This module intentionally stops at the provider boundary. It verifies request
shape, credential gating, safe error mapping, and structured-output parsing
without implementing production workflow orchestration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast
from uuid import uuid4

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from enterprise_ai_tool_gateway.llm.base import (
    LLMDecisionRequest,
    LLMDecisionResponse,
    PROJECT_ENV_FILE,
    ProviderConfigurationError,
    ProviderErrorCategory,
    ProviderRuntimeError,
    is_placeholder_secret,
    require_real_provider_smoke_enabled,
)

DEFAULT_GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
DEFAULT_GIGACHAT_BASE_URL = "https://gigachat.devices.sberbank.ru/api/v1"
DEFAULT_GIGACHAT_MODEL = "GigaChat-2-Pro"
DEFAULT_GIGACHAT_SCOPE = "GIGACHAT_API_PERS"


class _GigaChatEnvSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    gigachat_authorization_key: str | None = None
    gigachat_api_key: str | None = None
    gigachat_model: str = DEFAULT_GIGACHAT_MODEL
    gigachat_base_url: str = DEFAULT_GIGACHAT_BASE_URL
    gigachat_auth_url: str = DEFAULT_GIGACHAT_AUTH_URL
    gigachat_scope: str = DEFAULT_GIGACHAT_SCOPE
    llm_timeout_seconds: float = 60.0


GIGACHAT_TOOL_FUNCTIONS: list[dict[str, Any]] = [
    {
        "name": "create_access_request_draft",
        "description": "Create a draft access request for backend validation.",
        "parameters": {
            "type": "object",
            "properties": {
                "request_id": {
                    "type": "string",
                    "description": "Backend request identifier.",
                }
            },
            "required": ["request_id"],
        },
        "return_parameters": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string"},
                "status": {"type": "string", "enum": ["draft"]},
            },
            "required": ["draft_id", "status"],
        },
    }
]


SYSTEM_PROMPT = (
    "Classify the enterprise request and return only a structured decision. "
    "Tool calls are proposals only; backend validation and approval are required."
)


@dataclass(frozen=True)
class GigaChatSettings:
    """Environment-backed settings required for a real GigaChat call."""

    authorization_key: str | None
    model: str = DEFAULT_GIGACHAT_MODEL
    base_url: str = DEFAULT_GIGACHAT_BASE_URL
    auth_url: str = DEFAULT_GIGACHAT_AUTH_URL
    scope: str = DEFAULT_GIGACHAT_SCOPE
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        env_file: Path | str | None = None,
    ) -> "GigaChatSettings":
        if env is None:
            settings_cls = cast(Any, _GigaChatEnvSettings)
            loaded = settings_cls(_env_file=env_file or PROJECT_ENV_FILE)
            return cls(
                authorization_key=loaded.gigachat_authorization_key or loaded.gigachat_api_key,
                model=loaded.gigachat_model,
                base_url=loaded.gigachat_base_url,
                auth_url=loaded.gigachat_auth_url,
                scope=loaded.gigachat_scope,
                timeout_seconds=loaded.llm_timeout_seconds,
            )
        source = env
        return cls(
            authorization_key=source.get("GIGACHAT_AUTHORIZATION_KEY")
            or source.get("GIGACHAT_API_KEY"),
            model=source.get("GIGACHAT_MODEL", DEFAULT_GIGACHAT_MODEL),
            base_url=source.get("GIGACHAT_BASE_URL", DEFAULT_GIGACHAT_BASE_URL),
            auth_url=source.get("GIGACHAT_AUTH_URL", DEFAULT_GIGACHAT_AUTH_URL),
            scope=source.get("GIGACHAT_SCOPE", DEFAULT_GIGACHAT_SCOPE),
            timeout_seconds=float(source.get("LLM_TIMEOUT_SECONDS", "60")),
        )

    def validate_for_real_call(self) -> None:
        missing = []
        if is_placeholder_secret(self.authorization_key):
            missing.append("GIGACHAT_AUTHORIZATION_KEY or legacy GIGACHAT_API_KEY")
        if is_placeholder_secret(self.model):
            missing.append("GIGACHAT_MODEL")
        if is_placeholder_secret(self.base_url):
            missing.append("GIGACHAT_BASE_URL")
        if is_placeholder_secret(self.auth_url):
            missing.append("GIGACHAT_AUTH_URL")
        if is_placeholder_secret(self.scope):
            missing.append("GIGACHAT_SCOPE")

        if missing:
            joined = ", ".join(missing)
            raise ProviderConfigurationError(
                f"GigaChat real-provider mode requires non-placeholder values for: {joined}"
            )


def build_token_request(settings: GigaChatSettings) -> dict[str, Any]:
    """Build the documented OAuth request without sending it."""

    settings.validate_for_real_call()
    return {
        "method": "POST",
        "url": settings.auth_url,
        "headers": {
            "Accept": "application/json",
            "Authorization": f"Basic {settings.authorization_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "RqUID": str(uuid4()),
        },
        "data": {"scope": settings.scope},
    }


def structured_decision_response_format() -> dict[str, Any]:
    """Return the strict JSON-schema response format used for decision output."""

    return {
        "type": "json_schema",
        "schema": LLMDecisionResponse.model_json_schema(),
        "strict": True,
    }


def build_chat_completion_payload(
    request: LLMDecisionRequest,
    settings: GigaChatSettings,
    *,
    include_response_format: bool = True,
    include_functions: bool = True,
) -> dict[str, Any]:
    """Build the GigaChat chat completion payload for the spike."""

    payload: dict[str, Any] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": request.user_request},
        ],
    }
    if include_response_format:
        payload["response_format"] = structured_decision_response_format()
    if include_functions:
        payload["functions"] = GIGACHAT_TOOL_FUNCTIONS
        payload["function_call"] = "auto"
    return payload


def map_gigachat_status(status_code: int) -> ProviderErrorCategory:
    """Map provider HTTP status codes to safe project categories."""

    if status_code in {401, 403}:
        return ProviderErrorCategory.AUTH_ERROR
    if status_code == 429:
        return ProviderErrorCategory.RATE_LIMIT
    if status_code in {400, 404, 422}:
        return ProviderErrorCategory.INVALID_RESPONSE
    return ProviderErrorCategory.UNAVAILABLE


def safe_response_excerpt(text: str, *, limit: int = 300) -> str:
    """Return a short provider response excerpt without secret-bearing markers."""

    compact = " ".join(text.split())
    lowered = compact.lower()
    if any(marker in lowered for marker in ("authorization", "access_token", "bearer ", "basic ")):
        return "[redacted: response contained sensitive markers]"
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def extract_safe_response_summary(raw_response: Mapping[str, Any]) -> dict[str, Any]:
    """Return metadata safe to print from a provider response."""

    choices = raw_response.get("choices")
    first_choice = choices[0] if isinstance(choices, list) and choices else {}
    message = first_choice.get("message") if isinstance(first_choice, dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    function_call = message.get("function_call") if isinstance(message, dict) else None
    return {
        "model": raw_response.get("model"),
        "choices_count": len(choices) if isinstance(choices, list) else 0,
        "finish_reason": first_choice.get("finish_reason") if isinstance(first_choice, dict) else None,
        "content_chars": len(content) if isinstance(content, str) else 0,
        "has_function_call": function_call is not None,
    }


class GigaChatProvider:
    """Narrow async HTTP provider skeleton for manual smoke use."""

    def __init__(
        self,
        settings: GigaChatSettings | None = None,
        *,
        env_file: Path | str | None = None,
    ) -> None:
        self.env_file = env_file
        self.settings = settings or GigaChatSettings.from_env(env_file=env_file)

    async def fetch_access_token(self, client: httpx.AsyncClient) -> str:
        token_request = build_token_request(self.settings)
        response = await client.post(
            token_request["url"],
            headers=token_request["headers"],
            data=token_request["data"],
        )
        if response.status_code != 200:
            category = map_gigachat_status(response.status_code)
            raise ProviderRuntimeError(
                category,
                f"GigaChat token request failed: {category}",
                http_status_code=response.status_code,
                safe_response_excerpt=safe_response_excerpt(response.text),
            )
        payload = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise ProviderRuntimeError(
                ProviderErrorCategory.INVALID_RESPONSE,
                "GigaChat token response did not contain access_token",
            )
        return token

    async def generate_structured_decision(
        self, request: LLMDecisionRequest
    ) -> LLMDecisionResponse:
        require_real_provider_smoke_enabled(env_file=self.env_file)
        self.settings.validate_for_real_call()
        timeout = httpx.Timeout(self.settings.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            token = await self.fetch_access_token(client)
            payload = build_chat_completion_payload(request, self.settings)
            response = await client.post(
                f"{self.settings.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
            if response.status_code != 200:
                category = map_gigachat_status(response.status_code)
                raise ProviderRuntimeError(
                    category,
                    f"GigaChat completion failed: {category}",
                    http_status_code=response.status_code,
                    safe_response_excerpt=safe_response_excerpt(response.text),
                )
            return parse_structured_decision_response(response.json())


def parse_structured_decision_response(raw_response: Mapping[str, Any]) -> LLMDecisionResponse:
    """Parse the normalized decision from a GigaChat v1 chat completion response."""

    try:
        choices = raw_response["choices"]
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderRuntimeError(
            ProviderErrorCategory.INVALID_RESPONSE,
            "GigaChat response did not match expected chat completion shape",
        ) from exc

    if not isinstance(content, str) or not content.strip():
        raise ProviderRuntimeError(
            ProviderErrorCategory.INVALID_RESPONSE,
            "GigaChat response content was empty or not text",
        )

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProviderRuntimeError(
            ProviderErrorCategory.INVALID_RESPONSE,
            "GigaChat structured response content was not valid JSON",
        ) from exc
    return LLMDecisionResponse.model_validate(parsed)
