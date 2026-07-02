"""Audit event creation boundary."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from enterprise_ai_tool_gateway.audit.redaction import has_sensitive_marker, redact_payload
from enterprise_ai_tool_gateway.contracts.enums import AuditEventType
from enterprise_ai_tool_gateway.contracts.schemas import AuditEventCreate


def create_audit_event(
    run_id: UUID,
    event_type: AuditEventType,
    *,
    actor: str = "system",
    payload: Mapping[str, object] | None = None,
) -> AuditEventCreate:
    """Create a redacted audit event contract without writing persistence."""

    if has_sensitive_marker(actor):
        raise ValueError("Audit actor contains sensitive markers")
    return AuditEventCreate(
        run_id=run_id,
        event_type=event_type,
        actor=actor,
        payload=redact_payload(payload),
    )
