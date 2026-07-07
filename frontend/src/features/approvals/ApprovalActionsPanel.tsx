import { useState } from "react";
import { resolveApproval } from "../../api/approvals";
import { toDisplayError } from "../../api/errors";
import type { ApprovalResponse, NormalizedApiError, WorkflowResultResponse } from "../../api/types";
import { ActionButton } from "../../components/forms/ActionButton";
import { ErrorState } from "../../components/feedback/ErrorState";

type ApprovalActionsPanelProps = {
  approval: ApprovalResponse;
  onResolved: (result: WorkflowResultResponse) => void;
};

export function ApprovalActionsPanel({ approval, onResolved }: ApprovalActionsPanelProps) {
  const [decidedBy, setDecidedBy] = useState("manager-001");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<"APPROVED" | "REJECTED" | "CANCELLED" | null>(null);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const isPending = approval.status === "PENDING";

  async function submit(status: "APPROVED" | "REJECTED" | "CANCELLED") {
    setBusy(status);
    setError(null);
    try {
      const result = await resolveApproval(approval.id, {
        run_id: approval.run_id,
        status,
        decided_by: decidedBy,
        decision_comment: comment || null
      });
      onResolved(result);
    } catch (nextError) {
      setError(toDisplayError(nextError));
    } finally {
      setBusy(null);
    }
  }

  if (!isPending) {
    return <p className="muted">This approval has already been resolved.</p>;
  }

  return (
    <div className="approval-actions">
      <label>
        Decided by
        <input value={decidedBy} onChange={(event) => setDecidedBy(event.target.value)} />
      </label>
      <label>
        Decision comment
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
          {busy === "APPROVED" ? "Approving..." : "Approve"}
        </ActionButton>
        <ActionButton
          type="button"
          variant="danger"
          onClick={() => void submit("REJECTED")}
          disabled={busy !== null}
        >
          {busy === "REJECTED" ? "Rejecting..." : "Reject"}
        </ActionButton>
        <ActionButton
          type="button"
          onClick={() => void submit("CANCELLED")}
          disabled={busy !== null}
        >
          {busy === "CANCELLED" ? "Cancelling..." : "Cancel"}
        </ActionButton>
      </div>
    </div>
  );
}
