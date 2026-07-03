"""Minimal repository for already validated gateway facts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_ai_tool_gateway.contracts.enums import (
    AgentRunStatus,
    ApprovalMode,
    ApprovalStatus,
    AuditEventType,
    DomainTemplate,
    ProviderName,
    RequestType,
    RiskLevel,
    ToolCallStatus,
    ToolType,
)
from enterprise_ai_tool_gateway.contracts.schemas import (
    AgentRunCreate,
    AgentRunRead,
    ApprovalCreate,
    ApprovalRead,
    AuditEventCreate,
    AuditEventRead,
    LLMDecisionCreate,
    LLMDecisionRead,
    ToolCallCreate,
    ToolCallRead,
)
from enterprise_ai_tool_gateway.db.models import (
    AgentRunModel,
    ApprovalModel,
    AuditEventModel,
    LLMDecisionModel,
    ToolCallModel,
    utc_now,
)


class GatewayRepository:
    """Persistence facade that does not decide workflow or policy outcomes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_agent_run(
        self,
        create: AgentRunCreate,
        *,
        request_type: RequestType = RequestType.UNKNOWN,
        domain_template: DomainTemplate = DomainTemplate.UNKNOWN,
        status: AgentRunStatus = AgentRunStatus.CREATED,
        risk_level: RiskLevel | None = None,
        requires_approval: bool = False,
        provider_name: ProviderName | None = None,
        model_name: str | None = None,
    ) -> AgentRunRead:
        model = AgentRunModel(
            user_id=create.user_id,
            request_text=create.request_text,
            approval_mode=create.approval_mode.value,
            request_type=request_type.value,
            domain_template=domain_template.value,
            status=status.value,
            risk_level=risk_level.value if risk_level is not None else None,
            requires_approval=requires_approval,
            provider_name=provider_name.value if provider_name is not None else None,
            model_name=model_name,
        )
        self._session.add(model)
        await self._session.flush()
        return _agent_run_to_read(model)

    async def get_agent_run(self, run_id: UUID) -> AgentRunRead | None:
        model = await self._session.get(AgentRunModel, str(run_id))
        if model is None:
            return None
        return _agent_run_to_read(model)

    async def update_agent_run_status(
        self,
        run_id: UUID,
        status: AgentRunStatus,
    ) -> AgentRunRead:
        model = await self._session.get(AgentRunModel, str(run_id))
        if model is None:
            raise KeyError(f"AgentRun {run_id} does not exist")
        model.status = status.value
        model.updated_at = utc_now()
        await self._session.flush()
        return _agent_run_to_read(model)

    async def update_agent_run_result(
        self,
        run_id: UUID,
        *,
        status: AgentRunStatus,
        request_type: RequestType | None = None,
        domain_template: DomainTemplate | None = None,
        risk_level: RiskLevel | None = None,
        requires_approval: bool | None = None,
        provider_name: ProviderName | None = None,
        model_name: str | None = None,
        final_summary: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> AgentRunRead:
        model = await self._session.get(AgentRunModel, str(run_id))
        if model is None:
            raise KeyError(f"AgentRun {run_id} does not exist")
        model.status = status.value
        if request_type is not None:
            model.request_type = request_type.value
        if domain_template is not None:
            model.domain_template = domain_template.value
        if risk_level is not None:
            model.risk_level = risk_level.value
        if requires_approval is not None:
            model.requires_approval = requires_approval
        if provider_name is not None:
            model.provider_name = provider_name.value
        if model_name is not None:
            model.model_name = model_name
        if final_summary is not None:
            model.final_summary = final_summary
        if error_type is not None:
            model.error_type = error_type
        if error_message is not None:
            model.error_message = error_message
        model.updated_at = utc_now()
        await self._session.flush()
        return _agent_run_to_read(model)

    async def add_llm_decision(self, create: LLMDecisionCreate) -> LLMDecisionRead:
        model = LLMDecisionModel(
            run_id=str(create.run_id),
            schema_version=create.schema_version,
            raw_response_ref=create.raw_response_ref,
            validated_payload=create.validated_payload,
            schema_valid=create.schema_valid,
            validation_errors=create.validation_errors,
            confidence=create.confidence,
        )
        self._session.add(model)
        await self._session.flush()
        return _llm_decision_to_read(model)

    async def add_tool_call(self, create: ToolCallCreate) -> ToolCallRead:
        model = ToolCallModel(
            run_id=str(create.run_id),
            tool_name=create.tool_name,
            tool_type=create.tool_type.value,
            status=create.status.value,
            input_payload=create.input_payload,
            output_payload=create.output_payload,
            error_message=create.error_message,
            requires_approval=create.requires_approval,
            approval_id=str(create.approval_id) if create.approval_id is not None else None,
        )
        self._session.add(model)
        await self._session.flush()
        return _tool_call_to_read(model)

    async def get_tool_call(self, tool_call_id: UUID) -> ToolCallRead | None:
        model = await self._session.get(ToolCallModel, str(tool_call_id))
        if model is None:
            return None
        return _tool_call_to_read(model)

    async def update_tool_call_result(
        self,
        tool_call_id: UUID,
        *,
        status: ToolCallStatus,
        output_payload: dict[str, object] | None = None,
        error_message: str | None = None,
        approval_id: UUID | None = None,
    ) -> ToolCallRead:
        model = await self._session.get(ToolCallModel, str(tool_call_id))
        if model is None:
            raise KeyError(f"ToolCall {tool_call_id} does not exist")
        model.status = status.value
        model.output_payload = output_payload
        model.error_message = error_message
        if approval_id is not None:
            model.approval_id = str(approval_id)
        model.updated_at = utc_now()
        await self._session.flush()
        return _tool_call_to_read(model)

    async def list_tool_calls(self, run_id: UUID) -> list[ToolCallRead]:
        result = await self._session.execute(
            select(ToolCallModel)
            .where(ToolCallModel.run_id == str(run_id))
            .order_by(ToolCallModel.created_at, ToolCallModel.id)
        )
        return [_tool_call_to_read(model) for model in result.scalars()]

    async def add_approval(self, create: ApprovalCreate) -> ApprovalRead:
        model = ApprovalModel(
            run_id=str(create.run_id),
            tool_call_id=str(create.tool_call_id) if create.tool_call_id is not None else None,
            status=create.status.value,
            required_approver_role=create.required_approver_role,
            summary=create.summary,
            reason=create.reason,
            decided_by=create.decided_by,
            decision_comment=create.decision_comment,
        )
        self._session.add(model)
        await self._session.flush()
        return _approval_to_read(model)

    async def get_approval(self, approval_id: UUID) -> ApprovalRead | None:
        model = await self._session.get(ApprovalModel, str(approval_id))
        if model is None:
            return None
        return _approval_to_read(model)

    async def update_approval_decision(
        self,
        approval_id: UUID,
        *,
        status: ApprovalStatus,
        decided_by: str,
        decision_comment: str | None = None,
    ) -> ApprovalRead:
        model = await self._session.get(ApprovalModel, str(approval_id))
        if model is None:
            raise KeyError(f"Approval {approval_id} does not exist")
        model.status = status.value
        model.decided_by = decided_by
        model.decision_comment = decision_comment
        model.updated_at = utc_now()
        await self._session.flush()
        return _approval_to_read(model)

    async def list_approvals(self, run_id: UUID) -> list[ApprovalRead]:
        result = await self._session.execute(
            select(ApprovalModel)
            .where(ApprovalModel.run_id == str(run_id))
            .order_by(ApprovalModel.created_at, ApprovalModel.id)
        )
        return [_approval_to_read(model) for model in result.scalars()]

    async def add_audit_event(self, create: AuditEventCreate) -> AuditEventRead:
        model = AuditEventModel(
            run_id=str(create.run_id),
            event_type=create.event_type.value,
            actor=create.actor,
            payload=create.payload,
        )
        self._session.add(model)
        await self._session.flush()
        return _audit_event_to_read(model)

    async def list_audit_events(self, run_id: UUID) -> list[AuditEventRead]:
        result = await self._session.execute(
            select(AuditEventModel)
            .where(AuditEventModel.run_id == str(run_id))
            .order_by(AuditEventModel.created_at, AuditEventModel.id)
        )
        return [_audit_event_to_read(model) for model in result.scalars()]


def _agent_run_to_read(model: AgentRunModel) -> AgentRunRead:
    return AgentRunRead(
        id=UUID(model.id),
        user_id=model.user_id,
        request_text=model.request_text,
        approval_mode=ApprovalMode(model.approval_mode),
        request_type=RequestType(model.request_type),
        domain_template=DomainTemplate(model.domain_template),
        status=AgentRunStatus(model.status),
        risk_level=RiskLevel(model.risk_level) if model.risk_level is not None else None,
        requires_approval=model.requires_approval,
        provider_name=ProviderName(model.provider_name) if model.provider_name is not None else None,
        model_name=model.model_name,
        final_summary=model.final_summary,
        error_type=model.error_type,
        error_message=model.error_message,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _llm_decision_to_read(model: LLMDecisionModel) -> LLMDecisionRead:
    return LLMDecisionRead(
        id=UUID(model.id),
        run_id=UUID(model.run_id),
        schema_version=model.schema_version,
        raw_response_ref=model.raw_response_ref,
        validated_payload=cast(dict[str, object], model.validated_payload),
        schema_valid=model.schema_valid,
        validation_errors=cast(list[object], model.validation_errors),
        confidence=model.confidence,
        created_at=_as_utc(model.created_at),
    )


def _tool_call_to_read(model: ToolCallModel) -> ToolCallRead:
    return ToolCallRead(
        id=UUID(model.id),
        run_id=UUID(model.run_id),
        tool_name=model.tool_name,
        tool_type=ToolType(model.tool_type),
        status=ToolCallStatus(model.status),
        input_payload=cast(dict[str, object], model.input_payload),
        output_payload=cast(dict[str, object] | None, model.output_payload),
        error_message=model.error_message,
        requires_approval=model.requires_approval,
        approval_id=UUID(model.approval_id) if model.approval_id is not None else None,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _approval_to_read(model: ApprovalModel) -> ApprovalRead:
    return ApprovalRead(
        id=UUID(model.id),
        run_id=UUID(model.run_id),
        tool_call_id=UUID(model.tool_call_id) if model.tool_call_id is not None else None,
        status=ApprovalStatus(model.status),
        required_approver_role=model.required_approver_role,
        summary=model.summary,
        reason=model.reason,
        decided_by=model.decided_by,
        decision_comment=model.decision_comment,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _audit_event_to_read(model: AuditEventModel) -> AuditEventRead:
    return AuditEventRead(
        id=UUID(model.id),
        run_id=UUID(model.run_id),
        event_type=AuditEventType(model.event_type),
        actor=model.actor,
        payload=cast(dict[str, object], model.payload),
        created_at=_as_utc(model.created_at),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
