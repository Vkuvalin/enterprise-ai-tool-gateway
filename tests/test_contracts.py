from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from enterprise_ai_tool_gateway.contracts import (
    AgentRunCreate,
    AgentRunRead,
    AgentRunStatus,
    ApprovalCreate,
    ApprovalMode,
    ApprovalRead,
    ApprovalStatus,
    AuditEventCreate,
    AuditEventRead,
    AuditEventType,
    DomainTemplate,
    LLMDecisionCreate,
    LLMDecisionPayload,
    LLMDecisionRead,
    PolicyDecisionStatus,
    ProviderName,
    ProposedToolCall,
    RequestType,
    RiskLevel,
    ToolCallCreate,
    ToolCallRead,
    ToolCallStatus,
    ToolType,
)
from enterprise_ai_tool_gateway.llm import LLMDecisionRequest, MockLLMProvider


def test_core_enum_values_are_stable_strings() -> None:
    assert [item.value for item in RequestType] == [
        "ACCESS_REQUEST",
        "PROCUREMENT_REQUEST",
        "MAINTENANCE_REQUEST",
        "POLICY_INQUIRY",
        "UNKNOWN",
    ]
    assert [item.value for item in DomainTemplate] == [
        "ACCESS",
        "PROCUREMENT",
        "MAINTENANCE_LITE",
        "POLICY",
        "UNKNOWN",
    ]
    assert [item.value for item in AgentRunStatus] == [
        "CREATED",
        "CLASSIFYING",
        "DECISION_VALIDATION",
        "NEEDS_USER_INPUT",
        "TOOL_PLANNING",
        "TOOL_VALIDATION",
        "EXECUTING_READ_TOOLS",
        "POLICY_CHECK",
        "WAITING_FOR_APPROVAL",
        "EXECUTING_ACTION",
        "COMPLETED",
        "FAILED_PROVIDER",
        "FAILED_VALIDATION",
        "FAILED_TOOL",
        "REJECTED",
        "NEEDS_MANUAL_REVIEW",
    ]
    assert [item.value for item in RiskLevel] == ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert [item.value for item in ToolType] == [
        "READ_ONLY",
        "STATE_CHANGING",
        "APPROVAL",
        "AUDIT",
    ]
    assert [item.value for item in ToolCallStatus] == [
        "PROPOSED",
        "VALIDATED",
        "EXECUTING",
        "SUCCEEDED",
        "FAILED",
        "REJECTED",
        "WAITING_FOR_APPROVAL",
    ]
    assert [item.value for item in ApprovalStatus] == [
        "PENDING",
        "APPROVED",
        "REJECTED",
        "CANCELLED",
    ]
    assert [item.value for item in PolicyDecisionStatus] == [
        "ALLOWED",
        "DENIED",
        "REQUIRES_APPROVAL",
        "NEEDS_MANUAL_REVIEW",
    ]
    assert [item.value for item in ApprovalMode] == [
        "AUTO_APPROVE",
        "HIGH_RISK_ONLY",
        "ALWAYS_REQUIRE",
    ]
    assert [item.value for item in ProviderName] == ["MOCK", "GIGACHAT", "YANDEX"]
    assert [item.value for item in AuditEventType] == [
        "RUN_CREATED",
        "PROVIDER_SELECTED",
        "DECISION_VALIDATED",
        "TOOL_PROPOSED",
        "TOOL_VALIDATED",
        "TOOL_EXECUTED",
        "POLICY_CHECKED",
        "APPROVAL_REQUESTED",
        "APPROVAL_DECIDED",
        "USER_INPUT_REQUIRED",
        "MANUAL_REVIEW_REQUIRED",
        "RUN_REJECTED",
        "RUN_COMPLETED",
        "RUN_FAILED",
    ]


def test_agent_run_create_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AgentRunCreate.model_validate(
            {
                "user_id": "user-1",
                "request_text": "Need access",
                "unexpected": "value",
            }
        )


def test_agent_run_create_defaults_approval_mode() -> None:
    create = AgentRunCreate(user_id="user-1", request_text="Need access")

    assert create.approval_mode is ApprovalMode.HIGH_RISK_ONLY


def test_llm_decision_payload_validates_enums_and_nested_tools() -> None:
    decision = LLMDecisionPayload(
        request_type=RequestType.ACCESS_REQUEST,
        domain_template=DomainTemplate.ACCESS,
        confidence=0.95,
        risk_level=RiskLevel.MEDIUM,
        requires_approval=True,
        proposed_tool_calls=[
            ProposedToolCall(
                name="create_access_request_draft",
                arguments={"run_id": "run-1"},
                requires_approval=True,
            )
        ],
        user_facing_summary="Access request classified.",
        reason_codes=["ACCESS_MATCH"],
    )

    assert decision.schema_version == "1.0"
    assert decision.request_type == RequestType.ACCESS_REQUEST
    assert decision.domain_template is DomainTemplate.ACCESS
    assert decision.proposed_tool_calls[0].arguments == {"run_id": "run-1"}


def test_llm_decision_payload_rejects_unknown_enum_value() -> None:
    with pytest.raises(ValidationError):
        LLMDecisionPayload.model_validate(
            {
                "request_type": "INCIDENT",
                "domain_template": DomainTemplate.UNKNOWN,
                "confidence": 0.2,
                "risk_level": RiskLevel.LOW,
                "requires_approval": False,
                "user_facing_summary": "Unknown",
            }
        )


def test_llm_decision_payload_accepts_legacy_domain_template_alias() -> None:
    decision = LLMDecisionPayload.model_validate(
        {
            "request_type": RequestType.ACCESS_REQUEST,
            "domain_template": "ACCESS_REQUEST",
            "confidence": 0.95,
            "risk_level": RiskLevel.MEDIUM,
            "requires_approval": True,
            "user_facing_summary": "Access request classified.",
        }
    )

    assert decision.domain_template is DomainTemplate.ACCESS


def test_read_contracts_validate_minimal_foundation_shapes() -> None:
    now = datetime.now(UTC)
    run_id = uuid4()
    tool_call_id = uuid4()
    approval_id = uuid4()

    run = AgentRunRead(
        id=run_id,
        user_id="user-1",
        request_text="Need access",
        approval_mode=ApprovalMode.ALWAYS_REQUIRE,
        request_type=RequestType.ACCESS_REQUEST,
        domain_template=DomainTemplate.ACCESS,
        status=AgentRunStatus.CREATED,
        risk_level=None,
        requires_approval=False,
        provider_name=ProviderName.MOCK,
        model_name="mock-model",
        final_summary=None,
        error_type=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    tool_call = ToolCallRead(
        id=tool_call_id,
        run_id=run_id,
        tool_name="fake_policy_lookup",
        tool_type=ToolType.READ_ONLY,
        status=ToolCallStatus.PROPOSED,
        input_payload={"request_type": RequestType.ACCESS_REQUEST.value},
        output_payload=None,
        error_message=None,
        requires_approval=False,
        approval_id=approval_id,
        created_at=now,
        updated_at=now,
    )
    approval = ApprovalRead(
        id=approval_id,
        run_id=run_id,
        tool_call_id=tool_call_id,
        status=ApprovalStatus.PENDING,
        required_approver_role="manager",
        summary="Approve access draft",
        reason=None,
        decided_by=None,
        decision_comment=None,
        created_at=now,
        updated_at=now,
    )
    event = AuditEventRead(
        id=uuid4(),
        run_id=run_id,
        event_type=AuditEventType.RUN_CREATED,
        actor="system",
        payload={"status": AgentRunStatus.CREATED.value},
        created_at=now,
    )

    assert run.id == run_id
    assert run.approval_mode is ApprovalMode.ALWAYS_REQUIRE
    assert run.model_name == "mock-model"
    assert tool_call.approval_id == approval_id
    assert approval.tool_call_id == tool_call_id
    assert event.payload == {"status": "CREATED"}


def test_stage_4_create_and_read_contracts_validate_foundation_shapes() -> None:
    now = datetime.now(UTC)
    run_id = uuid4()
    decision_id = uuid4()
    tool_call_id = uuid4()

    decision_create = LLMDecisionCreate(
        run_id=run_id,
        validated_payload={"request_type": RequestType.UNKNOWN.value},
        schema_valid=True,
        confidence=0.7,
    )
    decision_read = LLMDecisionRead(
        id=decision_id,
        run_id=run_id,
        schema_version="1.0",
        validated_payload=decision_create.validated_payload,
        schema_valid=True,
        validation_errors=[],
        confidence=0.7,
        created_at=now,
    )
    tool_call_create = ToolCallCreate(
        run_id=run_id,
        tool_name="fake_policy_lookup",
        tool_type=ToolType.READ_ONLY,
        input_payload={"request_type": RequestType.UNKNOWN.value},
        requires_approval=False,
    )
    approval_create = ApprovalCreate(
        run_id=run_id,
        tool_call_id=tool_call_id,
        required_approver_role="manager",
        summary="Approve action",
    )
    audit_create = AuditEventCreate(
        run_id=run_id,
        event_type=AuditEventType.USER_INPUT_REQUIRED,
        payload={"missing_fields": ["system"]},
    )

    assert decision_read.run_id == decision_create.run_id
    assert tool_call_create.status is ToolCallStatus.PROPOSED
    assert approval_create.status is ApprovalStatus.PENDING
    assert audit_create.actor == "system"


@pytest.mark.asyncio
async def test_existing_mock_provider_uses_shared_decision_contract() -> None:
    decision = await MockLLMProvider().generate_structured_decision(
        LLMDecisionRequest(user_request="Нужен доступ к CRM.")
    )

    payload = LLMDecisionPayload.model_validate(decision.model_dump())

    assert decision.request_type == RequestType.ACCESS_REQUEST
    assert decision.domain_template is DomainTemplate.ACCESS
    assert payload.request_type is RequestType.ACCESS_REQUEST
    assert payload.domain_template is DomainTemplate.ACCESS
    assert isinstance(decision.proposed_tool_calls[0], ProposedToolCall)
    assert payload.proposed_tool_calls[0].name == "create_access_request_draft"
