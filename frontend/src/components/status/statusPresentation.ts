import type { RunStatus } from "../../api/types";
import type { Translator } from "../../i18n/messages";

export type Tone = "green" | "yellow" | "orange" | "red" | "blue" | "purple" | "gray";

export type StatusPresentation = {
  label: string;
  tone: Tone;
  description: string;
};

export function getRunStatusPresentation(status: RunStatus | string, t: Translator): StatusPresentation {
  switch (status) {
    case "COMPLETED":
      return {
        label: t("runStatus.completed.label"),
        tone: "green",
        description: t("runStatus.completed.description")
      };
    case "WAITING_FOR_APPROVAL":
      return {
        label: t("runStatus.waitingForApproval.label"),
        tone: "yellow",
        description: t("runStatus.waitingForApproval.description")
      };
    case "NEEDS_USER_INPUT":
      return {
        label: t("runStatus.needsUserInput.label"),
        tone: "yellow",
        description: t("runStatus.needsUserInput.description")
      };
    case "NEEDS_MANUAL_REVIEW":
      return {
        label: t("runStatus.needsManualReview.label"),
        tone: "orange",
        description: t("runStatus.needsManualReview.description")
      };
    case "REJECTED":
      return {
        label: t("runStatus.rejected.label"),
        tone: "red",
        description: t("runStatus.rejected.description")
      };
    case "FAILED_VALIDATION":
      return {
        label: t("runStatus.failedValidation.label"),
        tone: "red",
        description: t("runStatus.failedValidation.description")
      };
    case "FAILED_TOOL":
      return {
        label: t("runStatus.failedTool.label"),
        tone: "red",
        description: t("runStatus.failedTool.description")
      };
    case "FAILED_PROVIDER":
      return {
        label: t("runStatus.failedProvider.label"),
        tone: "red",
        description: t("runStatus.failedProvider.description")
      };
    case "FAILED":
      return {
        label: t("runStatus.failed.label"),
        tone: "red",
        description: t("runStatus.failed.description")
      };
    default:
      return {
        label: String(status || t("runStatus.unknown")),
        tone: "gray",
        description: t("runStatus.unknownDescription")
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
