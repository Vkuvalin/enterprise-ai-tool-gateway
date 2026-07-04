"""Manual GigaChat Lite/Pro/Max smoke matrix.

Disabled by default. This script is for explicit local/manual checks only and
does not claim production readiness.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import httpx
import truststore

from enterprise_ai_tool_gateway.contracts.enums import RequestType
from enterprise_ai_tool_gateway.llm.base import (
    LLMDecisionRequest,
    ProviderConfigurationError,
    ProviderRuntimeError,
    is_real_provider_smoke_enabled,
)
from enterprise_ai_tool_gateway.llm.gigachat import (
    GigaChatProvider,
    GigaChatProviderConfig,
    redacted_config_summary,
)
from enterprise_ai_tool_gateway.llm.structured_output import parse_llm_decision_payload

_MODEL_ALIASES = {
    "lite": "GigaChat-2-Lite",
    "pro": "GigaChat-2-Pro",
    "max": "GigaChat-2-Max",
}
_ALLOWED_STAGE6_TOOL_NAMES = {"create_access_request_draft"}


@dataclass
class MatrixResult:
    model: str
    auth: bool = False
    chat: bool = False
    structured_decision: bool = False
    schema_valid: bool = False
    stable_enums: bool = False
    stable_tools: bool = False
    usable_for_demo: bool = False
    reason: str = "not run"


def _project_env_file() -> Path:
    return Path(__file__).resolve().parents[1] / ".env"


def _enable_local_os_trust_store() -> None:
    truststore.inject_into_ssl()


def _sample_decision_json() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "request_type": "UNKNOWN",
            "domain_template": "UNKNOWN",
            "confidence": 0.7,
            "risk_level": "LOW",
            "requires_approval": False,
            "missing_fields": [],
            "proposed_tool_calls": [],
            "user_facing_summary": "Safe summary.",
            "reason_codes": ["LOCAL_EXTRACTION_PROBE"],
        },
        ensure_ascii=False,
    )


def _local_extraction_probes_pass() -> bool:
    sample = _sample_decision_json()
    parse_llm_decision_payload(sample)
    parse_llm_decision_payload(f"```json\n{sample}\n```")
    parse_llm_decision_payload(f"prefix {sample} suffix")
    return True


async def _run_model(
    base_config: GigaChatProviderConfig,
    model: str,
    env_file: Path,
    *,
    local_extract: bool,
) -> MatrixResult:
    config = GigaChatProviderConfig(
        authorization_key=base_config.authorization_key,
        auth_url=base_config.auth_url,
        base_url=base_config.base_url,
        scope=base_config.scope,
        model=model,
        timeout_seconds=base_config.timeout_seconds,
        max_retries=base_config.max_retries,
        verify_ssl=base_config.verify_ssl,
    )
    provider = GigaChatProvider(config=config, env_file=env_file)
    result = MatrixResult(model=model)
    decisions = []
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds),
            verify=config.verify_ssl,
        ) as client:
            await provider.fetch_access_token(client)
        result.auth = True

        await provider.complete_chat_text("Ответь одним коротким предложением: проверка связи.")
        result.chat = True

        prompts = [
            "Employee emp-001 needs READ access to CRM for 30 days.",
            "Сотруднику emp-001 нужен доступ READ к CRM на 30 дней.",
            "Unsupported gateway request: explain how to make coffee.",
            "!!!",
        ]
        for index, prompt in enumerate(prompts):
            decision = await provider.generate_structured_decision(
                LLMDecisionRequest(request_id=f"manual-gigachat-{index}", user_request=prompt)
            )
            decisions.append(decision)

        result.structured_decision = True
        result.schema_valid = True
        result.stable_enums = all(isinstance(decision.request_type, RequestType) for decision in decisions)
        result.stable_tools = all(
            tool.name in _ALLOWED_STAGE6_TOOL_NAMES
            for decision in decisions
            for tool in decision.proposed_tool_calls
        )
        invalid_prompt_decision = decisions[-1]
        invalid_prompt_safe = (
            invalid_prompt_decision.request_type is RequestType.UNKNOWN
            or not invalid_prompt_decision.proposed_tool_calls
        )
        result.usable_for_demo = all(
            [
                result.auth,
                result.chat,
                local_extract,
                result.structured_decision,
                result.schema_valid,
                result.stable_enums,
                result.stable_tools,
                invalid_prompt_safe,
            ]
        )
        result.reason = "ok" if result.usable_for_demo else "manual review required"
    except ProviderConfigurationError as exc:
        result.reason = f"config:{exc.reason_code}"
    except ProviderRuntimeError as exc:
        result.reason = f"provider:{exc.reason_code}"
    except Exception as exc:
        result.reason = f"unexpected:{type(exc).__name__}"
    return result


def _parse_matrix(value: str) -> list[str]:
    models = []
    for item in value.split(","):
        normalized = item.strip().lower()
        if not normalized:
            continue
        models.append(_MODEL_ALIASES.get(normalized, item.strip()))
    return models or [_MODEL_ALIASES["lite"], _MODEL_ALIASES["pro"], _MODEL_ALIASES["max"]]


def _print_table(results: list[MatrixResult]) -> None:
    print(
        "model | auth | chat | structured_decision | schema_valid | stable_enums | stable_tools | usable_for_demo | reason"
    )
    for result in results:
        print(
            " | ".join(
                [
                    result.model,
                    _status(result.auth),
                    _status(result.chat),
                    _status(result.structured_decision),
                    _status(result.schema_valid),
                    _status(result.stable_enums),
                    _status(result.stable_tools),
                    "yes" if result.usable_for_demo else "no",
                    result.reason,
                ]
            )
        )


def _status(value: bool) -> str:
    return "ok" if value else "fail"


async def _run(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file)
    if not args.live:
        print(
            "SKIPPED: live GigaChat smoke не запускался. "
            "Требуются --live и ENABLE_REAL_PROVIDER_SMOKE=1."
        )
        return 0
    if not is_real_provider_smoke_enabled(env_file=env_file):
        print(
            "SKIPPED: live GigaChat smoke не запускался. "
            f"ENABLE_REAL_PROVIDER_SMOKE=1 is not set in {env_file}."
        )
        return 0
    local_extract = _local_extraction_probes_pass()
    _enable_local_os_trust_store()
    try:
        base_config = GigaChatProviderConfig.from_env(env_file=env_file)
    except ProviderConfigurationError as exc:
        print(f"GigaChat smoke configuration failed: reason={exc.reason_code}")
        return 2

    print("GigaChat manual smoke matrix only; not a production readiness check.")
    print(f"config={redacted_config_summary(base_config)}")
    print(f"local_extract | {_status(local_extract)}")
    results = []
    for model in _parse_matrix(args.matrix):
        results.append(await _run_model(base_config, model, env_file, local_extract=local_extract))
    _print_table(results)
    return 0 if all(result.usable_for_demo for result in results) else 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Run manual GigaChat smoke matrix.")
    parser.add_argument("--matrix", default="lite,pro,max", help="Comma-separated model aliases or names.")
    parser.add_argument("--env-file", default=str(_project_env_file()), help="Path to local .env file.")
    parser.add_argument("--live", action="store_true", help="Allow a live GigaChat call when the env flag is also enabled.")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
