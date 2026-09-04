import type { Translator } from "./messages";

export function getApprovalStatusLabel(value: string, t: Translator): string {
  switch (value) {
    case "PENDING":
      return t("approvalStatus.pending");
    case "APPROVED":
      return t("approvalStatus.approved");
    case "REJECTED":
      return t("approvalStatus.rejected");
    case "CANCELLED":
      return t("approvalStatus.cancelled");
    default:
      return value || t("common.unknown");
  }
}

export function getToolCallStatusLabel(value: string, t: Translator): string {
  switch (value) {
    case "SUCCEEDED":
      return t("toolStatus.succeeded");
    case "FAILED":
      return t("toolStatus.failed");
    default:
      return value || t("common.unknown");
  }
}

export function getRiskLabel(value: string | null | undefined, t: Translator): string {
  switch ((value ?? "").toLowerCase()) {
    case "low":
      return t("risk.low");
    case "medium":
      return t("risk.medium");
    case "high":
      return t("risk.high");
    case "critical":
      return t("risk.critical");
    default:
      return value || t("risk.unknown");
  }
}

export function getApprovalModeLabel(value: string, t: Translator): string {
  switch (value) {
    case "AUTO_APPROVE":
      return t("approvalMode.AUTO_APPROVE");
    case "HIGH_RISK_ONLY":
      return t("approvalMode.HIGH_RISK_ONLY");
    case "ALWAYS_REQUIRE":
      return t("approvalMode.ALWAYS_REQUIRE");
    default:
      return value;
  }
}

export function getAccessLevelLabel(value: string, t: Translator): string {
  switch (value) {
    case "READ":
      return t("accessLevel.READ");
    case "WRITE":
      return t("accessLevel.WRITE");
    case "ADMIN":
      return t("accessLevel.ADMIN");
    default:
      return value;
  }
}

export function getSeverityLabel(value: string, t: Translator): string {
  switch (value) {
    case "LOW":
      return t("severity.LOW");
    case "MEDIUM":
      return t("severity.MEDIUM");
    case "HIGH":
      return t("severity.HIGH");
    case "CRITICAL":
      return t("severity.CRITICAL");
    default:
      return value;
  }
}
