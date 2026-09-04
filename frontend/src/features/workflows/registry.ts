import {
  submitAccessRequest,
  submitMaintenanceRequest,
  submitProcurementRequest
} from "../../api/workflows";
import type {
  AccessSubmitRequest,
  MaintenanceSubmitRequest,
  ProcurementSubmitRequest,
  RequestType,
  WorkflowResultResponse
} from "../../api/types";
import type { MessageKey } from "../../i18n/messages";

export type WorkflowKey = "access" | "procurement" | "maintenance";

export type WorkflowDefinition = {
  key: WorkflowKey;
  requestType: Extract<RequestType, "ACCESS_REQUEST" | "PROCUREMENT_REQUEST" | "MAINTENANCE_REQUEST">;
  titleKey: MessageKey;
  route: string;
  endpoint: string;
  descriptionKey: MessageKey;
  safetyNoteKeys: MessageKey[];
  submit: (
    payload: AccessSubmitRequest | ProcurementSubmitRequest | MaintenanceSubmitRequest
  ) => Promise<WorkflowResultResponse>;
};

export const workflowRegistry: WorkflowDefinition[] = [
  {
    key: "access",
    requestType: "ACCESS_REQUEST",
    titleKey: "workflows.access.title",
    route: "/workflows/access",
    endpoint: "POST /api/v1/access-requests",
    descriptionKey: "workflows.access.description",
    safetyNoteKeys: [
      "workflows.access.safety.iam",
      "workflows.access.safety.policy",
      "workflows.access.safety.provider"
    ],
    submit: (payload) => submitAccessRequest(payload as AccessSubmitRequest)
  },
  {
    key: "procurement",
    requestType: "PROCUREMENT_REQUEST",
    titleKey: "workflows.procurement.title",
    route: "/workflows/procurement",
    endpoint: "POST /api/v1/procurement-requests",
    descriptionKey: "workflows.procurement.description",
    safetyNoteKeys: [
      "workflows.procurement.safety.integrations",
      "workflows.procurement.safety.demoData",
      "workflows.procurement.safety.backendOwnership"
    ],
    submit: (payload) => submitProcurementRequest(payload as ProcurementSubmitRequest)
  },
  {
    key: "maintenance",
    requestType: "MAINTENANCE_REQUEST",
    titleKey: "workflows.maintenance.title",
    route: "/workflows/maintenance",
    endpoint: "POST /api/v1/maintenance-requests",
    descriptionKey: "workflows.maintenance.description",
    safetyNoteKeys: [
      "workflows.maintenance.safety.integrations",
      "workflows.maintenance.safety.review",
      "workflows.maintenance.safety.draftOnly"
    ],
    submit: (payload) => submitMaintenanceRequest(payload as MaintenanceSubmitRequest)
  }
];

export function getWorkflowByKey(key: WorkflowKey): WorkflowDefinition {
  const workflow = workflowRegistry.find((item) => item.key === key);
  if (!workflow) {
    throw new Error(`Unknown workflow key: ${key}`);
  }
  return workflow;
}

export function isWorkflowAvailable(workflow: WorkflowDefinition, available: string[] | null): boolean {
  return available === null || available.includes(workflow.requestType);
}
