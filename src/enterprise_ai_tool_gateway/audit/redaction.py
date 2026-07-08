"""Audit payload redaction helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

REDACTED_VALUE = "[REDACTED]"
TRUNCATED_SUFFIX = "...[TRUNCATED]"
DEFAULT_MAX_STRING_LENGTH = 512

SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "access_token",
        "refresh_token",
        "token",
        "bearer",
        "password",
        "secret",
        "client_secret",
        "credentials",
        "cookie",
        "set-cookie",
    }
)
SENSITIVE_KEY_TOKENS = frozenset(
    {
        "authorization",
        "token",
        "bearer",
        "password",
        "secret",
        "credentials",
        "cookie",
    }
)
SENSITIVE_KEY_PHRASES = frozenset(
    {
        ("api", "key"),
        ("access", "token"),
        ("refresh", "token"),
        ("client", "secret"),
        ("set", "cookie"),
        ("bearer", "token"),
    }
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(
        r"\bauthorization\s*:\s*(?:bearer|basic|token)\s+\S+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bbearer\s+(?:sk-[A-Za-z0-9_-]+|[A-Za-z0-9._~+/=-]{8,})\b",
        re.IGNORECASE,
    ),
    re.compile(
        (
            r"\b(?:api[_\s-]*key|access[_\s-]*token|refresh[_\s-]*token|"
            r"client[_\s-]*secret|password|secret|token)\b"
            r"\s*[:=]\s*['\"]?[^'\"\s,;]+"
        ),
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:cookie|set-cookie)\s*:\s*[^=\s;]+=[^;\s]+",
        re.IGNORECASE,
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE),
)


def redact_payload(
    payload: Mapping[str, object] | None,
    *,
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
) -> dict[str, object]:
    """Return a recursively redacted copy of an audit payload."""

    if payload is None:
        return {}
    return {
        key: _redact_value(key, value, max_string_length=max_string_length)
        for key, value in payload.items()
    }


def has_sensitive_marker(value: str) -> bool:
    return _is_sensitive_key(value)


def _redact_value(key: str, value: object, *, max_string_length: int) -> object:
    if _is_sensitive_key(key):
        return REDACTED_VALUE
    return _redact_nested(value, max_string_length=max_string_length)


def _redact_nested(value: object, *, max_string_length: int) -> object:
    if isinstance(value, Mapping):
        return {
            str(nested_key): _redact_value(
                str(nested_key),
                nested_value,
                max_string_length=max_string_length,
            )
            for nested_key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_nested(item, max_string_length=max_string_length) for item in value]
    if _is_non_string_sequence(value):
        sequence_value = cast(Sequence[object], value)
        return [
            _redact_nested(item, max_string_length=max_string_length) for item in sequence_value
        ]
    if isinstance(value, str):
        if _has_sensitive_value_marker(value):
            return REDACTED_VALUE
        return _truncate_string(value, max_string_length=max_string_length)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized_key = key.casefold()
    if normalized_key in SENSITIVE_KEYS:
        return True

    tokens = _key_tokens(key)
    if not tokens:
        return False
    if any(token in SENSITIVE_KEY_TOKENS for token in tokens):
        return True
    return any(_contains_phrase(tokens, phrase) for phrase in SENSITIVE_KEY_PHRASES)


def _key_tokens(key: str) -> tuple[str, ...]:
    snake_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return tuple(
        token
        for token in re.split(r"[^A-Za-z0-9]+", snake_key.casefold())
        if token
    )


def _contains_phrase(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    phrase_length = len(phrase)
    return any(
        tokens[index : index + phrase_length] == phrase
        for index in range(len(tokens) - phrase_length + 1)
    )


def _has_sensitive_value_marker(value: str) -> bool:
    return any(pattern.search(value) is not None for pattern in SENSITIVE_VALUE_PATTERNS)


def _is_non_string_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)


def _truncate_string(value: str, *, max_string_length: int) -> str:
    if len(value) <= max_string_length:
        return value
    return f"{value[:max_string_length]}{TRUNCATED_SUFFIX}"
