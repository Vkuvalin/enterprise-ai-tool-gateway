import { apiRequest } from "./client";
import type {
  ApprovalResponse,
  AuditEventResponse,
  RunDetailResponse,
  ToolCallResponse
} from "./types";

export function getRunDetail(runId: string): Promise<RunDetailResponse> {
  return apiRequest<RunDetailResponse>(`/runs/${encodePathSegment(runId)}`);
}

export function getRunToolCalls(runId: string): Promise<ToolCallResponse[]> {
  return apiRequest<ToolCallResponse[]>(`/runs/${encodePathSegment(runId)}/tool-calls`);
}

export function getRunApprovals(runId: string): Promise<ApprovalResponse[]> {
  return apiRequest<ApprovalResponse[]>(`/runs/${encodePathSegment(runId)}/approvals`);
}

export function getRunAuditEvents(runId: string): Promise<AuditEventResponse[]> {
  return apiRequest<AuditEventResponse[]>(`/runs/${encodePathSegment(runId)}/audit-events`);
}

function encodePathSegment(value: string): string {
  return encodeURIComponent(value);
}
