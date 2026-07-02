from __future__ import annotations

import pytest

from enterprise_ai_tool_gateway.contracts.enums import (
    ApprovalMode,
    PolicyDecisionStatus,
    RiskLevel,
    ToolType,
)
from enterprise_ai_tool_gateway.policy import PolicyCheckRequest, evaluate_default_tool_policy


def make_request(
    *,
    tool_type: ToolType = ToolType.STATE_CHANGING,
    risk_level: RiskLevel = RiskLevel.LOW,
    approval_mode: ApprovalMode = ApprovalMode.HIGH_RISK_ONLY,
    requires_approval_by_default: bool = False,
) -> PolicyCheckRequest:
    return PolicyCheckRequest(
        tool_name="example_tool",
        tool_type=tool_type,
        risk_level=risk_level,
        requires_approval_by_default=requires_approval_by_default,
        approval_mode=approval_mode,
    )


def test_approval_mode_affects_approval_decision() -> None:
    auto_decision = evaluate_default_tool_policy(
        make_request(risk_level=RiskLevel.HIGH, approval_mode=ApprovalMode.AUTO_APPROVE)
    )
    high_risk_decision = evaluate_default_tool_policy(
        make_request(risk_level=RiskLevel.HIGH, approval_mode=ApprovalMode.HIGH_RISK_ONLY)
    )

    assert auto_decision.status is PolicyDecisionStatus.ALLOWED
    assert high_risk_decision.status is PolicyDecisionStatus.REQUIRES_APPROVAL


def test_critical_stays_manual_review() -> None:
    decision = evaluate_default_tool_policy(
        make_request(risk_level=RiskLevel.CRITICAL, approval_mode=ApprovalMode.AUTO_APPROVE)
    )

    assert decision.status is PolicyDecisionStatus.NEEDS_MANUAL_REVIEW
    assert decision.requires_approval is False


def test_always_require_requires_approval_for_state_changing() -> None:
    decision = evaluate_default_tool_policy(
        make_request(approval_mode=ApprovalMode.ALWAYS_REQUIRE)
    )

    assert decision.status is PolicyDecisionStatus.REQUIRES_APPROVAL
    assert decision.requires_approval is True


def test_high_risk_only_requires_approval_for_high_risk_state_changing() -> None:
    decision = evaluate_default_tool_policy(
        make_request(risk_level=RiskLevel.HIGH, approval_mode=ApprovalMode.HIGH_RISK_ONLY)
    )

    assert decision.status is PolicyDecisionStatus.REQUIRES_APPROVAL
    assert decision.requires_approval is True


def test_auto_approve_does_not_bypass_manual_review_safety_floor() -> None:
    decision = evaluate_default_tool_policy(
        make_request(
            tool_type=ToolType.AUDIT,
            risk_level=RiskLevel.LOW,
            approval_mode=ApprovalMode.AUTO_APPROVE,
        )
    )

    assert decision.status is PolicyDecisionStatus.NEEDS_MANUAL_REVIEW
    assert decision.required_approver_role == "security_review"


@pytest.mark.parametrize(
    ("approval_mode", "expected_status"),
    [
        (ApprovalMode.HIGH_RISK_ONLY, PolicyDecisionStatus.REQUIRES_APPROVAL),
        (ApprovalMode.ALWAYS_REQUIRE, PolicyDecisionStatus.REQUIRES_APPROVAL),
        (ApprovalMode.AUTO_APPROVE, PolicyDecisionStatus.ALLOWED),
    ],
)
def test_requires_approval_by_default_respects_approval_mode(
    approval_mode: ApprovalMode,
    expected_status: PolicyDecisionStatus,
) -> None:
    decision = evaluate_default_tool_policy(
        make_request(
            risk_level=RiskLevel.LOW,
            approval_mode=approval_mode,
            requires_approval_by_default=True,
        )
    )

    assert decision.status is expected_status


@pytest.mark.parametrize(
    ("approval_mode", "expected_status"),
    [
        (ApprovalMode.HIGH_RISK_ONLY, PolicyDecisionStatus.REQUIRES_APPROVAL),
        (ApprovalMode.ALWAYS_REQUIRE, PolicyDecisionStatus.REQUIRES_APPROVAL),
        (ApprovalMode.AUTO_APPROVE, PolicyDecisionStatus.ALLOWED),
    ],
)
def test_read_only_requires_approval_by_default_respects_approval_mode(
    approval_mode: ApprovalMode,
    expected_status: PolicyDecisionStatus,
) -> None:
    decision = evaluate_default_tool_policy(
        make_request(
            tool_type=ToolType.READ_ONLY,
            risk_level=RiskLevel.MEDIUM,
            approval_mode=approval_mode,
            requires_approval_by_default=True,
        )
    )

    assert decision.status is expected_status


@pytest.mark.parametrize("risk_level", [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH])
def test_read_only_without_default_approval_requirement_remains_allowed(
    risk_level: RiskLevel,
) -> None:
    decision = evaluate_default_tool_policy(
        make_request(
            tool_type=ToolType.READ_ONLY,
            risk_level=risk_level,
            approval_mode=ApprovalMode.ALWAYS_REQUIRE,
            requires_approval_by_default=False,
        )
    )

    assert decision.status is PolicyDecisionStatus.ALLOWED


def test_critical_auto_approve_still_needs_manual_review() -> None:
    decision = evaluate_default_tool_policy(
        make_request(
            risk_level=RiskLevel.CRITICAL,
            approval_mode=ApprovalMode.AUTO_APPROVE,
            requires_approval_by_default=True,
        )
    )

    assert decision.status is PolicyDecisionStatus.NEEDS_MANUAL_REVIEW


@pytest.mark.parametrize("tool_type", [ToolType.APPROVAL, ToolType.AUDIT])
def test_approval_and_audit_tools_auto_approve_still_need_manual_review(
    tool_type: ToolType,
) -> None:
    decision = evaluate_default_tool_policy(
        make_request(
            tool_type=tool_type,
            risk_level=RiskLevel.LOW,
            approval_mode=ApprovalMode.AUTO_APPROVE,
            requires_approval_by_default=True,
        )
    )

    assert decision.status is PolicyDecisionStatus.NEEDS_MANUAL_REVIEW
