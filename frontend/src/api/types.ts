import type { NormalizedApiError } from "./errors";

export type { NormalizedApiError };

export type KnownRunStatus =
  | "COMPLETED"
  | "WAITING_FOR_APPROVAL"
  | "NEEDS_USER_INPUT"
  | "NEEDS_MANUAL_REVIEW"
  | "REJECTED"
  | "FAILED_VALIDATION"
  | "FAILED_TOOL"
  | "FAILED_PROVIDER"
  | "FAILED";

export type RunStatus = KnownRunStatus | (string & {});

export type ApprovalStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "CANCELLED"
  | (string & {});

export type ApprovalMode =
  | "AUTO_APPROVE"
  | "HIGH_RISK_ONLY"
  | "ALWAYS_REQUIRE"
  | (string & {});

export type RequestType =
  | "ACCESS_REQUEST"
  | "PROCUREMENT_REQUEST"
  | "MAINTENANCE_REQUEST"
  | (string & {});

export type ModelSelectionResponse = {
  enabled: boolean;
  active_profile: string;
  available_profiles: string[];
  note: string;
};

export type CapabilitiesResponse = {
  workflows: string[];
  approval_modes: string[];
  provider_mode: string;
  model_selection: ModelSelectionResponse;
};

export type HealthResponse = {
  status: string;
};

export type AccessSubmitRequest = {
  user_id: string;
  request_text: string;
  employee_id?: string | null;
  system_id?: string | null;
  access_level?: "READ" | "WRITE" | "ADMIN" | null;
  duration_days?: number | null;
  justification?: string | null;
  approval_mode: ApprovalMode;
};

export type ProcurementSubmitRequest = {
  user_id: string;
  request_text: string;
  requester_id?: string | null;
  item_id?: string | null;
  item_name?: string | null;
  quantity?: number | null;
  estimated_total?: number | null;
  currency: string;
  cost_center?: string | null;
  justification?: string | null;
  preferred_vendor_id?: string | null;
  approval_mode: ApprovalMode;
};

export type MaintenanceSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type MaintenanceSubmitRequest = {
  user_id: string;
  request_text: string;
  requester_id?: string | null;
  asset_id?: string | null;
  asset_name?: string | null;
  issue_description?: string | null;
  location?: string | null;
  observed_severity?: MaintenanceSeverity | null;
  safety_concern?: boolean | null;
  approval_mode: ApprovalMode;
};

export type RunResponse = {
  id: string;
  user_id: string;
  approval_mode: string;
  request_type: RequestType;
  domain_template: string;
  status: RunStatus;
  risk_level: string | null;
  requires_approval: boolean;
  provider_name: string | null;
  model_name: string | null;
  final_summary: string | null;
  error_type: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type ToolCallResponse = {
  id: string;
  run_id: string;
  tool_name: string;
  tool_type: string;
  status: string;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown> | null;
  error_message: string | null;
  requires_approval: boolean;
  approval_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ApprovalResponse = {
  id: string;
  run_id: string;
  tool_call_id: string | null;
  status: ApprovalStatus;
  required_approver_role: string;
  summary: string;
  reason: string | null;
  decided_by: string | null;
  decision_comment: string | null;
  created_at: string;
  updated_at: string;
};

export type AuditEventResponse = {
  id: string;
  run_id: string;
  event_type: string;
  actor: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type WorkflowResultResponse = {
  run: RunResponse;
  final_summary: string | null;
  requires_approval: boolean;
  approval: ApprovalResponse | null;
  tool_calls: ToolCallResponse[];
  audit_events: AuditEventResponse[];
};

export type RunDetailResponse = WorkflowResultResponse;

export type ApprovalResolveRequest = {
  run_id: string;
  status: Exclude<ApprovalStatus, "PENDING">;
  decided_by: string;
  decision_comment?: string | null;
};
