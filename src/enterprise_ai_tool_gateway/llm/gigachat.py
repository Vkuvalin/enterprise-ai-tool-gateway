"""Stage 6 GigaChat provider boundary.

The provider is optional/manual. It owns provider-specific auth, transport,
safe error mapping, and response-shape parsing, but it does not decide which
tools execute.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from enterprise_ai_tool_gateway.llm.base import (
    LLMDecisionRequest,
    LLMDecisionResponse,
    PROJECT_ENV_FILE,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderErrorCategory,
    ProviderModelUnavailableError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderRuntimeError,
    ProviderSchemaValidationError,
    ProviderTransportError,
    is_placeholder_secret,
    require_real_provider_smoke_enabled,
)
from enterprise_ai_tool_gateway.llm.structured_output import parse_llm_decision_payload

DEFAULT_GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
DEFAULT_GIGACHAT_BASE_URL = "https://gigachat.devices.sberbank.ru/api/v1"
DEFAULT_GIGACHAT_MODEL = "GigaChat-2-Pro"
DEFAULT_GIGACHAT_SCOPE = "GIGACHAT_API_PERS"
DEFAULT_GIGACHAT_TIMEOUT_SECONDS = 30.0
DEFAULT_GIGACHAT_MAX_RETRIES = 1
MAX_GIGACHAT_TIMEOUT_SECONDS = 120.0
MAX_GIGACHAT_MAX_RETRIES = 3
GIGACHAT_PROVIDER_NAME = "gigachat"
_TOKEN_REFRESH_SKEW_SECONDS = 60.0


class _GigaChatEnvSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    gigachat_authorization_key: str | None = None
    gigachat_model: str = DEFAULT_GIGACHAT_MODEL
    gigachat_base_url: str = DEFAULT_GIGACHAT_BASE_URL
    gigachat_auth_url: str = DEFAULT_GIGACHAT_AUTH_URL
    gigachat_scope: str = DEFAULT_GIGACHAT_SCOPE
    gigachat_timeout_seconds: float = DEFAULT_GIGACHAT_TIMEOUT_SECONDS
    gigachat_max_retries: int = DEFAULT_GIGACHAT_MAX_RETRIES
    gigachat_verify_ssl: bool = True


@dataclass(frozen=True)
class GigaChatProviderConfig:
    """Explicit settings required for optional real GigaChat calls."""

    authorization_key: str | None
    auth_url: str = DEFAULT_GIGACHAT_AUTH_URL
    base_url: str = DEFAULT_GIGACHAT_BASE_URL
    scope: str = DEFAULT_GIGACHAT_SCOPE
    model: str = DEFAULT_GIGACHAT_MODEL
    timeout_seconds: float = DEFAULT_GIGACHAT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_GIGACHAT_MAX_RETRIES
    verify_ssl: bool = True
    structured_output_enabled: bool = True
    debug_capture_redacted_raw: bool = False

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        env_file: Path | str | None = None,
    ) -> GigaChatProviderConfig:
        """Load supported GigaChat env vars only.

        Older API-key aliases are intentionally ignored and unsupported.
        """

        if env is None:
            try:
                settings_cls = cast(Any, _GigaChatEnvSettings)
                loaded = settings_cls(_env_file=env_file or PROJECT_ENV_FILE)
            except ValidationError as exc:
                raise ProviderConfigurationError(
                    "GigaChat environment configuration was invalid.",
                    reason_code="gigachat_env_invalid",
                    provider_name=GIGACHAT_PROVIDER_NAME,
                ) from exc
            config = cls(
                authorization_key=loaded.gigachat_authorization_key,
                model=loaded.gigachat_model,
                base_url=loaded.gigachat_base_url,
                auth_url=loaded.gigachat_auth_url,
                scope=loaded.gigachat_scope,
                timeout_seconds=loaded.gigachat_timeout_seconds,
                max_retries=loaded.gigachat_max_retries,
                verify_ssl=loaded.gigachat_verify_ssl,
            )
            config.validate_for_real_call()
            return config

        config = cls(
            authorization_key=env.get("GIGACHAT_AUTHORIZATION_KEY"),
            model=env.get("GIGACHAT_MODEL", DEFAULT_GIGACHAT_MODEL),
            base_url=env.get("GIGACHAT_BASE_URL", DEFAULT_GIGACHAT_BASE_URL),
            auth_url=env.get("GIGACHAT_AUTH_URL", DEFAULT_GIGACHAT_AUTH_URL),
            scope=env.get("GIGACHAT_SCOPE", DEFAULT_GIGACHAT_SCOPE),
            timeout_seconds=_parse_positive_float(
                env.get("GIGACHAT_TIMEOUT_SECONDS"),
                DEFAULT_GIGACHAT_TIMEOUT_SECONDS,
                "GIGACHAT_TIMEOUT_SECONDS",
            ),
            max_retries=_parse_non_negative_int(
                env.get("GIGACHAT_MAX_RETRIES"),
                DEFAULT_GIGACHAT_MAX_RETRIES,
                "GIGACHAT_MAX_RETRIES",
            ),
            verify_ssl=_parse_bool(env.get("GIGACHAT_VERIFY_SSL"), True, "GIGACHAT_VERIFY_SSL"),
        )
        config.validate_for_real_call()
        return config

    def validate_for_real_call(self) -> None:
        missing = []
        if is_placeholder_secret(self.authorization_key):
            missing.append("GIGACHAT_AUTHORIZATION_KEY")
        if is_placeholder_secret(self.model):
            missing.append("GIGACHAT_MODEL")
        if is_placeholder_secret(self.base_url):
            missing.append("GIGACHAT_BASE_URL")
        if is_placeholder_secret(self.auth_url):
            missing.append("GIGACHAT_AUTH_URL")
        if is_placeholder_secret(self.scope):
            missing.append("GIGACHAT_SCOPE")
        if self.timeout_seconds <= 0:
            missing.append("GIGACHAT_TIMEOUT_SECONDS")
        if self.timeout_seconds > MAX_GIGACHAT_TIMEOUT_SECONDS:
            missing.append("GIGACHAT_TIMEOUT_SECONDS")
        if self.max_retries < 0:
            missing.append("GIGACHAT_MAX_RETRIES")
        if self.max_retries > MAX_GIGACHAT_MAX_RETRIES:
            missing.append("GIGACHAT_MAX_RETRIES")

        if missing:
            joined = ", ".join(missing)
            raise ProviderConfigurationError(
                f"GigaChat real-provider mode requires valid values for: {joined}",
                reason_code="gigachat_config_missing_or_invalid",
                provider_name=GIGACHAT_PROVIDER_NAME,
                model_name=self.model if not is_placeholder_secret(self.model) else None,
            )


# Backward-compatible name for older imports; Stage 6 code should prefer
# GigaChatProviderConfig.
GigaChatSettings = GigaChatProviderConfig


@dataclass(frozen=True)
class ProviderResponseMetadata:
    provider_name: str
    model_name: str | None
    duration_ms: int
    retry_count: int
    structured_output_valid: bool


@dataclass
class _RequestStats:
    retry_count: int = 0


SleepFunc = Callable[[float], Awaitable[None]]


SYSTEM_PROMPT = (
    "You classify enterprise gateway requests. Return exactly one JSON object "
    "matching the backend LLMDecisionPayload contract. Do not use markdown. "
    "Do not include explanations or text before or after JSON. Use only allowed "
    "enum values. If information is missing, list missing field names. If the "
    "request is unsupported, use UNKNOWN. Tool calls are proposals only; backend "
    "validation and approval decide execution."
)

_DECISION_USER_PROMPT_TEMPLATE = """User request:
{user_request}

Return exactly one JSON object with these fields:
schema_version, request_type, domain_template, confidence, risk_level,
requires_approval, missing_fields, proposed_tool_calls, user_facing_summary,
reason_codes.

Allowed request_type values: ACCESS_REQUEST, PROCUREMENT_REQUEST,
MAINTENANCE_REQUEST, POLICY_INQUIRY, UNKNOWN.
Allowed domain_template values: ACCESS, PROCUREMENT, MAINTENANCE_LITE, POLICY,
UNKNOWN.
Allowed risk_level values: LOW, MEDIUM, HIGH, CRITICAL.
Allowed tool proposal names for Stage 6 demo access requests:
create_access_request_draft.
"""


def build_token_request(config: GigaChatProviderConfig) -> dict[str, Any]:
    """Build the OAuth request without sending it."""

    config.validate_for_real_call()
    return {
        "method": "POST",
        "url": config.auth_url,
        "headers": {
            "Accept": "application/json",
            "Authorization": f"Basic {config.authorization_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "RqUID": str(uuid4()),
        },
        "data": {"scope": config.scope},
    }


def build_structured_decision_user_prompt(request: LLMDecisionRequest) -> str:
    """Build the prompt contract for strict backend-validated JSON output."""

    return _DECISION_USER_PROMPT_TEMPLATE.format(user_request=request.user_request)


def build_chat_completion_payload(
    request: LLMDecisionRequest,
    config: GigaChatProviderConfig,
    *,
    structured: bool = True,
) -> dict[str, Any]:
    """Build a GigaChat chat completion payload without provider-native tools."""

    user_content = (
        build_structured_decision_user_prompt(request) if structured else request.user_request
    )
    return {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT if structured else "Respond briefly."},
            {"role": "user", "content": user_content},
        ],
    }


def safe_response_excerpt(text: str, *, limit: int = 300) -> str:
    """Return a short provider response excerpt without secret-bearing markers."""

    compact = " ".join(text.split())
    lowered = compact.lower()
    secret_markers = ("authorization", "access_token", "bearer ", "basic ", "api_key", "token")
    if any(marker in lowered for marker in secret_markers):
        return "[redacted: response contained sensitive markers]"
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def redacted_config_summary(config: GigaChatProviderConfig) -> dict[str, object]:
    """Return config values safe for manual smoke diagnostics."""

    return {
        "authorization_key": "<redacted>" if config.authorization_key else None,
        "auth_url": config.auth_url,
        "base_url": config.base_url,
        "scope": config.scope,
        "model": config.model,
        "timeout_seconds": config.timeout_seconds,
        "max_retries": config.max_retries,
        "verify_ssl": config.verify_ssl,
    }


def extract_safe_response_summary(raw_response: Mapping[str, Any]) -> dict[str, Any]:
    """Return metadata safe to print from a provider chat response."""

    choices = raw_response.get("choices")
    first_choice = choices[0] if isinstance(choices, list) and choices else {}
    message = first_choice.get("message") if isinstance(first_choice, dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    return {
        "model": raw_response.get("model"),
        "choices_count": len(choices) if isinstance(choices, list) else 0,
        "finish_reason": first_choice.get("finish_reason") if isinstance(first_choice, dict) else None,
        "content_chars": len(content) if isinstance(content, str) else 0,
    }


def map_gigachat_status(status_code: int) -> ProviderErrorCategory:
    """Map provider HTTP status codes to existing safe categories."""

    if status_code in {401, 403}:
        return ProviderErrorCategory.AUTH_ERROR
    if status_code == 429:
        return ProviderErrorCategory.RATE_LIMIT
    if status_code in {400, 404, 422}:
        return ProviderErrorCategory.INVALID_RESPONSE
    if status_code == 408:
        return ProviderErrorCategory.TIMEOUT
    return ProviderErrorCategory.UNAVAILABLE


class GigaChatProvider:
    """Narrow async HTTP provider for explicit manual GigaChat use."""

    def __init__(
        self,
        config: GigaChatProviderConfig | None = None,
        *,
        settings: GigaChatProviderConfig | None = None,
        env_file: Path | str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: SleepFunc = asyncio.sleep,
    ) -> None:
        self.env_file = env_file
        self.config = config or settings or GigaChatProviderConfig.from_env(env_file=env_file)
        self.settings = self.config
        self._transport = transport
        self._sleep = sleep
        self._access_token: str | None = None
        self._access_token_expires_at: float | None = None
        self.last_metadata: ProviderResponseMetadata | None = None

    async def fetch_access_token(
        self,
        client: httpx.AsyncClient,
        stats: _RequestStats | None = None,
    ) -> str:
        """Fetch and cache one access token using the configured authorization key."""

        token_request = build_token_request(self.config)
        request_stats = stats or _RequestStats()
        response = await self._request_with_retries(
            client,
            token_request["method"],
            token_request["url"],
            stats=request_stats,
            headers=token_request["headers"],
            data=token_request["data"],
        )
        payload = _response_json(response, provider_name=GIGACHAT_PROVIDER_NAME)
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise ProviderResponseError(
                "GigaChat token response did not contain access_token.",
                reason_code="gigachat_auth_response_malformed",
                provider_name=GIGACHAT_PROVIDER_NAME,
                model_name=self.config.model,
                http_status_code=response.status_code,
            )
        self._access_token = token
        self._access_token_expires_at = _token_expires_at(payload, time.time())
        return token

    async def generate_structured_decision(
        self, request: LLMDecisionRequest
    ) -> LLMDecisionResponse:
        require_real_provider_smoke_enabled(env_file=self.env_file)
        self.config.validate_for_real_call()

        started = time.perf_counter()
        stats = _RequestStats()
        async with self._create_client() as client:
            token = await self._access_token_for_request(client, stats)
            payload = build_chat_completion_payload(request, self.config, structured=True)
            response = await self._request_with_retries(
                client,
                "POST",
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                stats=stats,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
            raw_payload = _response_json(response, provider_name=GIGACHAT_PROVIDER_NAME)
            decision = parse_structured_decision_response(raw_payload, model_name=self.config.model)

        self.last_metadata = ProviderResponseMetadata(
            provider_name=GIGACHAT_PROVIDER_NAME,
            model_name=self.config.model,
            duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
            retry_count=stats.retry_count,
            structured_output_valid=True,
        )
        return LLMDecisionResponse.model_validate(decision.model_dump(mode="json"))

    async def complete_chat_text(self, user_request: str) -> str:
        """Run a simple manual chat completion and return safe text content."""

        require_real_provider_smoke_enabled(env_file=self.env_file)
        request = LLMDecisionRequest(user_request=user_request, request_id="manual-simple-chat")
        stats = _RequestStats()
        async with self._create_client() as client:
            token = await self._access_token_for_request(client, stats)
            response = await self._request_with_retries(
                client,
                "POST",
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                stats=stats,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=build_chat_completion_payload(request, self.config, structured=False),
            )
            payload = _response_json(response, provider_name=GIGACHAT_PROVIDER_NAME)
            return _extract_chat_content(payload)

    def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.timeout_seconds),
            verify=self.config.verify_ssl,
            transport=self._transport,
        )

    async def _access_token_for_request(
        self,
        client: httpx.AsyncClient,
        stats: _RequestStats,
    ) -> str:
        if self._access_token_is_valid(time.time()):
            return cast(str, self._access_token)
        return await self.fetch_access_token(client, stats)

    def _access_token_is_valid(self, now: float) -> bool:
        if not self._access_token:
            return False
        if self._access_token_expires_at is None:
            return True
        return self._access_token_expires_at - now > _TOKEN_REFRESH_SKEW_SECONDS

    async def _request_with_retries(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        stats: _RequestStats,
        **kwargs: Any,
    ) -> httpx.Response:
        attempts = self.config.max_retries + 1
        last_timeout = False
        for attempt_index in range(attempts):
            try:
                response = await client.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                last_timeout = True
                if attempt_index < self.config.max_retries:
                    stats.retry_count += 1
                    await self._sleep(_retry_delay_seconds(attempt_index))
                    continue
                raise ProviderTransportError(
                    "GigaChat request timed out.",
                    reason_code="gigachat_timeout",
                    provider_name=GIGACHAT_PROVIDER_NAME,
                    model_name=self.config.model,
                    category=ProviderErrorCategory.TIMEOUT,
                ) from exc
            except httpx.TransportError as exc:
                if attempt_index < self.config.max_retries:
                    stats.retry_count += 1
                    await self._sleep(_retry_delay_seconds(attempt_index))
                    continue
                raise ProviderTransportError(
                    "GigaChat transport request failed.",
                    reason_code="gigachat_transport_failure",
                    provider_name=GIGACHAT_PROVIDER_NAME,
                    model_name=self.config.model,
                ) from exc

            if _is_retryable_status(response.status_code) and attempt_index < self.config.max_retries:
                stats.retry_count += 1
                await self._sleep(_retry_delay_seconds(attempt_index))
                continue
            if 200 <= response.status_code < 300:
                return response
            raise _http_error(response, self.config.model, timeout_hint=last_timeout)

        raise ProviderTransportError(
            "GigaChat transport request failed.",
            reason_code="gigachat_retry_exhausted",
            provider_name=GIGACHAT_PROVIDER_NAME,
            model_name=self.config.model,
        )


def parse_structured_decision_response(
    raw_response: Mapping[str, Any],
    *,
    model_name: str | None = None,
) -> LLMDecisionResponse:
    """Parse validated decision content from a GigaChat chat completion response."""

    content = _extract_chat_content(raw_response)
    try:
        decision = parse_llm_decision_payload(content)
    except ProviderSchemaValidationError as exc:
        raise ProviderSchemaValidationError(
            exc.safe_message,
            reason_code=exc.reason_code,
            provider_name=GIGACHAT_PROVIDER_NAME,
            model_name=model_name,
        ) from exc
    return LLMDecisionResponse.model_validate(decision.model_dump(mode="json"))


def _response_json(response: httpx.Response, *, provider_name: str) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderResponseError(
            "Provider response was not valid JSON.",
            reason_code="provider_http_response_invalid_json",
            provider_name=provider_name,
            http_status_code=response.status_code,
            safe_response_excerpt=safe_response_excerpt(response.text),
        ) from exc


def _extract_chat_content(raw_response: Mapping[str, Any]) -> str:
    try:
        choices = raw_response["choices"]
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderResponseError(
            "GigaChat response did not match expected chat completion shape.",
            reason_code="gigachat_chat_response_malformed",
            provider_name=GIGACHAT_PROVIDER_NAME,
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise ProviderResponseError(
            "GigaChat response content was empty or not text.",
            reason_code="gigachat_chat_content_empty",
            provider_name=GIGACHAT_PROVIDER_NAME,
        )
    return content


def _http_error(
    response: httpx.Response,
    model_name: str,
    *,
    timeout_hint: bool = False,
) -> ProviderRuntimeError:
    excerpt = safe_response_excerpt(response.text)
    status_code = response.status_code
    if status_code in {401, 403}:
        return ProviderAuthenticationError(
            "GigaChat authentication failed.",
            reason_code="gigachat_auth_failed",
            provider_name=GIGACHAT_PROVIDER_NAME,
            model_name=model_name,
            http_status_code=status_code,
            safe_response_excerpt=excerpt,
        )
    if status_code == 429:
        return ProviderRateLimitError(
            "GigaChat rate limit was reached.",
            reason_code="gigachat_rate_limited",
            provider_name=GIGACHAT_PROVIDER_NAME,
            model_name=model_name,
            http_status_code=status_code,
            safe_response_excerpt=excerpt,
        )
    if status_code in {500, 502, 503, 504}:
        return ProviderTransportError(
            "GigaChat server error after bounded retries.",
            reason_code="gigachat_server_error",
            provider_name=GIGACHAT_PROVIDER_NAME,
            model_name=model_name,
            http_status_code=status_code,
            safe_response_excerpt=excerpt,
        )
    if status_code == 408 or timeout_hint:
        return ProviderTransportError(
            "GigaChat request timed out.",
            reason_code="gigachat_timeout_status",
            provider_name=GIGACHAT_PROVIDER_NAME,
            model_name=model_name,
            category=ProviderErrorCategory.TIMEOUT,
            http_status_code=status_code,
            safe_response_excerpt=excerpt,
        )
    if status_code == 404:
        return ProviderModelUnavailableError(
            "GigaChat model or endpoint was unavailable.",
            reason_code="gigachat_model_or_endpoint_unavailable",
            provider_name=GIGACHAT_PROVIDER_NAME,
            model_name=model_name,
            http_status_code=status_code,
            safe_response_excerpt=excerpt,
        )
    return ProviderResponseError(
        "GigaChat returned an unsupported HTTP response.",
        reason_code="gigachat_http_response_unsupported",
        provider_name=GIGACHAT_PROVIDER_NAME,
        model_name=model_name,
        http_status_code=status_code,
        safe_response_excerpt=excerpt,
    )


def _token_expires_at(payload: Mapping[str, Any], now: float) -> float | None:
    expires_at = payload.get("expires_at")
    if isinstance(expires_at, int | float):
        if expires_at > 10_000_000_000:
            return float(expires_at) / 1000.0
        return float(expires_at)
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, int | float) and expires_in > 0:
        return now + float(expires_in)
    return None


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {429, 500, 502, 503, 504}


def _retry_delay_seconds(attempt_index: int) -> float:
    return min(0.5 * (attempt_index + 1), 1.0)


def _parse_positive_float(value: str | None, default: float, env_name: str) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ProviderConfigurationError(
            f"{env_name} must be a positive number.",
            reason_code="gigachat_env_invalid_number",
            provider_name=GIGACHAT_PROVIDER_NAME,
        ) from exc
    if parsed <= 0:
        raise ProviderConfigurationError(
            f"{env_name} must be a positive number.",
            reason_code="gigachat_env_invalid_number",
            provider_name=GIGACHAT_PROVIDER_NAME,
        )
    return parsed


def _parse_non_negative_int(value: str | None, default: int, env_name: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ProviderConfigurationError(
            f"{env_name} must be a non-negative integer.",
            reason_code="gigachat_env_invalid_integer",
            provider_name=GIGACHAT_PROVIDER_NAME,
        ) from exc
    if parsed < 0:
        raise ProviderConfigurationError(
            f"{env_name} must be a non-negative integer.",
            reason_code="gigachat_env_invalid_integer",
            provider_name=GIGACHAT_PROVIDER_NAME,
        )
    return parsed


def _parse_bool(value: str | None, default: bool, env_name: str) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ProviderConfigurationError(
        f"{env_name} must be a boolean value.",
        reason_code="gigachat_env_invalid_bool",
        provider_name=GIGACHAT_PROVIDER_NAME,
    )
