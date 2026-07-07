import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiBaseUrl } from "../api/client";
import { getRunApprovals, getRunDetail } from "../api/runs";
import { toDisplayError } from "../api/errors";
import type { ApprovalResponse, NormalizedApiError, RunDetailResponse } from "../api/types";
import { DataTable, type DataTableColumn } from "../components/data/DataTable";
import { MetricCard } from "../components/data/MetricCard";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { RiskBadge } from "../components/status/RiskBadge";
import { StatusChip } from "../components/status/StatusChip";
import { getRunStatusPresentation } from "../components/status/statusPresentation";
import { CapabilitiesPanel } from "../features/capabilities/CapabilitiesPanel";
import { useApiStatus } from "../features/capabilities/useApiStatus";
import { WorkflowCard } from "../features/workflows/WorkflowCard";
import { isWorkflowAvailable, workflowRegistry } from "../features/workflows/registry";
import { addKnownRunId, useKnownRuns } from "../state/knownRuns";

type RunRow = RunDetailResponse["run"];

const runColumns: DataTableColumn<RunRow>[] = [
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
  { key: "updated", header: "Updated", render: (row) => <time>{row.updated_at}</time> }
];

export function DashboardPage() {
  const navigate = useNavigate();
  const { knownRunIds } = useKnownRuns();
  const { health, capabilities, loading: apiLoading, error: apiError } = useApiStatus();
  const [runRows, setRunRows] = useState<RunRow[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalResponse[]>([]);
  const [manualRunId, setManualRunId] = useState("");
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState<NormalizedApiError | null>(null);
  const [openingRun, setOpeningRun] = useState(false);
  const available = capabilities?.workflows ?? null;

  useEffect(() => {
    let cancelled = false;
    setRunsLoading(true);
    setRunsError(null);

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
          setRunsError(toDisplayError(nextError));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setRunsLoading(false);
        }
      });

    Promise.all(
      knownRunIds.map((runId) =>
        getRunApprovals(runId).catch(() => {
          return [] as ApprovalResponse[];
        })
      )
    ).then((responses) => {
      if (!cancelled) {
        setPendingApprovals(responses.flat().filter((approval) => approval.status === "PENDING"));
      }
    });

    return () => {
      cancelled = true;
    };
  }, [knownRunIds]);

  async function openRun(event: FormEvent) {
    event.preventDefault();
    const candidateRunId = manualRunId.trim();
    if (!candidateRunId) {
      return;
    }
    setOpeningRun(true);
    setRunsError(null);
    try {
      const response = await getRunDetail(candidateRunId);
      addKnownRunId(response.run.id);
      setManualRunId("");
      navigate(`/runs/${response.run.id}`);
    } catch (nextError) {
      setRunsError(toDisplayError(nextError));
    } finally {
      setOpeningRun(false);
    }
  }

  const lastKnownRun = runRows[0] ?? null;

  return (
    <div className="page-stack">
      <PageHeader
        title="Gateway Command Center"
        eyebrow="Local demo UI"
        description="A run-centric surface over the FastAPI /api/v1 contract."
        actions={
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
        }
      />
      {apiError ? <ErrorState error={apiError} /> : null}
      <div className="metric-grid">
        <MetricCard
          label="API Health"
          value={apiLoading ? "checking" : health?.status ?? "unknown"}
          helper={apiBaseUrl}
          tone={health?.status === "ok" ? "good" : "warn"}
        />
        <MetricCard
          label="Provider Mode"
          value={capabilities?.provider_mode ?? "unknown"}
          helper="from capabilities"
          tone={capabilities?.provider_mode === "mock" ? "info" : "warn"}
        />
        <MetricCard
          label="Model Selection"
          value={capabilities?.model_selection.enabled ? "enabled" : "disabled"}
          helper="provider/model selector is not exposed"
          tone={capabilities?.model_selection.enabled ? "warn" : "default"}
        />
        <MetricCard
          label="Available Workflows"
          value={capabilities?.workflows.length ?? 0}
          helper="backend-supported templates"
          tone="default"
        />
        <MetricCard label="Known Runs" value={knownRunIds.length} helper="local/session run IDs only" tone="info" />
        <MetricCard
          label="Pending Approvals"
          value={pendingApprovals.length}
          helper="from locally known runs only"
          tone={pendingApprovals.length > 0 ? "warn" : "default"}
        />
      </div>
      <div className="content-with-inspector">
        <section className="panel">
          <div className="panel__header">
            <h2>Session Run Snapshot</h2>
            <Link to="/runs">Open Agent Runs</Link>
          </div>
          {runsLoading ? <LoadingState label="Loading known runs..." /> : null}
          {runsError ? <ErrorState error={runsError} /> : null}
          <DataTable columns={runColumns} rows={runRows} rowKey={(row) => row.id} emptyLabel="No known runs yet." />
        </section>
        <div className="stack">
          <CapabilitiesPanel health={health} capabilities={capabilities} />
          <section className="panel">
            <h2>Last Known Run</h2>
            {lastKnownRun ? (
              <div className="kv-grid">
                <span>Run ID</span>
                <Link to={`/runs/${lastKnownRun.id}`}>{lastKnownRun.id}</Link>
                <span>Status</span>
                <StatusChip
                  label={getRunStatusPresentation(lastKnownRun.status).label}
                  tone={getRunStatusPresentation(lastKnownRun.status).tone}
                />
                <span>Updated</span>
                <time>{lastKnownRun.updated_at}</time>
              </div>
            ) : (
              <p className="muted">Submit or open a run to populate this panel.</p>
            )}
          </section>
        </div>
      </div>
      <section className="panel">
        <div className="panel__header">
          <h2>Quick Launch</h2>
          <Link to="/workflows">Workflow catalog</Link>
        </div>
        <div className="workflow-grid">
          {workflowRegistry.map((workflow) => (
            <WorkflowCard
              key={workflow.key}
              workflow={workflow}
              available={isWorkflowAvailable(workflow, available)}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
