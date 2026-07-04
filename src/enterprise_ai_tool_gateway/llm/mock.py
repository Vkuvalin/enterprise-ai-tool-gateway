"""Deterministic mock provider for offline tests and local development."""

from __future__ import annotations

from enterprise_ai_tool_gateway.contracts.enums import DomainTemplate, RequestType, RiskLevel
from enterprise_ai_tool_gateway.llm.base import (
    LLMDecisionRequest,
    LLMDecisionResponse,
    ProposedToolCall,
)


class MockLLMProvider:
    """Small deterministic provider that never calls the network."""

    async def generate_structured_decision(
        self, request: LLMDecisionRequest
    ) -> LLMDecisionResponse:
        normalized = request.user_request.strip().lower()
        if not normalized:
            return LLMDecisionResponse(
                request_type=RequestType.UNKNOWN,
                domain_template=DomainTemplate.UNKNOWN,
                confidence=1.0,
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                missing_fields=["user_request"],
                proposed_tool_calls=[],
                user_facing_summary="Request is empty and cannot be classified.",
                reason_codes=["EMPTY_REQUEST"],
            )

        if "access" in normalized or "доступ" in normalized:
            return LLMDecisionResponse(
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                confidence=0.95,
                risk_level=RiskLevel.MEDIUM,
                requires_approval=True,
                missing_fields=[],
                proposed_tool_calls=[
                    ProposedToolCall(
                        name="create_access_request_draft",
                        arguments={"request_id": request.request_id},
                        requires_approval=True,
                    )
                ],
                user_facing_summary="Access request classified for backend validation.",
                reason_codes=["MOCK_ACCESS_MATCH"],
            )

        return LLMDecisionResponse(
            request_type=RequestType.UNKNOWN,
            domain_template=DomainTemplate.UNKNOWN,
            confidence=0.8,
            risk_level=RiskLevel.LOW,
            requires_approval=False,
            missing_fields=[],
            proposed_tool_calls=[],
            user_facing_summary="Request requires fallback handling.",
            reason_codes=["MOCK_FALLBACK"],
        )
