"""Deterministic static providers for offline demo and acceptance paths."""

from __future__ import annotations

from enterprise_ai_tool_gateway.contracts.enums import DomainTemplate, RequestType, RiskLevel
from enterprise_ai_tool_gateway.llm.base import (
    LLMDecisionRequest,
    LLMDecisionResponse,
    ProposedToolCall,
)


class StaticDecisionProvider:
    """Offline provider that returns one deterministic structured decision."""

    def __init__(
        self,
        *,
        request_type: RequestType,
        domain_template: DomainTemplate,
        proposed_tool_name: str,
        reason_code: str,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
        requires_approval: bool = False,
    ) -> None:
        self._request_type = request_type
        self._domain_template = domain_template
        self._proposed_tool_name = proposed_tool_name
        self._reason_code = reason_code
        self._risk_level = risk_level
        self._requires_approval = requires_approval

    async def generate_structured_decision(
        self,
        request: LLMDecisionRequest,
    ) -> LLMDecisionResponse:
        _ = request
        return LLMDecisionResponse(
            request_type=self._request_type,
            domain_template=self._domain_template,
            confidence=0.95,
            risk_level=self._risk_level,
            requires_approval=self._requires_approval,
            missing_fields=[],
            proposed_tool_calls=[
                ProposedToolCall(
                    name=self._proposed_tool_name,
                    arguments={},
                    requires_approval=self._requires_approval,
                )
            ],
            user_facing_summary=f"{self._request_type.value} classified for API demo.",
            reason_codes=[self._reason_code],
        )


def create_procurement_demo_provider() -> StaticDecisionProvider:
    return StaticDecisionProvider(
        request_type=RequestType.PROCUREMENT_REQUEST,
        domain_template=DomainTemplate.PROCUREMENT,
        proposed_tool_name="create_purchase_request_draft",
        reason_code="API_PROCUREMENT_MATCH",
    )


def create_maintenance_demo_provider() -> StaticDecisionProvider:
    return StaticDecisionProvider(
        request_type=RequestType.MAINTENANCE_REQUEST,
        domain_template=DomainTemplate.MAINTENANCE_LITE,
        proposed_tool_name="create_work_order_draft",
        reason_code="API_MAINTENANCE_MATCH",
    )
