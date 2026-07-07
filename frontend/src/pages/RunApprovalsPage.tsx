import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getRunApprovals } from "../api/runs";
import { toDisplayError } from "../api/errors";
import type { ApprovalResponse, NormalizedApiError, WorkflowResultResponse } from "../api/types";
import { DataTable, type DataTableColumn } from "../components/data/DataTable";
import { InspectorPanel } from "../components/data/InspectorPanel";
import { JsonViewer } from "../components/data/JsonViewer";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Toast, useToast } from "../components/feedback/Toast";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { StatusChip } from "../components/status/StatusChip";
import { toneForApproval } from "../components/status/statusPresentation";
import { ApprovalActionsPanel } from "../features/approvals/ApprovalActionsPanel";
import { setSelectedRunId } from "../state/knownRuns";

const columns: DataTableColumn<ApprovalResponse>[] = [
  { key: "status", header: "Status", render: (row) => <StatusChip label={row.status} tone={toneForApproval(row.status)} /> },
  { key: "role", header: "Approver Role", render: (row) => row.required_approver_role },
  { key: "summary", header: "Summary", render: (row) => row.summary },
  { key: "created", header: "Created", render: (row) => <time>{row.created_at}</time> },
  { key: "decision", header: "Decision", render: (row) => row.decided_by ?? "pending" }
];

export function RunApprovalsPage() {
  const { runId = "" } = useParams();
  const [approvals, setApprovals] = useState<ApprovalResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [resolvedResult, setResolvedResult] = useState<WorkflowResultResponse | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const { toast, showToast } = useToast();

  useEffect(() => {
    let cancelled = false;
    const hadLoaded = hasLoaded;
    const manualRefresh = refreshToken > 0;
    setLoading(true);
    if (!hadLoaded) {
      setError(null);
    }
    getRunApprovals(runId)
      .then((response) => {
        if (!cancelled) {
          setApprovals(response);
          setSelectedId(response[0]?.id ?? null);
          setHasLoaded(true);
          setError(null);
          const confirmedRunId = response[0]?.run_id ?? runId;
          if (confirmedRunId) {
            setSelectedRunId(confirmedRunId);
          }
          if (manualRefresh) {
            showToast({ message: "Data refreshed", tone: "success" });
          }
        }
      })
      .catch((nextError: unknown) => {
        if (cancelled) {
          return;
        }
        const displayError = toDisplayError(nextError);
        if (hadLoaded) {
          showToast({ message: "Refresh failed", tone: "error" });
        } else {
          setError(displayError);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId, refreshToken, showToast]);

  const selected = approvals.find((approval) => approval.id === selectedId) ?? approvals[0] ?? null;
  const initialLoading = loading && !hasLoaded;

  function onResolved(result: WorkflowResultResponse) {
    setResolvedResult(result);
    setRefreshToken((value) => value + 1);
  }

  function refreshApprovals() {
    if (!loading) {
      setRefreshToken((value) => value + 1);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Run Approvals"
        eyebrow="Run-scoped view"
        description="Approvals are loaded for the selected run only."
        actions={
          <ActionButton
            type="button"
            className="action-button--compact"
            onClick={refreshApprovals}
            aria-busy={loading && hasLoaded}
          >
            Refresh
          </ActionButton>
        }
      />
      {initialLoading ? <LoadingState label="Loading approvals..." /> : null}
      {error && !hasLoaded ? <ErrorState error={error} /> : null}
      <div className="content-with-inspector">
        <section className="panel">
          <DataTable
            columns={[
              ...columns,
              {
                key: "inspect",
                header: "Inspect",
                render: (row) => (
                  <button className="ghost-button" type="button" onClick={() => setSelectedId(row.id)}>
                    Select
                  </button>
                )
              }
            ]}
            rows={approvals}
            rowKey={(row) => row.id}
            emptyLabel="No approvals recorded for this run."
          />
        </section>
        <InspectorPanel title="Approval Details">
          {selected ? (
            <div className="stack">
              <div className="kv-grid">
                <span>Approval ID</span>
                <code>{selected.id}</code>
                <span>Status</span>
                <StatusChip label={selected.status} tone={toneForApproval(selected.status)} />
                <span>Reason</span>
                <span>{selected.reason ?? "not returned"}</span>
                <span>Decided by</span>
                <span>{selected.decided_by ?? "pending"}</span>
                <span>Comment</span>
                <span>{selected.decision_comment ?? "none"}</span>
              </div>
              <ApprovalActionsPanel approval={selected} onResolved={onResolved} />
              {resolvedResult ? <JsonViewer value={resolvedResult} label="Latest resolve response" /> : null}
            </div>
          ) : (
            <p className="muted">Select an approval to inspect or decide it.</p>
          )}
        </InspectorPanel>
      </div>
      <Toast toast={toast} />
    </div>
  );
}
