"""Approval requirement and decision primitives."""

from enterprise_ai_tool_gateway.approval.primitives import (
    ApprovalDecision,
    ApprovalRequirement,
    is_approval_granted,
    is_approval_terminal,
)

__all__ = [
    "ApprovalDecision",
    "ApprovalRequirement",
    "is_approval_granted",
    "is_approval_terminal",
]
