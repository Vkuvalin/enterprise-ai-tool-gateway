import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRunDetail } from "../api/runs";
import { toDisplayError } from "../api/errors";
import type { NormalizedApiError, RunDetailResponse } from "../api/types";
import { InspectorPanel } from "../components/data/InspectorPanel";
import { JsonViewer } from "../components/data/JsonViewer";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Toast, useToast } from "../components/feedback/Toast";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { getRunStatusPresentation } from "../components/status/statusPresentation";
import { StatusChip } from "../components/status/StatusChip";
import { ToolCallsTable } from "../features/toolCalls/ToolCallsTable";
import { RunSummaryPanel } from "../features/runs/RunSummaryPanel";
import { addKnownRunId } from "../state/knownRuns";

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const [detail, setDetail] = useState<RunDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const { toast, showToast } = useToast();

  useEffect(() => {
    let cancelled = false;
    const hadDetail = detail !== null;
    const manualRefresh = refreshToken > 0;
    setLoading(true);
    if (!hadDetail) {
      setError(null);
    }
    getRunDetail(runId)
      .then((response) => {
        if (cancelled) {
          return;
        }
        addKnownRunId(response.run.id);
        setDetail(response);
        setError(null);
        if (manualRefresh) {
          showToast({ message: "Data refreshed", tone: "success" });
        }
      })
      .catch((nextError: unknown) => {
        if (cancelled) {
          return;
        }
        const displayError = toDisplayError(nextError);
        if (hadDetail) {
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

  const status = detail ? getRunStatusPresentation(detail.run.status) : null;
  const initialLoading = loading && detail === null;

  function refreshDetail() {
    if (!loading) {
      setRefreshToken((value) => value + 1);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Run Detail"
        eyebrow="Run-scoped view"
        description="This page reads one backend run by ID from /api/v1."
        actions={
          <ActionButton
            type="button"
            className="action-button--compact"
            onClick={refreshDetail}
            aria-busy={loading && detail !== null}
          >
            Refresh
          </ActionButton>
        }
      />
      {initialLoading ? <LoadingState label="Loading run detail..." /> : null}
      {error && !detail ? <ErrorState error={error} /> : null}
      {detail ? (
        <>
          <div className="run-detail-grid">
            <div className="run-detail-grid__main">
              <section className="panel">
                <div className="panel__header">
                  <h2>Controlled Outcome</h2>
                  {status ? <StatusChip label={status.label} tone={status.tone} title={status.description} /> : null}
                </div>
                <p>{status?.description}</p>
                {detail.final_summary ? <p>{detail.final_summary}</p> : null}
                {detail.run.error_message ? (
                  <div className="state-box state-box--error">
                    <strong>{detail.run.error_type ?? "run_error"}</strong>
                    <span>{detail.run.error_message}</span>
                  </div>
                ) : null}
              </section>
              <section className="panel">
                <div className="panel__header">
                  <h2>Records for this run</h2>
                  <div className="run-links">
                    <Link to={`/runs/${detail.run.id}/approvals`}>Approvals</Link>
                    <Link to={`/runs/${detail.run.id}/tool-calls`}>Tool Calls</Link>
                    <Link to={`/runs/${detail.run.id}/audit`}>Audit Trail</Link>
                  </div>
                </div>
                <p className="muted">Counts and links below are scoped to this backend run only.</p>
                <div className="metric-grid">
                  <div className="mini-metric">
                    <span>Approvals</span>
                    <strong>{detail.approval ? 1 : 0}</strong>
                  </div>
                  <div className="mini-metric">
                    <span>Tool calls</span>
                    <strong>{detail.tool_calls.length}</strong>
                  </div>
                  <div className="mini-metric">
                    <span>Audit events</span>
                    <strong>{detail.audit_events.length}</strong>
                  </div>
                </div>
              </section>
              <ToolCallsTable toolCalls={detail.tool_calls.slice(0, 3)} />
            </div>
            <RunSummaryPanel run={detail.run} showLinks={false} />
          </div>
          <InspectorPanel title="Run Detail JSON">
            <JsonViewer value={detail} />
          </InspectorPanel>
        </>
      ) : null}
      <Toast toast={toast} />
    </div>
  );
}
