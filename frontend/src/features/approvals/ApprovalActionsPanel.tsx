import { useEffect, useRef, useState } from "react";
import { resolveApproval } from "../../api/approvals";
import { toDisplayError } from "../../api/errors";
import type { ApprovalResponse, NormalizedApiError, WorkflowResultResponse } from "../../api/types";
import { ActionButton } from "../../components/forms/ActionButton";
import { ErrorState } from "../../components/feedback/ErrorState";
import { useLocale } from "../../i18n/LocaleProvider";

type ApprovalActionsPanelProps = {
  approval: ApprovalResponse;
  onResolved: (outcome: ApprovalResolveOutcome) => void;
};

export type ApprovalResolveOutcome = {
  approvalId: string;
  runId: string;
  result: WorkflowResultResponse;
};

export function ApprovalActionsPanel({ approval, onResolved }: ApprovalActionsPanelProps) {
  const { t } = useLocale();
  const [decidedBy, setDecidedBy] = useState("manager-001");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<"APPROVED" | "REJECTED" | "CANCELLED" | null>(null);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const activeApprovalIdRef = useRef<string | null>(approval.id);
  const requestIdRef = useRef(0);
  const isPending = approval.status === "PENDING";

  useEffect(() => {
    activeApprovalIdRef.current = approval.id;
    requestIdRef.current += 1;
    setDecidedBy("manager-001");
    setComment("");
    setBusy(null);
    setError(null);
    return () => {
      activeApprovalIdRef.current = null;
      requestIdRef.current += 1;
    };
  }, [approval.id]);

  async function submit(status: "APPROVED" | "REJECTED" | "CANCELLED") {
    const ownerApprovalId = approval.id;
    const ownerRunId = approval.run_id;
    const requestId = ++requestIdRef.current;
    setBusy(status);
    setError(null);
    try {
      const result = await resolveApproval(ownerApprovalId, {
        run_id: ownerRunId,
        status,
        decided_by: decidedBy,
        decision_comment: comment || null
      });
      onResolved({ approvalId: ownerApprovalId, runId: ownerRunId, result });
    } catch (nextError) {
      if (activeApprovalIdRef.current === ownerApprovalId && requestIdRef.current === requestId) {
        setError(toDisplayError(nextError));
      }
    } finally {
      if (activeApprovalIdRef.current === ownerApprovalId && requestIdRef.current === requestId) {
        setBusy(null);
      }
    }
  }

  if (!isPending) {
    return <p className="muted">{t("approvalActions.resolved")}</p>;
  }

  return (
    <div className="approval-actions">
      <label>
        {t("common.decidedBy")}
        <input value={decidedBy} onChange={(event) => setDecidedBy(event.target.value)} />
      </label>
      <label>
        {t("approvalActions.decisionComment")}
        <textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} />
      </label>
      {error ? <ErrorState error={error} /> : null}
      <div className="button-row">
        <ActionButton
          type="button"
          variant="success"
          onClick={() => void submit("APPROVED")}
          disabled={busy !== null}
        >
          {busy === "APPROVED" ? t("approvalActions.approving") : t("approvalActions.approve")}
        </ActionButton>
        <ActionButton
          type="button"
          variant="danger"
          onClick={() => void submit("REJECTED")}
          disabled={busy !== null}
        >
          {busy === "REJECTED" ? t("approvalActions.rejecting") : t("approvalActions.reject")}
        </ActionButton>
        <ActionButton
          type="button"
          onClick={() => void submit("CANCELLED")}
          disabled={busy !== null}
        >
          {busy === "CANCELLED" ? t("approvalActions.cancelling") : t("approvalActions.cancel")}
        </ActionButton>
      </div>
    </div>
  );
}
