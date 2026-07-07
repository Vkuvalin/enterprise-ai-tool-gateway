import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getRunToolCalls } from "../api/runs";
import { toDisplayError } from "../api/errors";
import type { NormalizedApiError, ToolCallResponse } from "../api/types";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Toast, useToast } from "../components/feedback/Toast";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { ToolCallsTable } from "../features/toolCalls/ToolCallsTable";
import { setSelectedRunId } from "../state/knownRuns";

export function RunToolCallsPage() {
  const { runId = "" } = useParams();
  const [toolCalls, setToolCalls] = useState<ToolCallResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
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
    getRunToolCalls(runId)
      .then((response) => {
        if (!cancelled) {
          setToolCalls(response);
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

  const initialLoading = loading && !hasLoaded;

  function refreshToolCalls() {
    if (!loading) {
      setRefreshToken((value) => value + 1);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Run Tool Calls"
        eyebrow="Run-scoped view"
        description="Tool calls are read from /api/v1 for the selected run only."
        actions={
          <ActionButton
            type="button"
            className="action-button--compact"
            onClick={refreshToolCalls}
            aria-busy={loading && hasLoaded}
          >
            Refresh
          </ActionButton>
        }
      />
      {initialLoading ? <LoadingState label="Loading tool calls..." /> : null}
      {error && !hasLoaded ? <ErrorState error={error} /> : null}
      <ToolCallsTable toolCalls={toolCalls} />
      <Toast toast={toast} />
    </div>
  );
}
