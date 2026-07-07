import { apiRequest } from "./client";
import type { ApprovalResolveRequest, WorkflowResultResponse } from "./types";

export function resolveApproval(
  approvalId: string,
  request: ApprovalResolveRequest
): Promise<WorkflowResultResponse> {
  return apiRequest<WorkflowResultResponse>(`/approvals/${encodeURIComponent(approvalId)}/resolve`, {
    method: "POST",
    body: request
  });
}
