from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from enterprise_ai_tool_gateway.approval import (
    ApprovalDecision,
    ApprovalRequirement,
    is_approval_granted,
    is_approval_terminal,
)
from enterprise_ai_tool_gateway.contracts.enums import ApprovalStatus, RiskLevel


def test_requirement_validation() -> None:
    requirement = ApprovalRequirement(
        run_id=uuid4(),
        tool_call_id=None,
        required_approver_role="manager",
        summary="Approve CRM access draft.",
        reason="High-risk action.",
        risk_level=RiskLevel.HIGH,
        expires_at=None,
    )

    assert requirement.required_approver_role == "manager"

    with pytest.raises(ValidationError):
        ApprovalRequirement(
            run_id=None,
            tool_call_id=None,
            required_approver_role="manager",
            summary="Approve CRM access draft.",
            reason=None,
            risk_level=RiskLevel.LOW,
            expires_at=None,
        )


def test_decision_validation() -> None:
    decision = ApprovalDecision(
        status=ApprovalStatus.APPROVED,
        decided_by="approver-1",
        decision_comment="Approved.",
        decided_at=datetime.now(UTC),
    )

    assert decision.status is ApprovalStatus.APPROVED

    with pytest.raises(ValidationError):
        ApprovalDecision(status=ApprovalStatus.APPROVED)


def test_approved_is_granted() -> None:
    decision = ApprovalDecision(
        status=ApprovalStatus.APPROVED,
        decided_by="approver-1",
        decided_at=datetime.now(UTC),
    )

    assert is_approval_granted(decision) is True


def test_rejected_is_not_granted() -> None:
    decision = ApprovalDecision(
        status=ApprovalStatus.REJECTED,
        decided_by="approver-1",
        decided_at=datetime.now(UTC),
    )

    assert is_approval_granted(decision) is False


def test_pending_is_not_terminal() -> None:
    decision = ApprovalDecision(status=ApprovalStatus.PENDING)

    assert is_approval_terminal(decision) is False


@pytest.mark.parametrize(
    "status",
    [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED],
)
def test_approved_rejected_cancelled_are_terminal(status: ApprovalStatus) -> None:
    decision = ApprovalDecision(
        status=status,
        decided_by="approver-1",
        decided_at=datetime.now(UTC),
    )

    assert is_approval_terminal(decision) is True
