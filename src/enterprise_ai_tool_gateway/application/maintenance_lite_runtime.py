"""Application coordinator for the Stage 7 maintenance-lite workflow."""

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
    MaintenanceApprovalResolutionRequest,
    MaintenanceWorkflowRequest,
    MaintenanceWorkflowResult,
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
from enterprise_ai_tool_gateway.maintenance_lite import register_maintenance_tools
from enterprise_ai_tool_gateway.maintenance_lite.schemas import (
    AssetStatus,
    CheckMaintenancePolicyInput,
    ClassifyMaintenanceSeverityOutput,
    CreateWorkOrderDraftOutput,
    GetAssetInfoOutput,
    GetMaintenanceRequesterProfileOutput,
    GetOpenMaintenanceTicketsOutput,
    MaintenancePolicyOutput,
    MaintenanceRequesterStatus,
)
from enterprise_ai_tool_gateway.policy import (
    PolicyCheckRequest,
    PolicyDecision,
    evaluate_default_tool_policy,
)
from enterprise_ai_tool_gateway.tools import ToolExecutor, ToolRegistry
from enterprise_ai_tool_gateway.workflow import WorkflowEventType, transition

_MAINTENANCE_PRE_POLICY_READ_TOOL_NAMES = (
    "get_maintenance_requester_profile",
    "get_asset_info",
    "classify_maintenance_severity",
    "get_open_maintenance_tickets",
)
_MAINTENANCE_POLICY_TOOL_NAME = "check_maintenance_policy"
_MAINTENANCE_ACTION_TOOL_NAME = "create_work_order_draft"
_MAINTENANCE_TOOL_NAMES = {
    *_MAINTENANCE_PRE_POLICY_READ_TOOL_NAMES,
    _MAINTENANCE_POLICY_TOOL_NAME,
    _MAINTENANCE_ACTION_TOOL_NAME,
}
_PolicyEvaluator = Callable[[PolicyCheckRequest], PolicyDecision]


@dataclass(frozen=True)
class _MaintenanceRequestFields:
    requester_id: str
    asset_id: str | None
    asset_name: str | None
    issue_description: str
    location: str | None
    observed_severity: str | None
    safety_concern: bool


@dataclass(frozen=True)
class _ProviderDecisionValidationResult:
    is_valid: bool
    reason_codes: list[str]
    safe_summary: str | None = None


class MaintenanceLiteWorkflowRuntime:
    """Coordinate one maintenance-lite workflow transaction at a time."""

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
        self._registry = registry or register_maintenance_tools(ToolRegistry())
        self._executor = ToolExecutor(self._registry)
        self._policy_evaluator = policy_evaluator or evaluate_default_tool_policy
        self._provider_name = provider_name
        self._model_name = model_name

    async def submit_maintenance_request(
        self, request: MaintenanceWorkflowRequest
    ) -> MaintenanceWorkflowResult:
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
                "request_type": RequestType.MAINTENANCE_REQUEST.value,
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
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Maintenance request failed because the provider was unavailable.",
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
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Maintenance request failed validation because provider output was invalid.",
                error_type="LLM_OUTPUT_VALIDATION_ERROR",
                error_message="Provider output failed schema validation.",
                audit_payload={"status": status.value},
            )
            return await self._commit_and_build_result(run)

        await self._audit_decision_validated(run.id, decision_payload)
        validation_result = self._validate_provider_decision(decision_payload)
        if not validation_result.is_valid:
            invalid_summary = (
                validation_result.safe_summary or "Maintenance request failed validation."
            )
            status = transition(status, WorkflowEventType.DECISION_INVALID)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
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

        missing_fields = _missing_maintenance_fields(request)
        if missing_fields:
            status = transition(status, WorkflowEventType.DECISION_MISSING_INPUT)
            final_summary = (
                "Maintenance request is missing required fields: "
                f"{', '.join(missing_fields)}."
            )
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
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

        maintenance_fields = _validate_required_maintenance_fields(request)
        if maintenance_fields is None:
            status = transition(status, WorkflowEventType.DECISION_MISSING_INPUT)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Maintenance request is missing required normalized fields.",
                error_type="MAINTENANCE_REQUEST_VALIDATION_ERROR",
                error_message="Maintenance request normalized fields were missing after validation.",
            )
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.USER_INPUT_REQUIRED,
                {"missing_fields": _missing_maintenance_fields(request)},
            )
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.DECISION_VALID)
        status = transition(status, WorkflowEventType.TOOL_PLAN_CREATED)
        missing_tool_names = missing_registered_tool_names(_MAINTENANCE_TOOL_NAMES, self._registry)
        if missing_tool_names:
            status = transition(status, WorkflowEventType.TOOL_PLAN_INVALID)
            run = await create_safe_failed_result(
                self._repo,
                run_id=run.id,
                status=status,
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Maintenance request failed validation because a maintenance tool is unavailable.",
                error_type="MAINTENANCE_TOOL_PLAN_INVALID",
                error_message="Maintenance tool plan validation failed safely.",
                audit_payload={
                    "status": status.value,
                    "reason_codes": ["MAINTENANCE_TOOL_PLAN_INVALID"],
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
            _pre_policy_read_tool_plan(maintenance_fields),
            _expected_tool_type,
        )
        if any(result.status is ToolCallStatus.FAILED for result in tool_outputs.values()):
            status = transition(status, WorkflowEventType.TOOL_EXECUTION_FAILED)
            run = await create_safe_failed_result(
                self._repo,
                run_id=run.id,
                status=status,
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Maintenance request failed because a read tool failed safely.",
                error_type="TOOL_EXECUTION_FAILED",
                error_message="Read tool execution failed.",
                audit_payload={"status": status.value},
            )
            return await self._commit_and_build_result(run)

        severity_output = ClassifyMaintenanceSeverityOutput.model_validate(
            tool_outputs["classify_maintenance_severity"].output_payload
        )
        policy_call = await execute_tool_and_persist(
            self._repo,
            self._executor,
            self._registry,
            run.id,
            ToolPlanItem(
                _MAINTENANCE_POLICY_TOOL_NAME,
                _policy_input_payload(maintenance_fields, severity_output),
            ),
            _expected_tool_type,
        )
        tool_outputs[_MAINTENANCE_POLICY_TOOL_NAME] = policy_call
        if policy_call.status is ToolCallStatus.FAILED:
            status = transition(status, WorkflowEventType.TOOL_EXECUTION_FAILED)
            run = await create_safe_failed_result(
                self._repo,
                run_id=run.id,
                status=status,
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Maintenance request failed because policy check failed safely.",
                error_type="TOOL_EXECUTION_FAILED",
                error_message="Maintenance policy tool execution failed.",
                audit_payload={"status": status.value},
            )
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.READ_TOOLS_EXECUTED)
        return await self._handle_maintenance_policy(
            run,
            status,
            request,
            maintenance_fields,
            tool_outputs,
        )

    async def resolve_maintenance_approval(
        self, request: MaintenanceApprovalResolutionRequest
    ) -> MaintenanceWorkflowResult:
        run = await self._repo.get_agent_run(request.run_id)
        if run is None:
            raise KeyError(f"AgentRun {request.run_id} does not exist")
        if run.status is not AgentRunStatus.WAITING_FOR_APPROVAL:
            raise ValueError("Maintenance approval can only be resolved for a waiting run")

        approval = await self._repo.get_approval(request.approval_id)
        if approval is None:
            raise KeyError(f"Approval {request.approval_id} does not exist")
        if approval.run_id != run.id:
            raise ValueError("Approval does not belong to the requested run")
        if approval.status is not ApprovalStatus.PENDING:
            raise ValueError("Approval is not pending")

        decision, approval = await apply_approval_decision(
            self._repo,
            approval,
            status=request.status,
            decided_by=request.decided_by,
            decision_comment=request.decision_comment,
        )
        await persist_audit(
            self._repo,
            run.id,
            AuditEventType.APPROVAL_DECIDED,
            {
                "approval_id": str(approval.id),
                "status": approval.status.value,
                "decided_by": approval.decided_by or request.decided_by,
            },
        )

        action_tool_call = await find_waiting_action_tool_call(
            self._repo, run.id, approval.id, _MAINTENANCE_ACTION_TOOL_NAME
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
                final_summary="Maintenance request rejected by approval decision.",
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
                final_summary="Maintenance request failed because the approved action was not found.",
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
                final_summary="Maintenance request failed because the approved action failed safely.",
                error_type="TOOL_EXECUTION_FAILED",
                error_message=action_tool_call.error_message,
            )
            await persist_audit(self._repo, run.id, AuditEventType.RUN_FAILED, {"status": status.value})
            return await self._commit_and_build_result(run, approval)

        status = transition(status, WorkflowEventType.ACTION_EXECUTED)
        draft_output = CreateWorkOrderDraftOutput.model_validate(action_tool_call.output_payload)
        run = await self._repo.update_agent_run_result(
            run.id,
            status=status,
            requires_approval=False,
            final_summary=_draft_final_summary(draft_output),
        )
        await persist_audit(self._repo, run.id, AuditEventType.RUN_COMPLETED, {"status": status.value})
        return await self._commit_and_build_result(run, approval)

    async def _handle_maintenance_policy(
        self,
        run: AgentRunRead,
        status: AgentRunStatus,
        request: MaintenanceWorkflowRequest,
        maintenance_fields: _MaintenanceRequestFields,
        tool_outputs: dict[str, ToolCallRead],
    ) -> MaintenanceWorkflowResult:
        requester_output = GetMaintenanceRequesterProfileOutput.model_validate(
            tool_outputs["get_maintenance_requester_profile"].output_payload
        )
        asset_output = GetAssetInfoOutput.model_validate(tool_outputs["get_asset_info"].output_payload)
        severity_output = ClassifyMaintenanceSeverityOutput.model_validate(
            tool_outputs["classify_maintenance_severity"].output_payload
        )
        duplicate_output = GetOpenMaintenanceTicketsOutput.model_validate(
            tool_outputs["get_open_maintenance_tickets"].output_payload
        )
        policy_output = MaintenancePolicyOutput.model_validate(
            tool_outputs["check_maintenance_policy"].output_payload
        )

        if policy_output.forbidden:
            return await self._reject_by_maintenance_policy(run, status, request, policy_output)

        manual_review_reason_codes = _manual_review_reason_codes(
            requester_output,
            asset_output,
            duplicate_output,
            policy_output,
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
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
                risk_level=policy_output.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Maintenance request needs manual review before draft creation.",
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
                tool_name=_MAINTENANCE_ACTION_TOOL_NAME,
                risk_level=policy_output.risk_level,
                requires_approval_by_default=policy_output.requires_approval_by_default,
                approval_mode=request.approval_mode,
                context={
                    "request_type": RequestType.MAINTENANCE_REQUEST.value,
                    "approval_mode": request.approval_mode.value,
                    "maintenance_reason_codes": policy_output.reason_codes,
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
            action_tool_call = await self._execute_maintenance_action(
                run.id,
                maintenance_fields,
                asset_output,
                severity_output,
                policy_decision.reasons + policy_output.reason_codes,
                requires_approval=False,
            )
            return await self._finalize_maintenance_action(
                run,
                status,
                action_tool_call,
                policy_output.risk_level,
            )

        if policy_decision.status is PolicyDecisionStatus.REQUIRES_APPROVAL:
            approver_role = (
                policy_output.required_approver_role
                or policy_decision.required_approver_role
                or "maintenance_supervisor"
            )
            final_summary = (
                f"Maintenance request requires approval by {approver_role} before draft creation."
            )
            approval = await create_pending_approval(
                self._repo,
                run_id=run.id,
                action_tool_name=_MAINTENANCE_ACTION_TOOL_NAME,
                action_input_payload=_action_input_payload(
                    run.id,
                    maintenance_fields,
                    asset_output,
                    severity_output,
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
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
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
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
                risk_level=policy_decision.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Maintenance request needs manual review because policy requires manual review.",
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
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
                risk_level=policy_decision.risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Maintenance request rejected by policy.",
            )
            await persist_audit(
                self._repo,
                run.id,
                AuditEventType.RUN_REJECTED,
                {"status": status.value, "reason_codes": policy_decision.reasons},
            )
            return await self._commit_and_build_result(run)

        raise AssertionError("Unsupported maintenance policy status")

    async def _reject_by_maintenance_policy(
        self,
        run: AgentRunRead,
        status: AgentRunStatus,
        request: MaintenanceWorkflowRequest,
        policy_output: MaintenancePolicyOutput,
    ) -> MaintenanceWorkflowResult:
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
            request_type=RequestType.MAINTENANCE_REQUEST,
            domain_template=DomainTemplate.MAINTENANCE_LITE,
            risk_level=policy_output.risk_level,
            requires_approval=False,
            provider_name=self._provider_name,
            model_name=self._model_name,
            final_summary=f"Maintenance request rejected by policy: {_rejection_reason(policy_output.reason_codes)}.",
        )
        await persist_audit(
            self._repo,
            run.id,
            AuditEventType.RUN_REJECTED,
            {"status": status.value, "reason_codes": policy_output.reason_codes},
        )
        return await self._commit_and_build_result(run)

    async def _execute_maintenance_action(
        self,
        run_id: UUID,
        maintenance_fields: _MaintenanceRequestFields,
        asset_output: GetAssetInfoOutput,
        severity_output: ClassifyMaintenanceSeverityOutput,
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
                tool_name=_MAINTENANCE_ACTION_TOOL_NAME,
                input_payload=_action_input_payload(
                    run_id,
                    maintenance_fields,
                    asset_output,
                    severity_output,
                    reason_codes,
                ),
                execution_authorized=True,
                requires_approval=requires_approval,
            ),
            _expected_tool_type,
        )

    async def _finalize_maintenance_action(
        self,
        run: AgentRunRead,
        status: AgentRunStatus,
        action_tool_call: ToolCallRead,
        risk_level: RiskLevel,
    ) -> MaintenanceWorkflowResult:
        if action_tool_call.status is ToolCallStatus.FAILED:
            status = transition(status, WorkflowEventType.ACTION_FAILED)
            run = await self._repo.update_agent_run_result(
                run.id,
                status=status,
                request_type=RequestType.MAINTENANCE_REQUEST,
                domain_template=DomainTemplate.MAINTENANCE_LITE,
                risk_level=risk_level,
                requires_approval=False,
                provider_name=self._provider_name,
                model_name=self._model_name,
                final_summary="Maintenance request failed because the draft action failed safely.",
                error_type="TOOL_EXECUTION_FAILED",
                error_message=action_tool_call.error_message or SAFE_TOOL_BOUNDARY_ERROR,
            )
            await persist_audit(self._repo, run.id, AuditEventType.RUN_FAILED, {"status": status.value})
            return await self._commit_and_build_result(run)

        status = transition(status, WorkflowEventType.ACTION_EXECUTED)
        draft_output = CreateWorkOrderDraftOutput.model_validate(action_tool_call.output_payload)
        run = await self._repo.update_agent_run_result(
            run.id,
            status=status,
            request_type=RequestType.MAINTENANCE_REQUEST,
            domain_template=DomainTemplate.MAINTENANCE_LITE,
            risk_level=risk_level,
            requires_approval=False,
            provider_name=self._provider_name,
            model_name=self._model_name,
            final_summary=_draft_final_summary(draft_output),
        )
        await persist_audit(self._repo, run.id, AuditEventType.RUN_COMPLETED, {"status": status.value})
        return await self._commit_and_build_result(run)

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
        if decision_payload.request_type is not RequestType.MAINTENANCE_REQUEST:
            return _ProviderDecisionValidationResult(
                is_valid=False,
                reason_codes=["REQUEST_TYPE_MISMATCH"],
                safe_summary=(
                    "Maintenance request failed validation because provider chose a different "
                    "request type."
                ),
            )
        if decision_payload.domain_template is not DomainTemplate.MAINTENANCE_LITE:
            return _ProviderDecisionValidationResult(
                is_valid=False,
                reason_codes=["DOMAIN_TEMPLATE_MISMATCH"],
                safe_summary=(
                    "Maintenance request failed validation because provider chose a different "
                    "domain template."
                ),
            )
        unknown_tool_names = validate_allowed_tool_names(
            decision_payload, _MAINTENANCE_TOOL_NAMES, self._registry
        )
        if unknown_tool_names:
            return _ProviderDecisionValidationResult(
                is_valid=False,
                reason_codes=["UNKNOWN_TOOL_PROPOSAL"],
                safe_summary=(
                    "Maintenance request failed validation because provider proposed an "
                    "unknown tool."
                ),
            )
        return _ProviderDecisionValidationResult(is_valid=True, reason_codes=[])

    async def _commit_and_build_result(
        self,
        run: AgentRunRead,
        approval: ApprovalRead | None = None,
    ) -> MaintenanceWorkflowResult:
        records = await collect_runtime_records(self._repo, run, approval)
        await self._session.commit()
        return MaintenanceWorkflowResult(
            run=run,
            final_summary=run.final_summary,
            requires_approval=run.requires_approval,
            approval=records.approval,
            tool_calls=records.tool_calls,
            audit_events=records.audit_events,
        )


def _missing_maintenance_fields(request: MaintenanceWorkflowRequest) -> list[str]:
    return find_missing_fields(
        request.model_dump(mode="python"),
        ["requester_id", ("asset_id", "asset_name"), "issue_description"],
    )


def _validate_required_maintenance_fields(
    request: MaintenanceWorkflowRequest,
) -> _MaintenanceRequestFields | None:
    if (
        request.requester_id is None
        or (request.asset_id is None and request.asset_name is None)
        or request.issue_description is None
    ):
        return None
    return _MaintenanceRequestFields(
        requester_id=request.requester_id,
        asset_id=request.asset_id,
        asset_name=request.asset_name,
        issue_description=request.issue_description,
        location=request.location,
        observed_severity=request.observed_severity,
        safety_concern=bool(request.safety_concern),
    )


def _pre_policy_read_tool_plan(
    maintenance_fields: _MaintenanceRequestFields,
) -> tuple[ToolPlanItem, ...]:
    return (
        ToolPlanItem(
            "get_maintenance_requester_profile",
            {"requester_id": maintenance_fields.requester_id},
        ),
        ToolPlanItem(
            "get_asset_info",
            {
                "asset_id": maintenance_fields.asset_id,
                "asset_name": maintenance_fields.asset_name,
            },
        ),
        ToolPlanItem(
            "classify_maintenance_severity",
            {
                "issue_description": maintenance_fields.issue_description,
                "observed_severity": maintenance_fields.observed_severity,
                "safety_concern": maintenance_fields.safety_concern,
            },
        ),
        ToolPlanItem(
            "get_open_maintenance_tickets",
            {
                "asset_id": maintenance_fields.asset_id,
                "asset_name": maintenance_fields.asset_name,
            },
        ),
    )


def _policy_input_payload(
    maintenance_fields: _MaintenanceRequestFields,
    severity_output: ClassifyMaintenanceSeverityOutput,
) -> dict[str, object]:
    return CheckMaintenancePolicyInput(
        requester_id=maintenance_fields.requester_id,
        asset_id=maintenance_fields.asset_id,
        asset_name=maintenance_fields.asset_name,
        issue_description=maintenance_fields.issue_description,
        severity=severity_output.severity,
        safety_concern=maintenance_fields.safety_concern,
    ).model_dump(mode="json")


def _action_input_payload(
    run_id: UUID,
    maintenance_fields: _MaintenanceRequestFields,
    asset_output: GetAssetInfoOutput,
    severity_output: ClassifyMaintenanceSeverityOutput,
    reason_codes: list[str],
) -> dict[str, object]:
    asset_id = maintenance_fields.asset_id
    asset_name = maintenance_fields.asset_name
    location = maintenance_fields.location
    if asset_output.asset is not None:
        asset_id = asset_output.asset.asset_id
        asset_name = asset_output.asset.asset_name
        location = location or asset_output.asset.location
    return {
        "run_id": str(run_id),
        "requester_id": maintenance_fields.requester_id,
        "asset_id": asset_id or "unknown-asset",
        "asset_name": asset_name or "Unknown asset",
        "severity": severity_output.severity.value,
        "location": location,
        "issue_description": maintenance_fields.issue_description,
        "safety_concern": maintenance_fields.safety_concern,
        "reason_codes": reason_codes,
    }


def _draft_final_summary(draft_output: CreateWorkOrderDraftOutput) -> str:
    return (
        "Maintenance work order draft created for "
        f"{draft_output.asset_name} with {draft_output.severity.value} severity."
    )


def _manual_review_reason_codes(
    requester_output: GetMaintenanceRequesterProfileOutput,
    asset_output: GetAssetInfoOutput,
    duplicate_output: GetOpenMaintenanceTicketsOutput,
    policy_output: MaintenancePolicyOutput,
) -> list[str]:
    reason_codes: list[str] = []
    if not requester_output.found:
        reason_codes.extend(requester_output.reason_codes)
    if requester_output.requester is not None:
        if requester_output.requester.status is MaintenanceRequesterStatus.INACTIVE:
            reason_codes.append("MAINTENANCE_REQUESTER_INACTIVE")
    if not asset_output.found:
        reason_codes.extend(asset_output.reason_codes)
    if asset_output.asset is not None and asset_output.asset.status in {
        AssetStatus.INACTIVE,
        AssetStatus.DECOMMISSIONED,
    }:
        reason_codes.extend(asset_output.reason_codes)
    if duplicate_output.has_open_duplicate:
        reason_codes.extend(duplicate_output.reason_codes)
    if policy_output.manual_review:
        reason_codes.extend(policy_output.reason_codes)
    return sorted(set(reason_codes))


def _rejection_reason(reason_codes: list[str]) -> str:
    if "FORBIDDEN_MAINTENANCE_REQUEST" in reason_codes:
        return "forbidden unsafe instruction"
    return "maintenance policy denied the request"


def _expected_tool_type(tool_name: str) -> ToolType:
    if tool_name == _MAINTENANCE_ACTION_TOOL_NAME:
        return ToolType.STATE_CHANGING
    return ToolType.READ_ONLY
