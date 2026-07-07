import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getRunDetail } from "../api/runs";
import { toDisplayError } from "../api/errors";
import type { NormalizedApiError, RunDetailResponse } from "../api/types";
import { DataTable, type DataTableColumn } from "../components/data/DataTable";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { RiskBadge } from "../components/status/RiskBadge";
import { StatusChip } from "../components/status/StatusChip";
import { getRunStatusPresentation } from "../components/status/statusPresentation";
import { addKnownRunId, useKnownRuns } from "../state/knownRuns";

type RunRow = RunDetailResponse["run"];

const columns: DataTableColumn<RunRow>[] = [
  { key: "id", header: "Run ID", render: (row) => <Link to={`/runs/${row.id}`}>{row.id}</Link> },
  { key: "request", header: "Request Type", render: (row) => <code>{row.request_type}</code> },
  {
    key: "status",
    header: "Status",
    render: (row) => {
      const status = getRunStatusPresentation(row.status);
      return <StatusChip label={status.label} tone={status.tone} title={status.description} />;
    }
  },
  { key: "risk", header: "Risk", render: (row) => <RiskBadge risk={row.risk_level} /> },
  { key: "updated", header: "Updated", render: (row) => <time>{row.updated_at}</time> },
  {
    key: "records",
    header: "Run Records",
    render: (row) => (
      <div className="run-links">
        <Link to={`/runs/${row.id}/approvals`}>Approvals</Link>
        <Link to={`/runs/${row.id}/tool-calls`}>Tool Calls</Link>
        <Link to={`/runs/${row.id}/audit`}>Audit Trail</Link>
      </div>
    )
  }
];

export function SessionRunsPage() {
  const navigate = useNavigate();
  const { knownRunIds } = useKnownRuns();
  const [runRows, setRunRows] = useState<RunRow[]>([]);
  const [manualRunId, setManualRunId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [openingRun, setOpeningRun] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all(
      knownRunIds.map((runId) =>
        getRunDetail(runId).catch(() => {
          return null;
        })
      )
    )
      .then((details) => {
        if (cancelled) {
          return;
        }
        setRunRows(details.filter((detail): detail is RunDetailResponse => detail !== null).map((detail) => detail.run));
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

  async function openRun(event: FormEvent) {
    event.preventDefault();
    const candidateRunId = manualRunId.trim();
    if (!candidateRunId) {
      return;
    }
    setOpeningRun(true);
    setError(null);
    try {
      const response = await getRunDetail(candidateRunId);
      addKnownRunId(response.run.id);
      setManualRunId("");
      navigate(`/runs/${response.run.id}`);
    } catch (nextError) {
      setError(toDisplayError(nextError));
    } finally {
      setOpeningRun(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Agent Runs"
        eyebrow="Local run index"
        description="This page shows locally known session run IDs only. Each row is refreshed from /api/v1/runs/{run_id}; it is not a global backend run list."
        actions={
          <div className="header-actions">
            <form className="inline-form inline-form--compact" onSubmit={openRun}>
              <input
                aria-label="Open run ID"
                placeholder="Paste run_id"
                value={manualRunId}
                onChange={(event) => setManualRunId(event.target.value)}
              />
              <ActionButton type="submit" variant="primary" className="action-button--compact" disabled={openingRun}>
                {openingRun ? "Opening..." : "Open Run"}
              </ActionButton>
            </form>
            <ActionButton
              type="button"
              className="action-button--compact"
              onClick={() => setRefreshToken((value) => value + 1)}
            >
              Refresh
            </ActionButton>
          </div>
        }
      />
      {knownRunIds.length === 0 ? (
        <EmptyState title="No known runs" detail="Submit a workflow or paste a backend-confirmed run ID to populate this local list." />
      ) : null}
      {loading ? <LoadingState label="Loading locally known runs..." /> : null}
      {error ? <ErrorState error={error} /> : null}
      <section className="panel">
        <div className="panel__header">
          <h2>Session-known runs</h2>
          <span className="muted">{knownRunIds.length} local run IDs</span>
        </div>
        <DataTable columns={columns} rows={runRows} rowKey={(row) => row.id} emptyLabel="No readable runs in the local index." />
      </section>
    </div>
  );
}
