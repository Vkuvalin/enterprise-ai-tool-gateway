"""Default Stage 4 policy evaluator."""

from __future__ import annotations

from enterprise_ai_tool_gateway.contracts.enums import (
    ApprovalMode,
    PolicyDecisionStatus,
    RiskLevel,
    ToolType,
)
from enterprise_ai_tool_gateway.policy.decisions import PolicyCheckRequest, PolicyDecision

_DEFAULT_APPROVER_ROLE = "manager"
_MANUAL_REVIEW_ROLE = "security_review"


def evaluate_default_tool_policy(request: PolicyCheckRequest) -> PolicyDecision:
    """Evaluate one tool against the approved Stage 4 default policy."""

    if request.risk_level is RiskLevel.CRITICAL:
        return _manual_review(
            request,
            "CRITICAL_RISK_REQUIRES_MANUAL_REVIEW",
            "Critical-risk tool calls require manual review.",
        )

    if request.tool_type in {ToolType.APPROVAL, ToolType.AUDIT}:
        return _manual_review(
            request,
            "STAGE_4_APPROVAL_AUDIT_TOOLS_REQUIRE_MANUAL_REVIEW",
            "Approval and audit tools require manual review in Stage 4.",
        )

    if (
        request.requires_approval_by_default
        and request.approval_mode is not ApprovalMode.AUTO_APPROVE
    ):
        return _requires_approval(
            request,
            "TOOL_REQUIRES_APPROVAL_BY_DEFAULT",
            "Tool metadata requires approval by default.",
        )

    if request.tool_type is ToolType.READ_ONLY:
        return _allowed(
            request,
            "READ_ONLY_ALLOWED",
            "Read-only tool call is allowed by default policy.",
        )

    if request.approval_mode is ApprovalMode.AUTO_APPROVE:
        return _allowed(
            request,
            "AUTO_APPROVE_STATE_CHANGING_ALLOWED",
            "State-changing tool call is allowed by AUTO_APPROVE mode.",
        )

    if request.approval_mode is ApprovalMode.ALWAYS_REQUIRE:
        return _requires_approval(
            request,
            "ALWAYS_REQUIRE_STATE_CHANGING_APPROVAL",
            "State-changing tool call requires approval.",
        )

    if (
        request.approval_mode is ApprovalMode.HIGH_RISK_ONLY
        and request.risk_level is RiskLevel.HIGH
    ):
        return _requires_approval(
            request,
            "HIGH_RISK_STATE_CHANGING_REQUIRES_APPROVAL",
            "High-risk state-changing tool call requires approval.",
        )

    return _allowed(
        request,
        "LOW_OR_MEDIUM_STATE_CHANGING_ALLOWED",
        "State-changing tool call is allowed by default policy.",
    )


def _allowed(request: PolicyCheckRequest, reason: str, summary: str) -> PolicyDecision:
    return PolicyDecision(
        status=PolicyDecisionStatus.ALLOWED,
        risk_level=request.risk_level,
        reasons=[reason],
        requires_approval=False,
        required_approver_role=None,
        safe_summary=summary,
    )


def _requires_approval(
    request: PolicyCheckRequest,
    reason: str,
    summary: str,
) -> PolicyDecision:
    return PolicyDecision(
        status=PolicyDecisionStatus.REQUIRES_APPROVAL,
        risk_level=request.risk_level,
        reasons=[reason],
        requires_approval=True,
        required_approver_role=_DEFAULT_APPROVER_ROLE,
        safe_summary=summary,
    )


def _manual_review(request: PolicyCheckRequest, reason: str, summary: str) -> PolicyDecision:
    return PolicyDecision(
        status=PolicyDecisionStatus.NEEDS_MANUAL_REVIEW,
        risk_level=request.risk_level,
        reasons=[reason],
        requires_approval=False,
        required_approver_role=_MANUAL_REVIEW_ROLE,
        safe_summary=summary,
    )
