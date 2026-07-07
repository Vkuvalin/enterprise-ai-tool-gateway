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

export type WorkflowKey = "access" | "procurement" | "maintenance";

export type WorkflowDefinition = {
  key: WorkflowKey;
  requestType: Extract<RequestType, "ACCESS_REQUEST" | "PROCUREMENT_REQUEST" | "MAINTENANCE_REQUEST">;
  title: string;
  route: string;
  endpoint: string;
  description: string;
  safetyNotes: string[];
  submit: (
    payload: AccessSubmitRequest | ProcurementSubmitRequest | MaintenanceSubmitRequest
  ) => Promise<WorkflowResultResponse>;
};

export const workflowRegistry: WorkflowDefinition[] = [
  {
    key: "access",
    requestType: "ACCESS_REQUEST",
    title: "Access Request",
    route: "/workflows/access",
    endpoint: "POST /api/v1/access-requests",
    description: "Controlled access draft workflow with policy checks and approval gates.",
    safetyNotes: [
      "No real IAM integration.",
      "State-changing draft actions stay behind backend policy and approval checks.",
      "Provider and model selection are not exposed."
    ],
    submit: (payload) => submitAccessRequest(payload as AccessSubmitRequest)
  },
  {
    key: "procurement",
    requestType: "PROCUREMENT_REQUEST",
    title: "Procurement Request",
    route: "/workflows/procurement",
    endpoint: "POST /api/v1/procurement-requests",
    description: "Synthetic spend/vendor/budget-control demo that creates draft-only outcomes.",
    safetyNotes: [
      "No real ERP, 1C, tender, vendor, or purchase-order integration.",
      "Budget and vendor checks use deterministic synthetic demo data.",
      "Backend owns draft creation and audit persistence."
    ],
    submit: (payload) => submitProcurementRequest(payload as ProcurementSubmitRequest)
  },
  {
    key: "maintenance",
    requestType: "MAINTENANCE_REQUEST",
    title: "Maintenance Request",
    route: "/workflows/maintenance",
    endpoint: "POST /api/v1/maintenance-requests",
    description: "Synthetic maintenance-lite demo for asset/severity/safety-control decisions.",
    safetyNotes: [
      "No real CMMS, EAM, 1C:TOIR, or work-order integration.",
      "Safety/manual-review outcomes are controlled backend states.",
      "Draft work orders are synthetic demo outputs only."
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
