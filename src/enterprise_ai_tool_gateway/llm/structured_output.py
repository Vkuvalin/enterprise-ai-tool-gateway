"""Deterministic structured-output extraction for provider text."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import NoReturn

from pydantic import ValidationError

from enterprise_ai_tool_gateway.contracts.schemas import LLMDecisionPayload
from enterprise_ai_tool_gateway.llm.base import ProviderSchemaValidationError

_FENCED_JSON_PATTERN = re.compile(r"```(?:json|JSON)?\s*(.*?)\s*```", re.DOTALL)


def extract_json_object(raw_text: str) -> str:
    """Extract exactly one JSON object from provider text.

    This is intentionally strict. It performs no repair, fuzzy correction,
    candidate ranking, JSON5/YAML parsing, comment stripping, or trailing comma
    cleanup.
    """

    text = raw_text.strip()
    if not text:
        _raise_schema_error("empty_response", "Provider output was empty.")

    fenced_matches = list(_FENCED_JSON_PATTERN.finditer(text))
    if fenced_matches:
        if len(fenced_matches) != 1:
            _raise_schema_error(
                "multiple_fenced_json_blocks",
                "Provider output contained multiple fenced JSON blocks.",
            )
        match = fenced_matches[0]
        outside = f"{text[: match.start()]}{text[match.end() :]}"
        if list(_balanced_json_object_candidates(outside)):
            _raise_schema_error(
                "multiple_json_objects",
                "Provider output contained a fenced JSON block and another JSON object.",
            )
        return _validate_json_object_text(match.group(1))

    full_text_result = _try_parse_full_text(text)
    if full_text_result is not None:
        return full_text_result

    candidates = list(_balanced_json_object_candidates(text))
    if len(candidates) == 1:
        return _validate_json_object_text(candidates[0])
    if len(candidates) > 1:
        _raise_schema_error(
            "multiple_json_objects",
            "Provider output contained multiple JSON objects.",
        )

    if "{" in text or "}" in text:
        _raise_schema_error("invalid_json", "Provider output contained invalid JSON.")
    _raise_schema_error("no_json_object", "Provider output did not contain a JSON object.")


def parse_llm_decision_payload(raw_text: str) -> LLMDecisionPayload:
    """Parse provider text into the canonical validated decision payload."""

    json_text = extract_json_object(raw_text)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ProviderSchemaValidationError(
            "Provider output contained invalid JSON.",
            reason_code="invalid_json",
        ) from exc
    if not isinstance(parsed, dict):
        raise ProviderSchemaValidationError(
            "Provider output JSON root was not an object.",
            reason_code="non_object_json_root",
        )
    try:
        return LLMDecisionPayload.model_validate(parsed)
    except ValidationError as exc:
        raise ProviderSchemaValidationError(
            "Provider output did not match LLMDecisionPayload.",
            reason_code="llm_decision_schema_invalid",
        ) from exc


def _try_parse_full_text(text: str) -> str | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        _raise_schema_error(
            "non_object_json_root",
            "Provider output JSON root was not an object.",
        )
    return text


def _validate_json_object_text(json_text: str) -> str:
    candidate = json_text.strip()
    if not candidate:
        _raise_schema_error("empty_json_object_candidate", "Provider JSON candidate was empty.")
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ProviderSchemaValidationError(
            "Provider output contained invalid JSON.",
            reason_code="invalid_json",
        ) from exc
    if not isinstance(parsed, dict):
        _raise_schema_error(
            "non_object_json_root",
            "Provider output JSON root was not an object.",
        )
    return candidate


def _balanced_json_object_candidates(text: str) -> Iterable[str]:
    in_string = False
    escaped = False
    depth = 0
    array_depth = 0
    start: int | None = None

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "[" and depth == 0:
            array_depth += 1
            continue

        if char == "]" and depth == 0:
            if array_depth > 0:
                array_depth -= 1
            continue

        if char == "{":
            if array_depth > 0:
                continue
            if depth == 0:
                start = index
            depth += 1
            continue

        if char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : index + 1]
                start = None


def _raise_schema_error(reason_code: str, safe_message: str) -> NoReturn:
    raise ProviderSchemaValidationError(safe_message, reason_code=reason_code)
