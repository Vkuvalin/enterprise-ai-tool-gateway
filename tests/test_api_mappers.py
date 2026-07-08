from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from enterprise_ai_tool_gateway.api.http.mappers import approval_to_response, tool_call_to_response
from enterprise_ai_tool_gateway.audit import REDACTED_VALUE
from enterprise_ai_tool_gateway.contracts.enums import ApprovalStatus, ToolCallStatus, ToolType
from enterprise_ai_tool_gateway.contracts.schemas import ApprovalRead, ToolCallRead


def test_tool_call_response_redacts_public_payload_keys_and_values() -> None:
    now = datetime.now(UTC)
    tool_call = ToolCallRead(
        id=uuid4(),
        run_id=uuid4(),
        tool_name="create_access_request_draft",
        tool_type=ToolType.STATE_CHANGING,
        status=ToolCallStatus.SUCCEEDED,
        input_payload={
            "employee_id": "emp-001",
            "access_level": "READ",
            "duration_days": 30,
            "api_key": "secret-value",
            "message": "Authorization: Bearer abc123456",
            "approved": True,
        },
        output_payload={
            "status": "draft",
            "summary": "Bearer sk-output-token-123456789",
            "client_secret": "secret-value",
            "reason_codes": ["SYNTHETIC_DRAFT_CREATED"],
        },
        requires_approval=False,
        created_at=now,
        updated_at=now,
    )

    response = tool_call_to_response(tool_call)

    assert response.input_payload == {
        "employee_id": "emp-001",
        "access_level": "READ",
        "duration_days": 30,
        "api_key": REDACTED_VALUE,
        "message": REDACTED_VALUE,
        "approved": True,
    }
    assert response.output_payload == {
        "status": "draft",
        "summary": REDACTED_VALUE,
        "client_secret": REDACTED_VALUE,
        "reason_codes": ["SYNTHETIC_DRAFT_CREATED"],
    }


def test_approval_response_redacts_public_free_text_values_and_preserves_structure() -> None:
    now = datetime.now(UTC)
    approval_id = uuid4()
    run_id = uuid4()
    tool_call_id = uuid4()
    approval = ApprovalRead(
        id=approval_id,
        run_id=run_id,
        tool_call_id=tool_call_id,
        status=ApprovalStatus.APPROVED,
        required_approver_role="manager",
        summary="Authorization: Bearer approvalsecret123456",
        reason="api_key=approval-secret",
        decided_by="manager token=approver-token",
        decision_comment="password=approval-password",
        created_at=now,
        updated_at=now,
    )

    response = approval_to_response(approval)

    assert response.id == str(approval_id)
    assert response.run_id == str(run_id)
    assert response.tool_call_id == str(tool_call_id)
    assert response.status == "APPROVED"
    assert response.required_approver_role == "manager"
    assert response.created_at == now.isoformat()
    assert response.updated_at == now.isoformat()
    assert response.summary == REDACTED_VALUE
    assert response.reason == REDACTED_VALUE
    assert response.decided_by == REDACTED_VALUE
    assert response.decision_comment == REDACTED_VALUE
