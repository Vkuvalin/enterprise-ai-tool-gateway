import type { RunStatus } from "../../api/types";

export type Tone = "green" | "yellow" | "orange" | "red" | "blue" | "purple" | "gray";

export type StatusPresentation = {
  label: string;
  tone: Tone;
  description: string;
};

export function getRunStatusPresentation(status: RunStatus | string): StatusPresentation {
  switch (status) {
    case "COMPLETED":
      return {
        label: "Completed",
        tone: "green",
        description: "Controlled draft or final outcome created."
      };
    case "WAITING_FOR_APPROVAL":
      return {
        label: "Approval required",
        tone: "yellow",
        description: "Backend paused execution until a human decision is recorded."
      };
    case "NEEDS_USER_INPUT":
      return {
        label: "Needs input",
        tone: "yellow",
        description: "The request needs additional user input."
      };
    case "NEEDS_MANUAL_REVIEW":
      return {
        label: "Manual review",
        tone: "orange",
        description: "Backend returned a controlled manual-review outcome."
      };
    case "REJECTED":
      return {
        label: "Rejected",
        tone: "red",
        description: "Request was safely rejected without unsafe execution."
      };
    case "FAILED_VALIDATION":
      return {
        label: "Validation failed",
        tone: "red",
        description: "Backend validation blocked unsafe or unknown execution."
      };
    case "FAILED_TOOL":
      return {
        label: "Tool failed",
        tone: "red",
        description: "Tool execution failed inside controlled boundaries."
      };
    case "FAILED_PROVIDER":
      return {
        label: "Provider failed",
        tone: "red",
        description: "Provider failure was handled as a controlled backend outcome."
      };
    case "FAILED":
      return {
        label: "Failed",
        tone: "red",
        description: "Controlled failure with safe error display."
      };
    default:
      return {
        label: String(status || "Unknown"),
        tone: "gray",
        description: "Unknown status returned by the API."
      };
  }
}

export function toneForApproval(status: string): Tone {
  switch (status) {
    case "APPROVED":
      return "green";
    case "PENDING":
      return "yellow";
    case "REJECTED":
    case "CANCELLED":
      return "red";
    default:
      return "gray";
  }
}

export function toneForRisk(risk: string | null | undefined): Tone {
  switch ((risk ?? "").toLowerCase()) {
    case "low":
      return "green";
    case "medium":
      return "yellow";
    case "high":
      return "red";
    default:
      return "gray";
  }
}
