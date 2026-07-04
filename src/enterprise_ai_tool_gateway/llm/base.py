"""LLM provider boundary contracts and safe provider errors."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, cast

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

from enterprise_ai_tool_gateway.contracts.schemas import (
    LLMDecisionPayload,
    ProposedToolCall as ProposedToolCall,
)

REAL_PROVIDER_SMOKE_FLAG = "ENABLE_REAL_PROVIDER_SMOKE"
PLACEHOLDER_VALUES = frozenset({"", "change_me", "changeme", "placeholder", "todo", "none", "null"})
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"


class _SmokeEnvSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    enable_real_provider_smoke: str = "0"


class ProviderErrorCategory(StrEnum):
    """Safe provider error categories persisted by application runtimes."""

    AUTH_ERROR = "PROVIDER_AUTH_ERROR"
    TIMEOUT = "PROVIDER_TIMEOUT"
    RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    INVALID_RESPONSE = "PROVIDER_INVALID_RESPONSE"
    UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"


class ProviderError(RuntimeError):
    """Base provider error with redacted context only."""

    def __init__(
        self,
        safe_message: str,
        *,
        reason_code: str,
        provider_name: str = "unknown",
        model_name: str | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.reason_code = reason_code
        self.provider_name = provider_name
        self.model_name = model_name

    def safe_context(self) -> dict[str, str | None]:
        """Return context safe for logs, reports, and user-facing errors."""

        return {
            "safe_message": self.safe_message,
            "reason_code": self.reason_code,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
        }

    def __str__(self) -> str:
        return self.safe_message


class ProviderConfigurationError(ProviderError):
    """Raised before a real-provider call when required settings are unsafe."""

    def __init__(
        self,
        safe_message: str,
        *,
        reason_code: str = "provider_configuration_error",
        provider_name: str = "unknown",
        model_name: str | None = None,
    ) -> None:
        super().__init__(
            safe_message,
            reason_code=reason_code,
            provider_name=provider_name,
            model_name=model_name,
        )


class ProviderRuntimeError(ProviderError):
    """Raised after a real-provider call fails in a safe, categorized way."""

    def __init__(
        self,
        category: ProviderErrorCategory,
        safe_message: str,
        *,
        reason_code: str | None = None,
        provider_name: str = "unknown",
        model_name: str | None = None,
        http_status_code: int | None = None,
        safe_response_excerpt: str | None = None,
    ) -> None:
        super().__init__(
            safe_message,
            reason_code=reason_code or category.value,
            provider_name=provider_name,
            model_name=model_name,
        )
        self.category = category
        self.http_status_code = http_status_code
        self.safe_response_excerpt = safe_response_excerpt


class ProviderAuthenticationError(ProviderRuntimeError):
    """Authentication or authorization failed at the provider boundary."""

    def __init__(
        self,
        safe_message: str = "Provider authentication failed.",
        *,
        reason_code: str = "provider_authentication_failed",
        provider_name: str = "unknown",
        model_name: str | None = None,
        http_status_code: int | None = None,
        safe_response_excerpt: str | None = None,
    ) -> None:
        super().__init__(
            ProviderErrorCategory.AUTH_ERROR,
            safe_message,
            reason_code=reason_code,
            provider_name=provider_name,
            model_name=model_name,
            http_status_code=http_status_code,
            safe_response_excerpt=safe_response_excerpt,
        )


class ProviderTransportError(ProviderRuntimeError):
    """Provider request failed because transport or availability failed."""

    def __init__(
        self,
        safe_message: str = "Provider transport failed.",
        *,
        reason_code: str = "provider_transport_failed",
        provider_name: str = "unknown",
        model_name: str | None = None,
        category: ProviderErrorCategory = ProviderErrorCategory.UNAVAILABLE,
        http_status_code: int | None = None,
        safe_response_excerpt: str | None = None,
    ) -> None:
        super().__init__(
            category,
            safe_message,
            reason_code=reason_code,
            provider_name=provider_name,
            model_name=model_name,
            http_status_code=http_status_code,
            safe_response_excerpt=safe_response_excerpt,
        )


class ProviderRateLimitError(ProviderRuntimeError):
    """Provider rejected the request because of rate limiting."""

    def __init__(
        self,
        safe_message: str = "Provider rate limit was reached.",
        *,
        reason_code: str = "provider_rate_limited",
        provider_name: str = "unknown",
        model_name: str | None = None,
        http_status_code: int | None = None,
        safe_response_excerpt: str | None = None,
    ) -> None:
        super().__init__(
            ProviderErrorCategory.RATE_LIMIT,
            safe_message,
            reason_code=reason_code,
            provider_name=provider_name,
            model_name=model_name,
            http_status_code=http_status_code,
            safe_response_excerpt=safe_response_excerpt,
        )


class ProviderResponseError(ProviderRuntimeError):
    """Provider returned a malformed or unsupported response."""

    def __init__(
        self,
        safe_message: str = "Provider response was invalid.",
        *,
        reason_code: str = "provider_response_invalid",
        provider_name: str = "unknown",
        model_name: str | None = None,
        http_status_code: int | None = None,
        safe_response_excerpt: str | None = None,
    ) -> None:
        super().__init__(
            ProviderErrorCategory.INVALID_RESPONSE,
            safe_message,
            reason_code=reason_code,
            provider_name=provider_name,
            model_name=model_name,
            http_status_code=http_status_code,
            safe_response_excerpt=safe_response_excerpt,
        )


class ProviderSchemaValidationError(ProviderRuntimeError):
    """Provider text could not become a validated decision payload."""

    def __init__(
        self,
        safe_message: str = "Provider output failed schema validation.",
        *,
        reason_code: str = "provider_schema_validation_failed",
        provider_name: str = "unknown",
        model_name: str | None = None,
    ) -> None:
        super().__init__(
            ProviderErrorCategory.INVALID_RESPONSE,
            safe_message,
            reason_code=reason_code,
            provider_name=provider_name,
            model_name=model_name,
        )


class ProviderModelUnavailableError(ProviderRuntimeError):
    """Requested provider model is unavailable or unsupported."""

    def __init__(
        self,
        safe_message: str = "Provider model is unavailable.",
        *,
        reason_code: str = "provider_model_unavailable",
        provider_name: str = "unknown",
        model_name: str | None = None,
        http_status_code: int | None = None,
        safe_response_excerpt: str | None = None,
    ) -> None:
        super().__init__(
            ProviderErrorCategory.INVALID_RESPONSE,
            safe_message,
            reason_code=reason_code,
            provider_name=provider_name,
            model_name=model_name,
            http_status_code=http_status_code,
            safe_response_excerpt=safe_response_excerpt,
        )


class LLMDecisionRequest(BaseModel):
    """Normalized request sent to an LLM provider."""

    model_config = ConfigDict(extra="forbid")

    user_request: str
    request_id: str = "local-spike"


class LLMDecisionResponse(LLMDecisionPayload):
    """Compatibility name for the canonical provider decision payload."""


class LLMProviderPort(Protocol):
    """Provider port used by future workflow code."""

    async def generate_structured_decision(
        self, request: LLMDecisionRequest
    ) -> LLMDecisionResponse:
        """Generate one validated structured decision."""
        ...


def is_placeholder_secret(value: str | None) -> bool:
    """Return True when a credential-like value is absent or still a placeholder."""

    if value is None:
        return True
    return value.strip().lower() in PLACEHOLDER_VALUES


def is_real_provider_smoke_enabled(
    env: Mapping[str, str] | None = None,
    *,
    env_file: Path | str | None = None,
) -> bool:
    """Check the explicit opt-in flag required for real provider smoke calls."""

    if env is None:
        value = os.environ.get(REAL_PROVIDER_SMOKE_FLAG)
        if value is None:
            settings_cls = cast(Any, _SmokeEnvSettings)
            value = settings_cls(_env_file=env_file or PROJECT_ENV_FILE).enable_real_provider_smoke
    else:
        value = env.get(REAL_PROVIDER_SMOKE_FLAG, "0")
    return value.strip().lower() in {"1", "true", "yes"}


def require_real_provider_smoke_enabled(
    env: Mapping[str, str] | None = None,
    *,
    env_file: Path | str | None = None,
) -> None:
    """Fail early unless real-provider smoke execution was explicitly enabled."""

    if not is_real_provider_smoke_enabled(env, env_file=env_file):
        raise ProviderConfigurationError(
            f"{REAL_PROVIDER_SMOKE_FLAG}=1 is required for real provider smoke calls",
            reason_code="real_provider_smoke_not_enabled",
        )
