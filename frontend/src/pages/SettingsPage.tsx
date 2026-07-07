import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiBaseUrl } from "../api/client";
import { toDisplayError } from "../api/errors";
import { getRunDetail } from "../api/runs";
import type { NormalizedApiError } from "../api/types";
import { JsonViewer } from "../components/data/JsonViewer";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Toast, useToast } from "../components/feedback/Toast";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { StatusChip } from "../components/status/StatusChip";
import { CapabilitiesPanel } from "../features/capabilities/CapabilitiesPanel";
import { useApiStatus } from "../features/capabilities/useApiStatus";
import { addKnownRunId, clearKnownRuns, removeKnownRunId, useKnownRuns } from "../state/knownRuns";

export function SettingsPage() {
  const navigate = useNavigate();
  const { knownRunIds } = useKnownRuns();
  const { toast, showToast } = useToast();
  const { health, capabilities, loading, hasLoaded, error, refresh } = useApiStatus({
    onRefreshSuccess: () => showToast({ message: "Data refreshed", tone: "success" }),
    onRefreshError: () => showToast({ message: "Refresh failed", tone: "error" })
  });
  const [manualRunId, setManualRunId] = useState("");
  const [openError, setOpenError] = useState<NormalizedApiError | null>(null);
  const [openingRun, setOpeningRun] = useState(false);

  async function openRun(event: FormEvent) {
    event.preventDefault();
    const candidateRunId = manualRunId.trim();
    if (!candidateRunId) {
      return;
    }
    setOpeningRun(true);
    setOpenError(null);
    try {
      const response = await getRunDetail(candidateRunId);
      addKnownRunId(response.run.id);
      setManualRunId("");
      navigate(`/runs/${response.run.id}`);
    } catch (nextError) {
      setOpenError(toDisplayError(nextError));
    } finally {
      setOpeningRun(false);
    }
  }

  const initialLoading = loading && !hasLoaded;

  function refreshApiStatus() {
    if (!loading) {
      refresh();
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Settings / API Status"
        eyebrow="Local client settings"
        description="This page shows API connectivity and local run index controls only."
        actions={
          <ActionButton
            type="button"
            className="action-button--compact"
            onClick={refreshApiStatus}
            aria-busy={loading && hasLoaded}
          >
            Refresh API Status
          </ActionButton>
        }
      />
      {initialLoading ? <LoadingState label="Loading API status..." /> : null}
      {error && !hasLoaded ? <ErrorState error={error} /> : null}
      <div className="content-with-inspector">
        <section className="panel">
          <h2>Client Boundary</h2>
          <div className="kv-grid">
            <span>API base URL</span>
            <code>{apiBaseUrl}</code>
            <span>Health</span>
            <StatusChip label={health?.status ?? "unknown"} tone={health?.status === "ok" ? "green" : "gray"} />
            <span>Provider mode</span>
            <StatusChip label={capabilities?.provider_mode ?? "unknown"} tone="purple" />
            <span>Model selection</span>
            <StatusChip
              label={capabilities?.model_selection.enabled ? "enabled" : "disabled"}
              tone={capabilities?.model_selection.enabled ? "orange" : "gray"}
            />
          </div>
          <p className="muted">
            The frontend calls FastAPI through /api/v1 and does not import backend internals. Local browser storage
            stores run IDs only.
          </p>
          <JsonViewer
            value={{
              health,
              capabilities
            }}
            label="API status payloads"
          />
        </section>
        <CapabilitiesPanel health={health} capabilities={capabilities} />
      </div>
      <section className="panel">
        <div className="panel__header">
          <h2>Known Run Index</h2>
        </div>
        <div className="known-run-actions">
          <form className="inline-form inline-form--compact" onSubmit={openRun}>
            <input
              aria-label="Add run ID"
              placeholder="Paste run_id"
              value={manualRunId}
              onChange={(event) => setManualRunId(event.target.value)}
            />
            <ActionButton type="submit" variant="primary" className="action-button--compact" disabled={openingRun}>
              {openingRun ? "Opening..." : "Open Run"}
            </ActionButton>
          </form>
          <ActionButton type="button" className="action-button--compact" onClick={clearKnownRuns}>
            Clear known runs
          </ActionButton>
        </div>
        {openError ? <ErrorState error={openError} /> : null}
        <div className="run-id-list">
          {knownRunIds.length === 0 ? <p className="muted">No run IDs stored.</p> : null}
          {knownRunIds.map((runId) => (
            <div className="run-id-list__row" key={runId}>
              <Link to={`/runs/${runId}`}>
                <code>{runId}</code>
              </Link>
              <button className="ghost-button" type="button" onClick={() => removeKnownRunId(runId)}>
                Remove
              </button>
            </div>
          ))}
        </div>
      </section>
      <Toast toast={toast} />
    </div>
  );
}
