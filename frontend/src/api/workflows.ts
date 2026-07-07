import { apiRequest } from "./client";
import type {
  AccessSubmitRequest,
  MaintenanceSubmitRequest,
  ProcurementSubmitRequest,
  WorkflowResultResponse
} from "./types";

export function submitAccessRequest(
  request: AccessSubmitRequest
): Promise<WorkflowResultResponse> {
  return apiRequest<WorkflowResultResponse>("/access-requests", {
    method: "POST",
    body: request
  });
}

export function submitProcurementRequest(
  request: ProcurementSubmitRequest
): Promise<WorkflowResultResponse> {
  return apiRequest<WorkflowResultResponse>("/procurement-requests", {
    method: "POST",
    body: request
  });
}

export function submitMaintenanceRequest(
  request: MaintenanceSubmitRequest
): Promise<WorkflowResultResponse> {
  return apiRequest<WorkflowResultResponse>("/maintenance-requests", {
    method: "POST",
    body: request
  });
}
