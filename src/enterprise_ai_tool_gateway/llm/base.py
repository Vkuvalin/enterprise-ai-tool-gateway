"""Minimal provider contracts for the Stage 3 technical spike."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REAL_PROVIDER_SMOKE_FLAG = "ENABLE_REAL_PROVIDER_SMOKE"
PLACEHOLDER_VALUES = frozenset({"", "change_me", "changeme", "placeholder", "todo", "none", "null"})
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"


class _SmokeEnvSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    enable_real_provider_smoke: str = "0"


class ProviderErrorCategory(StrEnum):
    """Safe provider error categories from the provider policy."""

    AUTH_ERROR = "PROVIDER_AUTH_ERROR"
    TIMEOUT = "PROVIDER_TIMEOUT"
    RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    INVALID_RESPONSE = "PROVIDER_INVALID_RESPONSE"
    UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"


class ProviderConfigurationError(RuntimeError):
    """Raised before a real-provider call when required settings are unsafe."""


class ProviderRuntimeError(RuntimeError):
    """Raised after a real-provider call fails in a safe, categorized way."""

    def __init__(
        self,
        category: ProviderErrorCategory,
        message: str,
        *,
        http_status_code: int | None = None,
        safe_response_excerpt: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.http_status_code = http_status_code
        self.safe_response_excerpt = safe_response_excerpt


class ProposedToolCall(BaseModel):
    """Model-suggested tool call proposal, not an execution authorization."""

    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    requires_approval: bool = True


class LLMDecisionRequest(BaseModel):
    """Normalized request sent to an LLM provider."""

    model_config = ConfigDict(extra="forbid")

    user_request: str
    request_id: str = "local-spike"


class LLMDecisionResponse(BaseModel):
    """Normalized structured decision expected from every provider."""

    model_config = ConfigDict(extra="forbid")

    request_type: str
    domain_template: str
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: str
    requires_approval: bool
    missing_fields: list[str] = Field(default_factory=list)
    proposed_tool_calls: list[ProposedToolCall] = Field(default_factory=list)
    user_facing_summary: str
    reason_codes: list[str] = Field(default_factory=list)


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
            f"{REAL_PROVIDER_SMOKE_FLAG}=1 is required for real provider smoke calls"
        )
