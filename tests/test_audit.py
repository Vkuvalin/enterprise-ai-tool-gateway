from __future__ import annotations

from uuid import uuid4

import pytest

from enterprise_ai_tool_gateway.audit import REDACTED_VALUE, create_audit_event, redact_payload
from enterprise_ai_tool_gateway.audit.redaction import TRUNCATED_SUFFIX
from enterprise_ai_tool_gateway.contracts.enums import AuditEventType


def test_create_audit_event() -> None:
    run_id = uuid4()

    event = create_audit_event(
        run_id,
        AuditEventType.RUN_CREATED,
        payload={"status": "CREATED", "access_token": "secret"},
    )

    assert event.run_id == run_id
    assert event.event_type is AuditEventType.RUN_CREATED
    assert event.actor == "system"
    assert event.payload["access_token"] == REDACTED_VALUE


@pytest.mark.parametrize("actor", ["system", "user:123"])
def test_create_audit_event_accepts_safe_actor(actor: str) -> None:
    event = create_audit_event(uuid4(), AuditEventType.RUN_CREATED, actor=actor)

    assert event.actor == actor


@pytest.mark.parametrize("actor", ["access_token", "client_secret", "authorization_header"])
def test_create_audit_event_rejects_sensitive_actor_marker(actor: str) -> None:
    with pytest.raises(ValueError, match="sensitive markers"):
        create_audit_event(uuid4(), AuditEventType.RUN_CREATED, actor=actor)


def test_recursive_redaction() -> None:
    redacted = redact_payload(
        {
            "nested": {
                "password": "secret",
                "items": [{"refresh_token": "secret"}, {"safe": "value"}],
            }
        }
    )

    assert redacted["nested"] == {
        "password": REDACTED_VALUE,
        "items": [{"refresh_token": REDACTED_VALUE}, {"safe": "value"}],
    }


@pytest.mark.parametrize(
    "sensitive_value",
    [
        "Authorization: Bearer abc123456",
        "Bearer sk-live-token-123456789",
        "api_key=abc123456",
        "password=correct-horse-battery-staple",
        "token=abc123456",
        "secret: abc123456",
        "Set-Cookie: session_id=abc123456; Path=/",
    ],
)
def test_neutral_string_values_with_sensitive_markers_are_redacted(
    sensitive_value: str,
) -> None:
    redacted = redact_payload({"message": sensitive_value})

    assert redacted["message"] == REDACTED_VALUE


def test_nested_neutral_string_values_with_sensitive_markers_are_redacted() -> None:
    redacted = redact_payload(
        {
            "details": {
                "summary": "Routine change",
                "items": [
                    {"note": "No credential here."},
                    {"note": "Bearer sk-nested-token-123456789"},
                ],
            }
        }
    )

    assert redacted["details"] == {
        "summary": "Routine change",
        "items": [{"note": "No credential here."}, {"note": REDACTED_VALUE}],
    }


def test_case_insensitive_sensitive_keys() -> None:
    redacted = redact_payload({"Authorization": "Bearer secret", "CLIENT_SECRET": "secret"})

    assert redacted["Authorization"] == REDACTED_VALUE
    assert redacted["CLIENT_SECRET"] == REDACTED_VALUE


def test_compound_sensitive_keys_are_redacted() -> None:
    payload = {
        "authorization_header": "secret",
        "AuthorizationHeader": "secret",
        "x_access_token": "secret",
        "accessToken": "secret",
        "apiKey": "secret",
        "clientSecret": "secret",
        "bearer_token": "secret",
    }

    redacted = redact_payload(payload)

    assert redacted == {key: REDACTED_VALUE for key in payload}


def test_redaction_keeps_adjacent_normal_domain_keys() -> None:
    redacted = redact_payload({"access_level": "admin", "client_name": "Acme"})

    assert redacted == {"access_level": "admin", "client_name": "Acme"}


def test_value_redaction_keeps_ordinary_business_text() -> None:
    redacted = redact_payload(
        {
            "message": "API key rotation is scheduled; no credential material is included.",
            "details": "Design token guidelines are documented for the frontend.",
            "summary": "Password reset workflow review completed without sample secrets.",
        }
    )

    assert redacted == {
        "message": "API key rotation is scheduled; no credential material is included.",
        "details": "Design token guidelines are documented for the frontend.",
        "summary": "Password reset workflow review completed without sample secrets.",
    }


def test_long_string_truncation() -> None:
    redacted = redact_payload({"message": "x" * 600}, max_string_length=32)
    value = redacted["message"]

    assert isinstance(value, str)
    assert value == f"{'x' * 32}{TRUNCATED_SUFFIX}"


def test_original_payload_not_mutated() -> None:
    payload = {"nested": {"token": "secret", "safe": ["x" * 20]}}

    redacted = redact_payload(payload, max_string_length=8)

    assert payload == {"nested": {"token": "secret", "safe": ["x" * 20]}}
    assert redacted["nested"] == {
        "token": REDACTED_VALUE,
        "safe": [f"{'x' * 8}{TRUNCATED_SUFFIX}"],
    }
