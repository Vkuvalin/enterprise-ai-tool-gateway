"""Application coordinator for the Stage 7 procurement request workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_ai_tool_gateway.approval import is_approval_granted
from enterprise_ai_tool_gateway.application.demo_workflow import (
    SAFE_TOOL_BOUNDARY_ERROR,
    ToolPlanItem,
    apply_approval_decision,
    build_policy_check_request,
    collect_runtime_records,
    create_pending_approval,
    create_safe_failed_result,
    execute_existing_tool_call,
    execute_read_tool_plan,
    execute_tool_and_persist,
    find_missing_fields,
    find_waiting_action_tool_call,
    map_policy_decision_to_runtime_step,
    missing_registered_tool_names,
    persist_audit,
    persist_llm_decision,
    validate_allowed_tool_names,
)
from enterprise_ai_tool_gateway.application.dtos import (
    ProcurementApprovalResolutionRequest,
    ProcurementWorkflowRequest,
    ProcurementWorkflowResult,
)
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
    ApprovalRead,
    LLMDecisionPayload,
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
from enterprise_ai_tool_gateway.procurement import register_procurement_tools
from enterprise_ai_tool_gateway.procurement.schemas import (
    CreatePurchaseRequestDraftOutput,
    GetCatalogItemOutput,
    GetExistingPurchaseRequestsOutput,
    GetProcurementRequesterProfileOutput,
    GetVendorInfoOutput,
    ProcurementPolicyOutput,
    RequesterStatus,
    VendorStatus,
)
from enterprise_ai_tool_gateway.tools import ToolExecutor, ToolRegistry
from enterprise_ai_tool_gateway.workflow import WorkflowEventType, transition

_PROCUREMENT_READ_TOOL_NAMES = (
    "get_procurement_requester_profile",
    "get_vendor_info",
    "get_catalog_item",
    "check_procurement_policy",
    "get_existing_purchase_requests",
)
_PROCUREMENT_ACTION_TOOL_NAME = "create_purchase_request_draft"
_PROCUREMENT_TOOL_NAMES = {*_PROCUREMENT_READ_TOOL_NAMES, _PROCUREMENT_ACTION_TOOL_NAME}
_PolicyEvaluator = Callable[[PolicyCheckRequest], PolicyDecision]


@dataclass(frozen=True)
class _ProcurementRequestFields:
    requester_id: str
    item_id: str | None
    item_name: str | None
    quantity: int
    estimated_total: float
    currency: str
    cost_center: str
    justification: str
    preferred_vendor_id: str | None


@dataclass(frozen=True)
class _ProviderDecisionValidationResult:
    is_valid: bool
    reason_codes: list[str]
    safe_summary: str | None = None


class ProcurementWorkflowRuntime:
    """Coordinate one procurement workflow transaction at a time."""

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
        self._registry = registry or register_procurement_tools(ToolRegistry())
        self._executor = ToolExecutor(self._registry)
        self._policy_evaluator = policy_evaluator or evaluate_default_tool_policy
        self._provider_name = provider_name
        self._model_name = model_name

    async def submit_procurement_request(
        self, request: ProcurementWorkflowRequest
    ) -> ProcurementWorkflowResult:
        run = await self._repo.create_agent_run(
            AgentRunCreate(
                user_id=request.user_id,
                request_text=request.request_text,
                approval_mode=request.approval_mode,
            )
        )
        await persist_audit(
            self._repo,
            run.id,
            AuditEventType.RUN_CREATED,
            {
                "status": AgentRunStatus.CREATED.value,
                "approval_mode": request.approval_mode.value,
                "request_type": RequestType.PROCUREMENT_REQUEST.value,
            },
        )

        status = transition(run.status, WorkflowEventType.START_CLASSIFICATION)
        await persist_audit(
            self._repo,
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
            run = await create_safe_failed_result(
                self._repo,
                run_id=run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Procurement request failed because the provider was unavailable.",
                error_type=exc.category.value,
                error_message="Provider call failed safely.",
                audit_payload={"status": status.value, "error_type": exc.category.value},
            )
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.PROVIDER_DECISION_RECEIVED)
        decision_payload, schema_valid = await persist_llm_decision(
            self._repo, run.id, provider_response
        )
        if not schema_valid or decision_payload is None:
            status = transition(status, WorkflowEventType.DECISION_INVALID)
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.DECISION_VALIDATED,
                {"schema_valid": False, "reason_codes": ["LLM_OUTPUT_VALIDATION_ERROR"]},
            )
            run = await create_safe_failed_result(
                self._repo,
                run_id=run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Procurement request failed validation because provider output was invalid.",
                error_type="LLM_OUTPUT_VALIDATION_ERROR",
                error_message="Provider output failed schema validation.",
                audit_payload={"status": status.value},
            )
            return await self._commit_and_build_result(run)

        await self._audit_decision_validated(run.id, decision_payload)
        validation_result = self._validate_provider_decision(decision_payload)
        if not validation_result.is_valid:
            invalid_summary = (
                validation_result.safe_summary or "Procurement request failed validation."
            )
            status = transition(status, WorkflowEventType.DECISION_INVALID)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=invalid_summary,
                error_type="LLM_OUTPUT_VALIDATION_ERROR",
                error_message=invalid_summary,
            )
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.RUN_FAILED,
                {"status": status.value, "reason_codes": validation_result.reason_codes},
            )
            return await self._commit_and_build_result(run)

        missing_fields = _missing_procurement_fields(request)
        if missing_fields:
            status = transition(status, WorkflowEventType.DECISION_MISSING_INPUT)
            final_summary = (
                "Procurement request is missing required fields: "
                f"{', '.join(missing_fields)}."
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                risk_level=decision_payload.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=final_summary,
            )
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.USER_INPUT_REQUIRED,
                {"missing_fields": missing_fields, "approval_mode": request.approval_mode.value},
            )
            return await self._commit_and_build_result(run)

        procurement_fields = _validate_required_procurement_fields(request)
        if procurement_fields is None:
            status = transition(status, WorkflowEventType.DECISION_MISSING_INPUT)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Procurement request is missing required normalized fields.",
                error_type="PROCUREMENT_REQUEST_VALIDATION_ERROR",
                error_message="Procurement request normalized fields were missing after validation.",
            )
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.USER_INPUT_REQUIRED,
                {"missing_fields": _missing_procurement_fields(request)},
            )
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.DECISION_VALID)
        status = transition(status, WorkflowEventType.TOOL_PLAN_CREATED)
        missing_tool_names = missing_registered_tool_names(_PROCUREMENT_TOOL_NAMES, self._registry)
        if missing_tool_names:
            status = transition(status, WorkflowEventType.TOOL_PLAN_INVALID)
            run = await create_safe_failed_result(
                self._repo,
                run_id=run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Procurement request failed validation because a procurement tool is unavailable.",
                error_type="PROCUREMENT_TOOL_PLAN_INVALID",
                error_message="Procurement tool plan validation failed safely.",
                audit_payload={
                    "status": status.value,
                    "reason_codes": ["PROCUREMENT_TOOL_PLAN_INVALID"],
                    "missing_tool_names": missing_tool_names,
                },
            )
            return await self._commit_and_build_result(run)
        status = transition(status, WorkflowEventType.TOOL_PLAN_VALID)

        tool_outputs = await execute_read_tool_plan(
            self._repo,
            self._executor,
            self._registry,
            run.id,
            _read_tool_plan(procurement_fields),
            _expected_tool_type,
        )
        if any(result.status is ToolCallStatus.FAILED for result in tool_outputs.values()):
            status = transition(status, WorkflowEventType.TOOL_EXECUTION_FAILED)
            run = await create_safe_failed_result(
                self._repo,
                run_id=run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Procurement request failed because a read tool failed safely.",
                error_type="TOOL_EXECUTION_FAILED",
                error_message="Read tool execution failed.",
                audit_payload={"status": status.value},
            )
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.READ_TOOLS_EXECUTED)
        return await self._handle_procurement_policy(
            run,
            status,
            request,
            procurement_fields,
            tool_outputs,
        )

    async def resolve_procurement_approval(
        self, request: ProcurementApprovalResolutionRequest
    ) -> ProcurementWorkflowResult:
        run = await self._repo.get_agent_run(request.run_id)
        if run is None:
            raise KeyError(f"AgentRun {request.run_id} does not exist")
        if run.status is not AgentRunStatus.WAITING_FOR_APPROVAL:
            raise ValueError("Procurement approval can only be resolved for a waiting run")

        approval = await self._repo.get_approval(request.approval_id)
        if approval is None:
            raise KeyError(f"Approval {request.approval_id} does not exist")
        if approval.run_id != run.id:
            raise ValueError("Approval does not belong to the requested run")
        if approval.status is not ApprovalStatus.PENDING:
            raise ValueError("Approval is not pending")

        decision, approval = await self._apply_approval_decision(run.id, approval, request)
        action_tool_call = await find_waiting_action_tool_call(
            self._repo, run.id, approval.id, _PROCUREMENT_ACTION_TOOL_NAME
        )
        if not is_approval_granted(decision):
            status = transition(run.status, WorkflowEventType.APPROVAL_REJECTED)
            if action_tool_call is not None:
                await self._repo.update_tool_call_result(
                    action_tool_call.id,
                    status=ToolCallStatus.REJECTED,
                    output_payload=None,
                    error_message="Approval was rejected or cancelled.",
                )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                requires_approval=False,
                final_summary="Procurement request rejected by approval decision.",
            )
            await persist_audit(self._repo, run.id, AuditEventType.RUN_REJECTED, {"status": status.value})
            return await self._commit_and_build_result(run, approval)

        status = transition(run.status, WorkflowEventType.APPROVAL_APPROVED)
        if action_tool_call is None:
            status = transition(status, WorkflowEventType.ACTION_FAILED)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                requires_approval=False,
                final_summary="Procurement request failed because the approved action was not found.",
                error_type="APPROVED_ACTION_NOT_FOUND",
                error_message="Waiting action tool call was missing.",
            )
            await persist_audit(self._repo, run.id, AuditEventType.RUN_FAILED, {"status": status.value})
            return await self._commit_and_build_result(run, approval)

        action_tool_call = await execute_existing_tool_call(
            self._repo,
            self._executor,
            run.id,
            action_tool_call,
            _expected_tool_type,
            execution_authorized=True,
            audit_payload={"approval_id": str(approval.id)},
        )
        if action_tool_call.status is ToolCallStatus.FAILED:
            status = transition(status, WorkflowEventType.ACTION_FAILED)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                requires_approval=False,
                final_summary="Procurement request failed because the approved action failed safely.",
                error_type="TOOL_EXECUTION_FAILED",
                error_message=action_tool_call.error_message,
            )
            await persist_audit(self._repo, run.id, AuditEventType.RUN_FAILED, {"status": status.value})
            return await self._commit_and_build_result(run, approval)

        status = transition(status, WorkflowEventType.ACTION_EXECUTED)
        draft_output = CreatePurchaseRequestDraftOutput.model_validate(
            action_tool_call.output_payload
        )
        run = await self._repo.update_agent_run_result(
            run.id,
            status=status,
            requires_approval=False,
            final_summary=draft_output.summary,
        )
        await persist_audit(self._repo, run.id, AuditEventType.RUN_COMPLETED, {"status": status.value})
        return await self._commit_and_build_result(run, approval)

    async def _handle_procurement_policy(
        self,
        run: AgentRunRead,
        status: AgentRunStatus,
        request: ProcurementWorkflowRequest,
        procurement_fields: _ProcurementRequestFields,
        tool_outputs: dict[str, ToolCallRead],
    ) -> ProcurementWorkflowResult:
        requester_output = GetProcurementRequesterProfileOutput.model_validate(
            tool_outputs["get_procurement_requester_profile"].output_payload
        )
        vendor_output = GetVendorInfoOutput.model_validate(
            tool_outputs["get_vendor_info"].output_payload
        )
        item_output = GetCatalogItemOutput.model_validate(
            tool_outputs["get_catalog_item"].output_payload
        )
        policy_output = ProcurementPolicyOutput.model_validate(
            tool_outputs["check_procurement_policy"].output_payload
        )
        duplicate_output = GetExistingPurchaseRequestsOutput.model_validate(
            tool_outputs["get_existing_purchase_requests"].output_payload
        )

        if policy_output.forbidden:
            return await self._reject_by_procurement_policy(run, status, request, policy_output)

        manual_review_reason_codes = _manual_review_reason_codes(
            requester_output,
            vendor_output,
            item_output,
            duplicate_output,
            policy_output,
            preferred_vendor_id=procurement_fields.preferred_vendor_id,
        )
        if manual_review_reason_codes:
            status = transition(status, WorkflowEventType.POLICY_MANUAL_REVIEW)
            reason_codes = sorted(set(manual_review_reason_codes + policy_output.reason_codes))
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.POLICY_CHECKED,
                {
                    "status": PolicyDecisionStatus.NEEDS_MANUAL_REVIEW.value,
                    "risk_level": policy_output.risk_level.value,
                    "reason_codes": reason_codes,
                    "approval_mode": request.approval_mode.value,
                },
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                risk_level=policy_output.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Procurement request needs manual review before draft creation.",
            )
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.MANUAL_REVIEW_REQUIRED,
                {"reason_codes": reason_codes, "approval_mode": request.approval_mode.value},
            )
            return await self._commit_and_build_result(run)

        policy_decision = self._policy_evaluator(
            build_policy_check_request(
                tool_name=_PROCUREMENT_ACTION_TOOL_NAME,
                risk_level=policy_output.risk_level,
                requires_approval_by_default=policy_output.requires_approval_by_default,
                approval_mode=request.approval_mode,
                context={
                    "request_type": RequestType.PROCUREMENT_REQUEST.value,
                    "approval_mode": request.approval_mode.value,
                    "procurement_reason_codes": policy_output.reason_codes,
                },
            )
        )
        await persist_audit(
            self._repo,
            run.id,
            AuditEventType.POLICY_CHECKED,
            {
                "status": policy_decision.status.value,
                "risk_level": policy_decision.risk_level.value,
                "reason_codes": policy_decision.reasons + policy_output.reason_codes,
                "approval_mode": request.approval_mode.value,
            },
        )
        policy_event = map_policy_decision_to_runtime_step(policy_decision)
        status = transition(status, policy_event)

        if policy_decision.status is PolicyDecisionStatus.ALLOWED:
            action_tool_call = await self._execute_procurement_action(
                run.id,
                procurement_fields,
                item_output,
                policy_decision.reasons + policy_output.reason_codes,
                requires_approval=False,
            )
            return await self._finalize_procurement_action(
                run,
                status,
                action_tool_call,
                policy_output.risk_level,
            )

        if policy_decision.status is PolicyDecisionStatus.REQUIRES_APPROVAL:
            approver_role = (
                policy_output.required_approver_role
                or policy_decision.required_approver_role
                or "procurement_manager"
            )
            final_summary = (
                f"Procurement request requires approval by {approver_role} before draft creation."
            )
            approval = await create_pending_approval(
                self._repo,
                run_id=run.id,
                action_tool_name=_PROCUREMENT_ACTION_TOOL_NAME,
                action_input_payload=_action_input_payload(
                    run.id,
                    procurement_fields,
                    item_output,
                    policy_decision.reasons + policy_output.reason_codes,
                ),
                risk_level=policy_output.risk_level,
                approver_role=approver_role,
                summary=final_summary,
                reason_codes=policy_decision.reasons + policy_output.reason_codes,
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                risk_level=policy_output.risk_level,
                requires_approval=True,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary=final_summary,
            )
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.APPROVAL_REQUESTED,
                {
                    "approval_id": str(approval.id),
                    "required_approver_role": approver_role,
                    "risk_level": policy_output.risk_level.value,
                    "approval_mode": request.approval_mode.value,
                },
            )
            return await self._commit_and_build_result(run, approval)

        if policy_decision.status is PolicyDecisionStatus.NEEDS_MANUAL_REVIEW:
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                risk_level=policy_decision.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Procurement request needs manual review because policy requires manual review.",
            )
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.MANUAL_REVIEW_REQUIRED,
                {
                    "status": policy_decision.status.value,
                    "reason_codes": policy_decision.reasons + policy_output.reason_codes,
                    "approval_mode": request.approval_mode.value,
                },
            )
            return await self._commit_and_build_result(run)

        if policy_decision.status is PolicyDecisionStatus.DENIED:
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                risk_level=policy_decision.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Procurement request rejected by policy.",
            )
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.RUN_REJECTED,
                {"status": status.value, "reason_codes": policy_decision.reasons},
            )
            return await self._commit_and_build_result(run)

        raise AssertionError("Unsupported procurement policy status")

    async def _reject_by_procurement_policy(
        self,
        run: AgentRunRead,
        status: AgentRunStatus,
        request: ProcurementWorkflowRequest,
        policy_output: ProcurementPolicyOutput,
    ) -> ProcurementWorkflowResult:
        status = transition(status, WorkflowEventType.POLICY_REJECTED)
        await persist_audit(
            self._repo,
            run.id,
            AuditEventType.POLICY_CHECKED,
            {
                "status": PolicyDecisionStatus.DENIED.value,
                "risk_level": policy_output.risk_level.value,
                "reason_codes": policy_output.reason_codes,
                "approval_mode": request.approval_mode.value,
            },
        )
        run = await self._repo.update_agent_run_result(
            run.id,
            status=status,
            request_type=RequestType.PROCUREMENT_REQUEST,
            domain_template=DomainTemplate.PROCUREMENT,
            risk_level=policy_output.risk_level,
            requires_approval=False,
            provider_name=self._provider_name,
            model_name=self._model_name,
            final_summary=f"Procurement request rejected by policy: {_rejection_reason(policy_output.reason_codes)}.",
        )
        await persist_audit(
            self._repo,
            run.id,
            AuditEventType.RUN_REJECTED,
            {"status": status.value, "reason_codes": policy_output.reason_codes},
        )
        return await self._commit_and_build_result(run)

    async def _execute_procurement_action(
        self,
        run_id: UUID,
        procurement_fields: _ProcurementRequestFields,
        item_output: GetCatalogItemOutput,
        reason_codes: list[str],
        *,
        requires_approval: bool,
    ) -> ToolCallRead:
        return await execute_tool_and_persist(
            self._repo,
            self._executor,
            self._registry,
            run_id,
            ToolPlanItem(
                tool_name=_PROCUREMENT_ACTION_TOOL_NAME,
                input_payload=_action_input_payload(
                    run_id, procurement_fields, item_output, reason_codes
                ),
                execution_authorized=True,
                requires_approval=requires_approval,
            ),
            _expected_tool_type,
        )

    async def _finalize_procurement_action(
        self,
        run: AgentRunRead,
        status: AgentRunStatus,
        action_tool_call: ToolCallRead,
        risk_level: RiskLevel,
    ) -> ProcurementWorkflowResult:
        if action_tool_call.status is ToolCallStatus.FAILED:
            status = transition(status, WorkflowEventType.ACTION_FAILED)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.PROCUREMENT_REQUEST,
                domain_template=DomainTemplate.PROCUREMENT,
                risk_level=risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Procurement request failed because the draft action failed safely.",
                error_type="TOOL_EXECUTION_FAILED",
                error_message=action_tool_call.error_message or SAFE_TOOL_BOUNDARY_ERROR,
            )
            await persist_audit(self._repo, run.id, AuditEventType.RUN_FAILED, {"status": status.value})
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.ACTION_EXECUTED)
        draft_output = CreatePurchaseRequestDraftOutput.model_validate(
            action_tool_call.output_payload
        )
        run = await self._repo.update_agent_run_result(
            run.id,
            status=status,
            request_type=RequestType.PROCUREMENT_REQUEST,
            domain_template=DomainTemplate.PROCUREMENT,
            risk_level=risk_level,
            requires_approval=False,
            provider_name=self._provider_name,
            model_name=self._model_name,
            final_summary=draft_output.summary,
        )
        await persist_audit(self._repo, run.id, AuditEventType.RUN_COMPLETED, {"status": status.value})
        return await self._commit_and_build_result(run)

    async def _apply_approval_decision(
        self,
        run_id: UUID,
        approval: ApprovalRead,
        request: ProcurementApprovalResolutionRequest,
    ):
        decision, approval = await apply_approval_decision(
            self._repo,
            approval,
            status=request.status,
            decided_by=request.decided_by,
            decision_comment=request.decision_comment,
        )
        await persist_audit(
            self._repo,
            run_id,
            AuditEventType.APPROVAL_DECIDED,
            {
                "approval_id": str(approval.id),
                "status": approval.status.value,
                "decided_by": approval.decided_by or request.decided_by,
            },
        )
        return decision, approval

    async def _audit_decision_validated(
        self,
        run_id: UUID,
        decision_payload: LLMDecisionPayload,
    ) -> None:
        await persist_audit(
            self._repo,
            run_id,
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

    def _validate_provider_decision(
        self, decision_payload: LLMDecisionPayload
    ) -> _ProviderDecisionValidationResult:
        if decision_payload.request_type is not RequestType.PROCUREMENT_REQUEST:
            return _ProviderDecisionValidationResult(
                is_valid=False,
                reason_codes=["REQUEST_TYPE_MISMATCH"],
                safe_summary=(
                    "Procurement request failed validation because provider chose a different "
                    "request type."
                ),
            )
        if decision_payload.domain_template is not DomainTemplate.PROCUREMENT:
            return _ProviderDecisionValidationResult(
                is_valid=False,
                reason_codes=["DOMAIN_TEMPLATE_MISMATCH"],
                safe_summary=(
                    "Procurement request failed validation because provider chose a different "
                    "domain template."
                ),
            )
        unknown_tool_names = validate_allowed_tool_names(
            decision_payload, _PROCUREMENT_TOOL_NAMES, self._registry
        )
        if unknown_tool_names:
            return _ProviderDecisionValidationResult(
                is_valid=False,
                reason_codes=["UNKNOWN_TOOL_PROPOSAL"],
                safe_summary=(
                    "Procurement request failed validation because provider proposed an "
                    "unknown tool."
                ),
            )
        return _ProviderDecisionValidationResult(is_valid=True, reason_codes=[])

    async def _commit_and_build_result(
        self,
        run: AgentRunRead,
        approval: ApprovalRead | None = None,
    ) -> ProcurementWorkflowResult:
        records = await collect_runtime_records(self._repo, run, approval)
        await self._session.commit()
        return ProcurementWorkflowResult(
            run=run,
            final_summary=run.final_summary,
            requires_approval=run.requires_approval,
            approval=records.approval,
            tool_calls=records.tool_calls,
            audit_events=records.audit_events,
        )


def _missing_procurement_fields(request: ProcurementWorkflowRequest) -> list[str]:
    return find_missing_fields(
        request.model_dump(mode="python"),
        [
            "requester_id",
            ("item_id", "item_name"),
            "quantity",
            "estimated_total",
            "cost_center",
            "justification",
        ],
    )


def _validate_required_procurement_fields(
    request: ProcurementWorkflowRequest,
) -> _ProcurementRequestFields | None:
    if (
        request.requester_id is None
        or (request.item_id is None and request.item_name is None)
        or request.quantity is None
        or request.estimated_total is None
        or request.cost_center is None
        or request.justification is None
    ):
        return None
    return _ProcurementRequestFields(
        requester_id=request.requester_id,
        item_id=request.item_id,
        item_name=request.item_name,
        quantity=request.quantity,
        estimated_total=request.estimated_total,
        currency=request.currency,
        cost_center=request.cost_center,
        justification=request.justification,
        preferred_vendor_id=request.preferred_vendor_id,
    )


def _read_tool_plan(procurement_fields: _ProcurementRequestFields) -> tuple[ToolPlanItem, ...]:
    return (
        ToolPlanItem(
            "get_procurement_requester_profile",
            {"requester_id": procurement_fields.requester_id},
        ),
        ToolPlanItem(
            "get_vendor_info",
            {"vendor_id": procurement_fields.preferred_vendor_id},
        ),
        ToolPlanItem(
            "get_catalog_item",
            {
                "item_id": procurement_fields.item_id,
                "item_name": procurement_fields.item_name,
            },
        ),
        ToolPlanItem(
            "check_procurement_policy",
            {
                "requester_id": procurement_fields.requester_id,
                "item_id": procurement_fields.item_id,
                "item_name": procurement_fields.item_name,
                "quantity": procurement_fields.quantity,
                "estimated_total": procurement_fields.estimated_total,
                "currency": procurement_fields.currency,
                "cost_center": procurement_fields.cost_center,
                "preferred_vendor_id": procurement_fields.preferred_vendor_id,
            },
        ),
        ToolPlanItem(
            "get_existing_purchase_requests",
            {
                "requester_id": procurement_fields.requester_id,
                "item_id": procurement_fields.item_id,
                "item_name": procurement_fields.item_name,
            },
        ),
    )


def _action_input_payload(
    run_id: UUID,
    procurement_fields: _ProcurementRequestFields,
    item_output: GetCatalogItemOutput,
    reason_codes: list[str],
) -> dict[str, object]:
    item_name = procurement_fields.item_name
    if item_output.item is not None:
        item_name = item_output.item.item_name
    if item_name is None:
        item_name = procurement_fields.item_id or "unknown item"

    return {
        "run_id": str(run_id),
        "requester_id": procurement_fields.requester_id,
        "item_id": procurement_fields.item_id,
        "item_name": item_name,
        "vendor_id": procurement_fields.preferred_vendor_id,
        "quantity": procurement_fields.quantity,
        "estimated_total": procurement_fields.estimated_total,
        "currency": procurement_fields.currency,
        "cost_center": procurement_fields.cost_center,
        "justification": procurement_fields.justification,
        "reason_codes": reason_codes,
    }


def _manual_review_reason_codes(
    requester_output: GetProcurementRequesterProfileOutput,
    vendor_output: GetVendorInfoOutput,
    item_output: GetCatalogItemOutput,
    duplicate_output: GetExistingPurchaseRequestsOutput,
    policy_output: ProcurementPolicyOutput,
    *,
    preferred_vendor_id: str | None,
) -> list[str]:
    reason_codes: list[str] = []
    if not requester_output.found:
        reason_codes.extend(requester_output.reason_codes)
    if requester_output.requester is not None:
        if requester_output.requester.status is RequesterStatus.INACTIVE:
            reason_codes.append("REQUESTER_INACTIVE")
        if not requester_output.requester.can_purchase:
            reason_codes.append("PURCHASE_PERMISSION_MISSING")
    if preferred_vendor_id is not None and not vendor_output.found:
        reason_codes.extend(vendor_output.reason_codes)
    if vendor_output.vendor is not None and vendor_output.vendor.status is VendorStatus.UNKNOWN:
        reason_codes.append("VENDOR_UNKNOWN")
    if not item_output.found:
        reason_codes.extend(item_output.reason_codes)
    if duplicate_output.has_open_duplicate:
        reason_codes.extend(duplicate_output.reason_codes)
    if policy_output.manual_review:
        reason_codes.extend(policy_output.reason_codes)
    return sorted(set(reason_codes))


def _rejection_reason(reason_codes: list[str]) -> str:
    if "RESTRICTED_ITEM_FORBIDDEN" in reason_codes:
        return "restricted item is forbidden"
    if "BLOCKED_VENDOR_FORBIDDEN" in reason_codes:
        return "blocked vendor is forbidden"
    return "procurement policy denied the request"


def _expected_tool_type(tool_name: str) -> ToolType:
    if tool_name == _PROCUREMENT_ACTION_TOOL_NAME:
        return ToolType.STATE_CHANGING
    return ToolType.READ_ONLY
