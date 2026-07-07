import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getRunApprovals } from "../api/runs";
import { toDisplayError } from "../api/errors";
import type { ApprovalResponse, NormalizedApiError, WorkflowResultResponse } from "../api/types";
import { DataTable, type DataTableColumn } from "../components/data/DataTable";
import { InspectorPanel } from "../components/data/InspectorPanel";
import { JsonViewer } from "../components/data/JsonViewer";
import { ErrorState } from "../components/feedback/ErrorState";
import { EmptyState } from "../components/feedback/EmptyState";
import { LoadingState } from "../components/feedback/LoadingState";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { StatusChip } from "../components/status/StatusChip";
import { toneForApproval } from "../components/status/statusPresentation";
import { ApprovalActionsPanel } from "../features/approvals/ApprovalActionsPanel";
import { useKnownRuns } from "../state/knownRuns";

const columns: DataTableColumn<ApprovalResponse>[] = [
  { key: "status", header: "Status", render: (row) => <StatusChip label={row.status} tone={toneForApproval(row.status)} /> },
  { key: "run", header: "Run ID", render: (row) => <Link to={`/runs/${row.run_id}`}>{row.run_id}</Link> },
  { key: "role", header: "Approver Role", render: (row) => row.required_approver_role },
  { key: "summary", header: "Summary", render: (row) => row.summary }
];

export function SessionApprovalsPage() {
  const { knownRunIds } = useKnownRuns();
  const [approvals, setApprovals] = useState<ApprovalResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [resolvedResult, setResolvedResult] = useState<WorkflowResultResponse | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all(
      knownRunIds.map((runId) =>
        getRunApprovals(runId).catch(() => {
          return [] as ApprovalResponse[];
        })
      )
    )
      .then((responses) => {
        if (cancelled) {
          return;
        }
        const pending = responses.flat().filter((approval) => approval.status === "PENDING");
        setApprovals(pending);
        setSelectedId(pending[0]?.id ?? null);
      })
      .catch((nextError: unknown) => {
        if (!cancelled) {
          setError(toDisplayError(nextError));
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
  }, [knownRunIds, refreshToken]);

  const selected = approvals.find((approval) => approval.id === selectedId) ?? approvals[0] ?? null;

  function onResolved(result: WorkflowResultResponse) {
    setResolvedResult(result);
    setRefreshToken((value) => value + 1);
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Session Approvals"
        eyebrow="Local run index"
        description="This is not a global backend queue; it aggregates pending approvals only from locally known run IDs."
        actions={
          <ActionButton type="button" onClick={() => setRefreshToken((value) => value + 1)}>
            Refresh
          </ActionButton>
        }
      />
      {knownRunIds.length === 0 ? (
        <EmptyState title="No known runs" detail="Submit or open a run before using the session approval view." />
      ) : null}
      {loading ? <LoadingState label="Loading session approvals..." /> : null}
      {error ? <ErrorState error={error} /> : null}
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
            emptyLabel="No pending approvals in locally known runs."
          />
        </section>
        <InspectorPanel title="Decision Panel">
          {selected ? (
            <div className="stack">
              <div className="kv-grid">
                <span>Run ID</span>
                <code>{selected.run_id}</code>
                <span>Approval ID</span>
                <code>{selected.id}</code>
                <span>Status</span>
                <StatusChip label={selected.status} tone={toneForApproval(selected.status)} />
              </div>
              <ApprovalActionsPanel approval={selected} onResolved={onResolved} />
              {resolvedResult ? <JsonViewer value={resolvedResult} label="Latest resolve response" /> : null}
            </div>
          ) : (
            <p className="muted">Select a pending approval from the local session list.</p>
          )}
        </InspectorPanel>
      </div>
    </div>
  );
}
