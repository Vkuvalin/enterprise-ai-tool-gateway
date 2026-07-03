"""Minimal Stage 4 persistence models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from enterprise_ai_tool_gateway.contracts.enums import (
    AgentRunStatus,
    ApprovalMode,
    DomainTemplate,
    RequestType,
)
from enterprise_ai_tool_gateway.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_uuid_string() -> str:
    return str(uuid4())


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid_string)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    approval_mode: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=ApprovalMode.HIGH_RISK_ONLY.value,
    )
    request_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=RequestType.UNKNOWN.value,
    )
    domain_template: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=DomainTemplate.UNKNOWN.value,
    )
    status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=AgentRunStatus.CREATED.value,
    )
    risk_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    final_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class LLMDecisionModel(Base):
    __tablename__ = "llm_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid_string)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id"),
        nullable=False,
        index=True,
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    raw_response_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validated_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    schema_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_errors: Mapped[list[object]] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


class ToolCallModel(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid_string)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class ApprovalModel(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid_string)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id"),
        nullable=False,
        index=True,
    )
    tool_call_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("tool_calls.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    required_approver_role: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid_string)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
