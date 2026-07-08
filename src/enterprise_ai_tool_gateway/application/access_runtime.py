"""Application coordinator for the Stage 5 access request workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_ai_tool_gateway.access import register_access_tools
from enterprise_ai_tool_gateway.access.schemas import (
    AccessLevel,
    AccessPolicyOutput,
    CreateAccessRequestDraftOutput,
    EmployeeStatus,
    GetEmployeeProfileOutput,
    GetExistingAccessTicketsOutput,
    GetSystemInfoOutput,
)
from enterprise_ai_tool_gateway.approval import (
    ApprovalDecision,
    ApprovalRequirement,
    is_approval_granted,
)
from enterprise_ai_tool_gateway.application.dtos import (
    AccessApprovalResolutionRequest,
    AccessWorkflowRequest,
    AccessWorkflowResult,
)
from enterprise_ai_tool_gateway.audit import create_audit_event
from enterprise_ai_tool_gateway.contracts.enums import (
    AgentRunStatus,
    ApprovalStatus,
    AuditEventType,
    DomainTemplate,
    PolicyDecisionStatus,
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
    AuditEventRead,
    LLMDecisionCreate,
    LLMDecisionPayload,
    ToolCallCreate,
    ToolCallRead,
)
from enterprise_ai_tool_gateway.db import GatewayRepository
from enterprise_ai_tool_gateway.llm import (
    LLMDecisionRequest,
    LLMProviderPort,
    MockLLMProvider,
    ProviderRuntimeError,
)
from enterprise_ai_tool_gateway.policy import (
    PolicyCheckRequest,
    PolicyDecision,
    evaluate_default_tool_policy,
)
from enterprise_ai_tool_gateway.tools import (
    ToolExecutionError,
    ToolExecutionNotAuthorizedError,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutor,
    ToolInputValidationError,
    ToolOutputValidationError,
    ToolRegistry,
    UnknownToolError,
)
from enterprise_ai_tool_gateway.workflow import WorkflowEventType, transition

_ACCESS_READ_TOOL_NAMES = (
    "get_employee_profile",
    "get_system_info",
    "search_access_policy",
    "get_existing_access_tickets",
)
_ACCESS_ACTION_TOOL_NAME = "create_access_request_draft"
_ACCESS_TOOL_NAMES = {*_ACCESS_READ_TOOL_NAMES, _ACCESS_ACTION_TOOL_NAME}
_SAFE_TOOL_BOUNDARY_ERROR = "Tool boundary failure was handled safely."
_TOOL_BOUNDARY_EXCEPTIONS = (
    UnknownToolError,
    ToolInputValidationError,
    ToolOutputValidationError,
    ToolExecutionNotAuthorizedError,
    ToolExecutionError,
)
_PolicyEvaluator = Callable[[PolicyCheckRequest], PolicyDecision]


@dataclass(frozen=True)
class _AccessRequestFields:
    employee_id: str
    system_id: str
    access_level: AccessLevel
    duration_days: int


@dataclass(frozen=True)
class _ProviderDecisionValidationResult:
    is_valid: bool
    reason_codes: list[str]
    safe_summary: str | None = None


class AccessWorkflowRuntime:
    """Coordinate one approved access workflow transaction at a time."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        provider: LLMProviderPort | None = None,
        registry: ToolRegistry | None = None,
        policy_evaluator: _PolicyEvaluator | None = None,
        provider_name: ProviderName = ProviderName.MOCK,
        model_name: str = "mock-provider",
    ) -> None:
        self._session = session
        self._repo = GatewayRepository(session)
        self._provider = provider or MockLLMProvider()
        self._registry = registry or register_access_tools(ToolRegistry())
        self._executor = ToolExecutor(self._registry)
        self._policy_evaluator = policy_evaluator or evaluate_default_tool_policy
        self._provider_name = provider_name
        self._model_name = model_name

    async def submit_access_request(self, request: AccessWorkflowRequest) -> AccessWorkflowResult:
        run = await self._repo.create_agent_run(
            AgentRunCreate(
                user_id=request.user_id,
                request_text=request.request_text,
                approval_mode=request.approval_mode,
            )
        )
        await self._audit(
            run.id,
            AuditEventType.RUN_CREATED,
            {
                "status": AgentRunStatus.CREATED.value,
                "approval_mode": request.approval_mode.value,
                "request_type": RequestType.ACCESS_REQUEST.value,
            },
        )

        status = transition(run.status, WorkflowEventType.START_CLASSIFICATION)
        await self._audit(
            run.id,
            AuditEventType.PROVIDER_SELECTED,
            {
                "provider_name": self._provider_name.value,
                "model_name": self._model_name,
                "approval_mode": request.approval_mode.value,
            },
        )

        try:
            provider_response = await self._provider.generate_structured_decision(
                LLMDecisionRequest(user_request=request.request_text, request_id=str(run.id))
            )
        except ProviderRuntimeError as exc:
            status = transition(status, WorkflowEventType.PROVIDER_FAILED)
            final_summary = "Access request failed because the provider was unavailable."
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=final_summary,
                error_type=exc.category.value,
                error_message="Provider call failed safely.",
            )
            await self._audit(
                run.id,
                AuditEventType.RUN_FAILED,
                {"status": status.value, "error_type": exc.category.value},
            )
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.PROVIDER_DECISION_RECEIVED)
        decision_payload, schema_valid = await self._persist_decision(run.id, provider_response)
        if not schema_valid or decision_payload is None:
            status = transition(status, WorkflowEventType.DECISION_INVALID)
            await self._audit(
                run.id,
                AuditEventType.DECISION_VALIDATED,
                {"schema_valid": False, "reason_codes": ["LLM_OUTPUT_VALIDATION_ERROR"]},
            )
            final_summary = "Access request failed validation because provider output was invalid."
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=final_summary,
                error_type="LLM_OUTPUT_VALIDATION_ERROR",
                error_message="Provider output failed schema validation.",
            )
            await self._audit(run.id, AuditEventType.RUN_FAILED, {"status": status.value})
            return await self._commit_and_build_result(run)

        await self._audit(
            run.id,
            AuditEventType.DECISION_VALIDATED,
            {
                "schema_valid": True,
                "request_type": decision_payload.request_type.value,
                "domain_template": decision_payload.domain_template.value,
                "risk_level": decision_payload.risk_level.value,
                "proposed_tool_names": [
                    tool.name for tool in decision_payload.proposed_tool_calls
                ],
            },
        )

        validation_result = self._validate_provider_decision(decision_payload)
        if not validation_result.is_valid:
            status = transition(status, WorkflowEventType.DECISION_INVALID)
            invalid_summary = validation_result.safe_summary or (
                "Access request failed provider validation."
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=invalid_summary,
                error_type="LLM_OUTPUT_VALIDATION_ERROR",
                error_message=invalid_summary,
            )
            await self._audit(
                run.id,
                AuditEventType.RUN_FAILED,
                {"status": status.value, "reason_codes": validation_result.reason_codes},
            )
            return await self._commit_and_build_result(run)

        missing_fields = _missing_access_fields(request)
        if missing_fields:
            status = transition(status, WorkflowEventType.DECISION_MISSING_INPUT)
            final_summary = (
                "Access request is missing required fields: "
                f"{', '.join(missing_fields)}."
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                risk_level=decision_payload.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=final_summary,
            )
            await self._audit(
                run.id,
                AuditEventType.USER_INPUT_REQUIRED,
                {"missing_fields": missing_fields, "approval_mode": request.approval_mode.value},
            )
            return await self._commit_and_build_result(run)

        access_fields = _validate_required_access_fields(request)
        if access_fields is None:
            status = transition(status, WorkflowEventType.DECISION_MISSING_INPUT)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Access request is missing required normalized fields.",
                error_type="ACCESS_REQUEST_VALIDATION_ERROR",
                error_message="Access request normalized fields were missing after validation.",
            )
            await self._audit(
                run.id,
                AuditEventType.USER_INPUT_REQUIRED,
                {"missing_fields": _missing_access_fields(request)},
            )
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.DECISION_VALID)
        status = transition(status, WorkflowEventType.TOOL_PLAN_CREATED)
        missing_tool_names = self._missing_access_tool_names()
        if missing_tool_names:
            status = transition(status, WorkflowEventType.TOOL_PLAN_INVALID)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Access request failed validation because an access tool is unavailable.",
                error_type="ACCESS_TOOL_PLAN_INVALID",
                error_message="Access tool plan validation failed safely.",
            )
            await self._audit(
                run.id,
                AuditEventType.RUN_FAILED,
                {
                    "status": status.value,
                    "reason_codes": ["ACCESS_TOOL_PLAN_INVALID"],
                    "missing_tool_names": missing_tool_names,
                },
            )
            return await self._commit_and_build_result(run)
        status = transition(status, WorkflowEventType.TOOL_PLAN_VALID)

        tool_outputs = await self._execute_read_tools(run.id, access_fields)
        employee_output = tool_outputs["get_employee_profile"]
        system_output = tool_outputs["get_system_info"]
        policy_output = tool_outputs["search_access_policy"]
        tickets_output = tool_outputs["get_existing_access_tickets"]

        if any(result.status is ToolCallStatus.FAILED for result in tool_outputs.values()):
            status = transition(status, WorkflowEventType.TOOL_EXECUTION_FAILED)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Access request failed because a read tool failed safely.",
                error_type="TOOL_EXECUTION_FAILED",
                error_message="Read tool execution failed.",
            )
            await self._audit(run.id, AuditEventType.RUN_FAILED, {"status": status.value})
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.READ_TOOLS_EXECUTED)
        manual_review_reason_codes = _manual_review_reason_codes(
            employee_output.output_payload,
            system_output.output_payload,
            tickets_output.output_payload,
        )
        if manual_review_reason_codes:
            status = transition(status, WorkflowEventType.POLICY_MANUAL_REVIEW)
            final_summary = (
                "Access request needs manual review because the employee or system "
                "could not be verified."
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                risk_level=_risk_from_policy_output(policy_output.output_payload),
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=final_summary,
            )
            await self._audit(
                run.id,
                AuditEventType.MANUAL_REVIEW_REQUIRED,
                {
                    "reason_codes": manual_review_reason_codes,
                    "approval_mode": request.approval_mode.value,
                },
            )
            return await self._commit_and_build_result(run)

        access_policy = AccessPolicyOutput.model_validate(policy_output.output_payload)
        if access_policy.forbidden:
            status = transition(status, WorkflowEventType.POLICY_REJECTED)
            final_summary = (
                "Access request rejected by policy: "
                f"{_policy_rejection_reason(access_policy.reason_codes)}."
            )
            await self._audit(
                run.id,
                AuditEventType.POLICY_CHECKED,
                {
                    "status": PolicyDecisionStatus.DENIED.value,
                    "risk_level": access_policy.risk_level.value,
                    "reason_codes": access_policy.reason_codes,
                    "approval_mode": request.approval_mode.value,
                },
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                risk_level=access_policy.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=final_summary,
            )
            await self._audit(
                run.id,
                AuditEventType.RUN_REJECTED,
                {"status": status.value, "reason_codes": access_policy.reason_codes},
            )
            return await self._commit_and_build_result(run)

        policy_decision = self._policy_evaluator(
            PolicyCheckRequest(
                tool_name=_ACCESS_ACTION_TOOL_NAME,
                tool_type=ToolType.STATE_CHANGING,
                risk_level=access_policy.risk_level,
                requires_approval_by_default=access_policy.requires_approval_by_default,
                approval_mode=request.approval_mode,
                context={
                    "request_type": RequestType.ACCESS_REQUEST.value,
                    "approval_mode": request.approval_mode.value,
                    "access_reason_codes": access_policy.reason_codes,
                },
            )
        )
        await self._audit(
            run.id,
            AuditEventType.POLICY_CHECKED,
            {
                "status": policy_decision.status.value,
                "risk_level": policy_decision.risk_level.value,
                "reason_codes": policy_decision.reasons + access_policy.reason_codes,
                "approval_mode": request.approval_mode.value,
            },
        )

        if policy_decision.status is PolicyDecisionStatus.ALLOWED:
            status = transition(status, WorkflowEventType.POLICY_ALLOWED_ACTION)
            action_tool_call = await self._execute_action_tool(
                run.id,
                request,
                access_fields,
                requires_approval=False,
            )
            if action_tool_call.status is ToolCallStatus.FAILED:
                status = transition(status, WorkflowEventType.ACTION_FAILED)
                run = await self._repo.update_agent_run_result(
                    run.id,
                    status=status,
                    request_type=RequestType.ACCESS_REQUEST,
                    domain_template=DomainTemplate.ACCESS,
                    risk_level=access_policy.risk_level,
                    requires_approval=False,
                    provider_name=self._provider_name,
                    model_name=self._model_name,
                    final_summary="Access request failed because the draft action failed safely.",
                    error_type="TOOL_EXECUTION_FAILED",
                    error_message="Draft tool execution failed safely.",
                )
                await self._audit(run.id, AuditEventType.RUN_FAILED, {"status": status.value})
                return await self._commit_and_build_result(run)

            status = transition(status, WorkflowEventType.ACTION_EXECUTED)
            draft_output = CreateAccessRequestDraftOutput.model_validate(
                action_tool_call.output_payload
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                risk_level=access_policy.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=draft_output.summary,
            )
            await self._audit(run.id, AuditEventType.RUN_COMPLETED, {"status": status.value})
            return await self._commit_and_build_result(run)

        if policy_decision.status is PolicyDecisionStatus.REQUIRES_APPROVAL:
            status = transition(status, WorkflowEventType.POLICY_REQUIRES_APPROVAL)
            approver_role = (
                access_policy.required_approver_role
                or policy_decision.required_approver_role
                or "manager"
            )
            final_summary = (
                f"Access request requires approval by {approver_role} before draft creation."
            )
            approval = await self._create_pending_action_approval(
                run.id,
                request,
                access_fields,
                access_policy.risk_level,
                approver_role,
                final_summary,
                policy_decision.reasons + access_policy.reason_codes,
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                risk_level=access_policy.risk_level,
                requires_approval=True,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=final_summary,
            )
            await self._audit(
                run.id,
                AuditEventType.APPROVAL_REQUESTED,
                {
                    "approval_id": str(approval.id),
                    "required_approver_role": approver_role,
                    "risk_level": access_policy.risk_level.value,
                    "approval_mode": request.approval_mode.value,
                },
            )
            return await self._commit_and_build_result(run, approval)

        if policy_decision.status is PolicyDecisionStatus.NEEDS_MANUAL_REVIEW:
            status = transition(status, WorkflowEventType.POLICY_MANUAL_REVIEW)
            final_summary = (
                "Access request needs manual review because policy requires manual review."
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                risk_level=policy_decision.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=final_summary,
            )
            await self._audit(
                run.id,
                AuditEventType.MANUAL_REVIEW_REQUIRED,
                {
                    "status": policy_decision.status.value,
                    "reason_codes": policy_decision.reasons + access_policy.reason_codes,
                    "approval_mode": request.approval_mode.value,
                },
            )
            return await self._commit_and_build_result(run)

        if policy_decision.status is PolicyDecisionStatus.DENIED:
            status = transition(status, WorkflowEventType.POLICY_REJECTED)
            final_summary = "Access request rejected by policy."
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.ACCESS_REQUEST,
                domain_template=DomainTemplate.ACCESS,
                risk_level=policy_decision.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=final_summary,
            )
            await self._audit(
                run.id,
                AuditEventType.RUN_REJECTED,
                {
                    "status": status.value,
                    "reason_codes": policy_decision.reasons + access_policy.reason_codes,
                },
            )
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.ACTION_FAILED)
        run = await self._repo.update_agent_run_result(
            run.id,
            status=status,
            request_type=RequestType.ACCESS_REQUEST,
            domain_template=DomainTemplate.ACCESS,
            risk_level=policy_decision.risk_level,
            requires_approval=False,
            provider_name=self._provider_name,
            model_name=self._model_name,
            final_summary="Access request failed because policy returned an unsupported status.",
            error_type="POLICY_STATUS_UNSUPPORTED",
            error_message="Unsupported policy status was handled safely.",
        )
        await self._audit(run.id, AuditEventType.RUN_FAILED, {"status": status.value})
        return await self._commit_and_build_result(run)

    async def resolve_access_approval(
        self, request: AccessApprovalResolutionRequest
    ) -> AccessWorkflowResult:
        run = await self._repo.get_agent_run(request.run_id)
        if run is None:
            raise KeyError(f"AgentRun {request.run_id} does not exist")
        if run.status is not AgentRunStatus.WAITING_FOR_APPROVAL:
            raise ValueError("Access approval can only be resolved for a waiting run")

        approval = await self._repo.get_approval(request.approval_id)
        if approval is None:
            raise KeyError(f"Approval {request.approval_id} does not exist")
        if approval.run_id != run.id:
            raise ValueError("Approval does not belong to the requested run")
        if approval.status is not ApprovalStatus.PENDING:
            raise ValueError("Approval is not pending")
        if request.status is ApprovalStatus.PENDING:
            raise ValueError("PENDING is not a valid approval decision status")

        decision = ApprovalDecision(
            status=request.status,
            decided_by=request.decided_by,
            decision_comment=request.decision_comment,
            decided_at=datetime.now(UTC),
        )
        approval = await self._repo.update_approval_decision(
            approval.id,
            status=decision.status,
            decided_by=decision.decided_by or request.decided_by,
            decision_comment=decision.decision_comment,
        )
        await self._audit(
            run.id,
            AuditEventType.APPROVAL_DECIDED,
            {
                "approval_id": str(approval.id),
                "status": approval.status.value,
                "decided_by": approval.decided_by or request.decided_by,
            },
        )

        action_tool_call = await self._find_waiting_action_tool_call(run.id, approval.id)
        if not is_approval_granted(decision):
            status = transition(run.status, WorkflowEventType.APPROVAL_REJECTED)
            if action_tool_call is not None:
                await self._repo.update_tool_call_result(
                    action_tool_call.id,
                    status=ToolCallStatus.REJECTED,
                    output_payload=None,
                    error_message="Approval was rejected or cancelled.",
                )
            final_summary = "Access request rejected by approval decision."
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                requires_approval=False,
                final_summary=final_summary,
            )
            await self._audit(run.id, AuditEventType.RUN_REJECTED, {"status": status.value})
            return await self._commit_and_build_result(run, approval)

        status = transition(run.status, WorkflowEventType.APPROVAL_APPROVED)
        if action_tool_call is None:
            status = transition(status, WorkflowEventType.ACTION_FAILED)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                requires_approval=False,
                final_summary="Access request failed because the approved action was not found.",
                error_type="APPROVED_ACTION_NOT_FOUND",
                error_message="Waiting action tool call was missing.",
            )
            await self._audit(run.id, AuditEventType.RUN_FAILED, {"status": status.value})
            return await self._commit_and_build_result(run, approval)

        action_tool_call = await self._execute_existing_tool_call(
            run.id,
            action_tool_call,
            execution_authorized=True,
            audit_payload={"approval_id": str(approval.id)},
        )

        if action_tool_call.status is ToolCallStatus.FAILED:
            status = transition(status, WorkflowEventType.ACTION_FAILED)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                requires_approval=False,
                final_summary="Access request failed because the approved action failed safely.",
                error_type="TOOL_EXECUTION_FAILED",
                error_message=action_tool_call.error_message,
            )
            await self._audit(run.id, AuditEventType.RUN_FAILED, {"status": status.value})
            return await self._commit_and_build_result(run, approval)

        status = transition(status, WorkflowEventType.ACTION_EXECUTED)
        draft_output = CreateAccessRequestDraftOutput.model_validate(
            action_tool_call.output_payload
        )
        run = await self._repo.update_agent_run_result(
            run.id,
            status=status,
            requires_approval=False,
            final_summary=draft_output.summary,
        )
        await self._audit(run.id, AuditEventType.RUN_COMPLETED, {"status": status.value})
        return await self._commit_and_build_result(run, approval)

    async def _persist_decision(
        self,
        run_id: UUID,
        provider_response: object,
    ) -> tuple[LLMDecisionPayload | None, bool]:
        response_payload = _model_dump_json_dict(provider_response)
        try:
            decision_payload = LLMDecisionPayload.model_validate(response_payload)
        except ValidationError:
            await self._repo.add_llm_decision(
                LLMDecisionCreate(
                    run_id=run_id,
                    validated_payload={},
                    schema_valid=False,
                    validation_errors=[{"message": "LLM output validation failed"}],
                    confidence=None,
                )
            )
            return None, False

        await self._repo.add_llm_decision(
            LLMDecisionCreate(
                run_id=run_id,
                schema_version=decision_payload.schema_version,
                validated_payload=decision_payload.model_dump(mode="json"),
                schema_valid=True,
                validation_errors=[],
                confidence=decision_payload.confidence,
            )
        )
        return decision_payload, True

    def _validate_provider_decision(
        self, decision_payload: LLMDecisionPayload
    ) -> _ProviderDecisionValidationResult:
        if decision_payload.request_type is not RequestType.ACCESS_REQUEST:
            return _ProviderDecisionValidationResult(
                is_valid=False,
                reason_codes=["REQUEST_TYPE_MISMATCH"],
                safe_summary=(
                    "Access request failed validation because provider chose a different "
                    "request type."
                ),
            )
        if decision_payload.domain_template is not DomainTemplate.ACCESS:
            return _ProviderDecisionValidationResult(
                is_valid=False,
                reason_codes=["DOMAIN_TEMPLATE_MISMATCH"],
                safe_summary=(
                    "Access request failed validation because provider chose a different "
                    "domain template."
                ),
            )
        unknown_tool_names = [
            tool.name
            for tool in decision_payload.proposed_tool_calls
            if tool.name not in _ACCESS_TOOL_NAMES or not self._registry.has(tool.name)
        ]
        if unknown_tool_names:
            return _ProviderDecisionValidationResult(
                is_valid=False,
                reason_codes=["UNKNOWN_TOOL_PROPOSAL"],
                safe_summary=(
                    "Access request failed validation because provider proposed an unknown tool."
                ),
            )
        return _ProviderDecisionValidationResult(is_valid=True, reason_codes=[])

    def _missing_access_tool_names(self) -> list[str]:
        return sorted(
            tool_name for tool_name in _ACCESS_TOOL_NAMES if not self._registry.has(tool_name)
        )

    async def _execute_read_tools(
        self,
        run_id: UUID,
        access_fields: _AccessRequestFields,
    ) -> dict[str, ToolCallRead]:
        payloads = {
            "get_employee_profile": {"employee_id": access_fields.employee_id},
            "get_system_info": {"system_id": access_fields.system_id},
            "search_access_policy": {
                "employee_id": access_fields.employee_id,
                "system_id": access_fields.system_id,
                "access_level": access_fields.access_level.value,
                "duration_days": access_fields.duration_days,
            },
            "get_existing_access_tickets": {
                "employee_id": access_fields.employee_id,
                "system_id": access_fields.system_id,
                "access_level": access_fields.access_level.value,
            },
        }
        results: dict[str, ToolCallRead] = {}
        for tool_name in _ACCESS_READ_TOOL_NAMES:
            results[tool_name] = await self._execute_and_persist_tool(
                run_id,
                tool_name,
                payloads[tool_name],
                execution_authorized=False,
                requires_approval=False,
            )
        return results

    async def _execute_action_tool(
        self,
        run_id: UUID,
        request: AccessWorkflowRequest,
        access_fields: _AccessRequestFields,
        *,
        requires_approval: bool,
    ) -> ToolCallRead:
        action_tool_call = await self._execute_and_persist_tool(
            run_id,
            _ACCESS_ACTION_TOOL_NAME,
            self._action_input_payload(run_id, request, access_fields),
            execution_authorized=True,
            requires_approval=requires_approval,
        )
        return action_tool_call

    async def _execute_and_persist_tool(
        self,
        run_id: UUID,
        tool_name: str,
        input_payload: dict[str, object],
        *,
        execution_authorized: bool,
        requires_approval: bool,
    ) -> ToolCallRead:
        try:
            definition = self._registry.get(tool_name)
        except UnknownToolError:
            tool_call = await self._repo.add_tool_call(
                ToolCallCreate(
                    run_id=run_id,
                    tool_name=tool_name,
                    tool_type=_expected_tool_type(tool_name),
                    status=ToolCallStatus.FAILED,
                    input_payload=input_payload,
                    output_payload=None,
                    error_message=_SAFE_TOOL_BOUNDARY_ERROR,
                    requires_approval=requires_approval,
                )
            )
            await self._audit(
                run_id,
                AuditEventType.TOOL_EXECUTED,
                {"tool_name": tool_name, "status": tool_call.status.value},
            )
            return tool_call

        tool_call = await self._repo.add_tool_call(
            ToolCallCreate(
                run_id=run_id,
                tool_name=tool_name,
                tool_type=definition.tool_type,
                status=ToolCallStatus.EXECUTING,
                input_payload=input_payload,
                requires_approval=requires_approval,
            )
        )
        tool_result = await self._execute_tool_boundary(
            tool_name,
            input_payload,
            execution_authorized=execution_authorized,
        )
        tool_call = await self._repo.update_tool_call_result(
            tool_call.id,
            status=tool_result.status,
            output_payload=tool_result.output_payload,
            error_message=tool_result.error_message,
        )
        await self._audit(
            run_id,
            AuditEventType.TOOL_EXECUTED,
            {"tool_name": tool_name, "status": tool_call.status.value},
        )
        return tool_call

    async def _execute_existing_tool_call(
        self,
        run_id: UUID,
        tool_call: ToolCallRead,
        *,
        execution_authorized: bool,
        audit_payload: dict[str, object] | None = None,
    ) -> ToolCallRead:
        await self._repo.update_tool_call_result(
            tool_call.id,
            status=ToolCallStatus.EXECUTING,
            output_payload=None,
            error_message=None,
        )
        tool_result = await self._execute_tool_boundary(
            tool_call.tool_name,
            tool_call.input_payload,
            execution_authorized=execution_authorized,
        )
        updated_tool_call = await self._repo.update_tool_call_result(
            tool_call.id,
            status=tool_result.status,
            output_payload=tool_result.output_payload,
            error_message=tool_result.error_message,
        )
        payload: dict[str, object] = {
            "tool_name": updated_tool_call.tool_name,
            "status": updated_tool_call.status.value,
        }
        if audit_payload is not None:
            payload.update(audit_payload)
        await self._audit(run_id, AuditEventType.TOOL_EXECUTED, payload)
        return updated_tool_call

    async def _execute_tool_boundary(
        self,
        tool_name: str,
        input_payload: dict[str, object],
        *,
        execution_authorized: bool,
    ) -> ToolExecutionResult:
        try:
            return await self._executor.execute(
                ToolExecutionRequest(
                    tool_name=tool_name,
                    input_payload=input_payload,
                    execution_authorized=execution_authorized,
                )
            )
        except _TOOL_BOUNDARY_EXCEPTIONS:
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_type=_expected_tool_type(tool_name),
                status=ToolCallStatus.FAILED,
                output_payload=None,
                error_message=_SAFE_TOOL_BOUNDARY_ERROR,
            )

    async def _create_pending_action_approval(
        self,
        run_id: UUID,
        request: AccessWorkflowRequest,
        access_fields: _AccessRequestFields,
        risk_level: RiskLevel,
        approver_role: str,
        summary: str,
        reason_codes: list[str],
    ) -> ApprovalRead:
        action_tool_call = await self._repo.add_tool_call(
            ToolCallCreate(
                run_id=run_id,
                tool_name=_ACCESS_ACTION_TOOL_NAME,
                tool_type=ToolType.STATE_CHANGING,
                status=ToolCallStatus.WAITING_FOR_APPROVAL,
                input_payload=self._action_input_payload(run_id, request, access_fields),
                output_payload=None,
                requires_approval=True,
            )
        )
        requirement = ApprovalRequirement(
            run_id=run_id,
            tool_call_id=action_tool_call.id,
            required_approver_role=approver_role,
            summary=summary,
            reason=", ".join(reason_codes) if reason_codes else None,
            risk_level=risk_level,
        )
        approval = await self._repo.add_approval(
            ApprovalCreate(
                run_id=run_id,
                tool_call_id=action_tool_call.id,
                status=ApprovalStatus.PENDING,
                required_approver_role=requirement.required_approver_role,
                summary=requirement.summary,
                reason=requirement.reason,
            )
        )
        await self._repo.update_tool_call_result(
            action_tool_call.id,
            status=ToolCallStatus.WAITING_FOR_APPROVAL,
            output_payload=None,
            error_message=None,
            approval_id=approval.id,
        )
        return approval

    async def _find_waiting_action_tool_call(
        self,
        run_id: UUID,
        approval_id: UUID,
    ) -> ToolCallRead | None:
        tool_calls = await self._repo.list_tool_calls(run_id)
        for tool_call in tool_calls:
            if (
                tool_call.tool_name == _ACCESS_ACTION_TOOL_NAME
                and tool_call.status is ToolCallStatus.WAITING_FOR_APPROVAL
                and tool_call.approval_id == approval_id
            ):
                return tool_call
        return None

    def _action_input_payload(
        self,
        run_id: UUID,
        request: AccessWorkflowRequest,
        access_fields: _AccessRequestFields,
    ) -> dict[str, object]:
        return {
            "run_id": str(run_id),
            "employee_id": access_fields.employee_id,
            "system_id": access_fields.system_id,
            "access_level": access_fields.access_level.value,
            "duration_days": access_fields.duration_days,
            "justification": request.justification,
        }

    async def _audit(
        self,
        run_id: UUID,
        event_type: AuditEventType,
        payload: dict[str, object],
    ) -> AuditEventRead:
        return await self._repo.add_audit_event(
            create_audit_event(run_id, event_type, payload=payload)
        )

    async def _commit_and_build_result(
        self,
        run: AgentRunRead,
        approval: ApprovalRead | None = None,
    ) -> AccessWorkflowResult:
        tool_calls = await self._repo.list_tool_calls(run.id)
        approvals = await self._repo.list_approvals(run.id)
        audit_events = await self._repo.list_audit_events(run.id)
        await self._session.commit()
        if approval is None and approvals:
            approval = approvals[-1]
        return AccessWorkflowResult(
            run=run,
            final_summary=run.final_summary,
            requires_approval=run.requires_approval,
            approval=approval,
            tool_calls=tool_calls,
            audit_events=audit_events,
        )


def _missing_access_fields(request: AccessWorkflowRequest) -> list[str]:
    missing_fields: list[str] = []
    if request.employee_id is None:
        missing_fields.append("employee_id")
    if request.system_id is None:
        missing_fields.append("system_id")
    if request.access_level is None:
        missing_fields.append("access_level")
    if request.duration_days is None:
        missing_fields.append("duration_days")
    return missing_fields


def _validate_required_access_fields(
    request: AccessWorkflowRequest,
) -> _AccessRequestFields | None:
    if (
        request.employee_id is None
        or request.system_id is None
        or request.access_level is None
        or request.duration_days is None
    ):
        return None
    return _AccessRequestFields(
        employee_id=request.employee_id,
        system_id=request.system_id,
        access_level=request.access_level,
        duration_days=request.duration_days,
    )


def _expected_tool_type(tool_name: str) -> ToolType:
    if tool_name == _ACCESS_ACTION_TOOL_NAME:
        return ToolType.STATE_CHANGING
    return ToolType.READ_ONLY


def _manual_review_reason_codes(
    employee_payload: dict[str, object] | None,
    system_payload: dict[str, object] | None,
    tickets_payload: dict[str, object] | None,
) -> list[str]:
    employee_output = GetEmployeeProfileOutput.model_validate(employee_payload)
    system_output = GetSystemInfoOutput.model_validate(system_payload)
    tickets_output = GetExistingAccessTicketsOutput.model_validate(tickets_payload)

    reason_codes: list[str] = []
    if not employee_output.found:
        reason_codes.extend(employee_output.reason_codes)
    if employee_output.employee is not None and employee_output.employee.status is EmployeeStatus.INACTIVE:
        reason_codes.append("EMPLOYEE_INACTIVE")
    if not system_output.found:
        reason_codes.extend(system_output.reason_codes)
    if tickets_output.has_open_duplicate:
        reason_codes.extend(tickets_output.reason_codes)
    return sorted(set(reason_codes))


def _risk_from_policy_output(policy_payload: dict[str, object] | None) -> RiskLevel | None:
    if policy_payload is None:
        return None
    return AccessPolicyOutput.model_validate(policy_payload).risk_level


def _policy_rejection_reason(reason_codes: list[str]) -> str:
    if "INTERN_ADMIN_FORBIDDEN" in reason_codes:
        return "intern admin access is forbidden"
    if "ACCESS_DURATION_EXCEEDS_MAX" in reason_codes:
        return "requested duration exceeds the allowed maximum"
    if "ACCESS_POLICY_NOT_FOUND" in reason_codes:
        return "no matching access policy rule was found"
    return "access policy denied the request"


def _model_dump_json_dict(model: object) -> dict[str, object]:
    if isinstance(model, BaseModel):
        dumped = model.model_dump(mode="json")
        return cast(dict[str, object], dumped)
    return cast(dict[str, object], model)
