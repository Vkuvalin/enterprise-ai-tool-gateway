"""YandexGPT stretch-provider spike stub.

YandexGPT remains deferred unless it is promoted from stretch scope. This file
only verifies that the existing provider boundary can host a second provider and
that missing credentials fail before any real call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from pydantic_settings import BaseSettings, SettingsConfigDict

from enterprise_ai_tool_gateway.llm.base import (
    LLMDecisionRequest,
    LLMDecisionResponse,
    ProviderConfigurationError,
    is_placeholder_secret,
    require_real_provider_smoke_enabled,
)

DEFAULT_YANDEX_MODEL = "yandexgpt"


class _YandexEnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    yandex_api_key: str | None = None
    yandex_folder_id: str | None = None
    yandex_model: str = DEFAULT_YANDEX_MODEL


@dataclass(frozen=True)
class YandexGptSettings:
    """Minimal settings for a future YandexGPT adapter."""

    api_key: str | None
    folder_id: str | None
    model: str = DEFAULT_YANDEX_MODEL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "YandexGptSettings":
        if env is None:
            loaded = _YandexEnvSettings()
            return cls(
                api_key=loaded.yandex_api_key,
                folder_id=loaded.yandex_folder_id,
                model=loaded.yandex_model,
            )
        source = env
        return cls(
            api_key=source.get("YANDEX_API_KEY"),
            folder_id=source.get("YANDEX_FOLDER_ID"),
            model=source.get("YANDEX_MODEL", DEFAULT_YANDEX_MODEL),
        )

    def validate_for_real_call(self) -> None:
        missing = []
        if is_placeholder_secret(self.api_key):
            missing.append("YANDEX_API_KEY")
        if is_placeholder_secret(self.folder_id):
            missing.append("YANDEX_FOLDER_ID")
        if is_placeholder_secret(self.model):
            missing.append("YANDEX_MODEL")

        if missing:
            joined = ", ".join(missing)
            raise ProviderConfigurationError(
                f"YandexGPT real-provider mode requires non-placeholder values for: {joined}"
            )


class YandexGptProvider:
    """Stretch-provider placeholder; no real calls in Stage 3."""

    def __init__(self, settings: YandexGptSettings | None = None) -> None:
        self.settings = settings or YandexGptSettings.from_env()

    async def generate_structured_decision(
        self, request: LLMDecisionRequest
    ) -> LLMDecisionResponse:
        require_real_provider_smoke_enabled()
        self.settings.validate_for_real_call()
        raise NotImplementedError("YandexGPT is deferred after the Stage 3 spike.")
