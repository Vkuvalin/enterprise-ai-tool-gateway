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
import { useLocale } from "../i18n/LocaleProvider";

type RunOwnedError = {
  runId: string;
  error: NormalizedApiError;
};

export function RunToolCallsPage() {
  const { t } = useLocale();
  const { runId = "" } = useParams();
  const [toolCalls, setToolCalls] = useState<ToolCallResponse[]>([]);
  const [loadedRunId, setLoadedRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorState, setErrorState] = useState<RunOwnedError | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const { toast, showToast, clearToast } = useToast();

  const hasCurrentSnapshot = loadedRunId === runId;
  const currentToolCalls = hasCurrentSnapshot ? toolCalls : [];
  const currentError = errorState?.runId === runId ? errorState.error : null;

  useEffect(() => {
    let cancelled = false;
    const hadLoaded = loadedRunId === runId;
    const manualRefresh = hadLoaded && refreshToken > 0;
    setLoading(true);
    if (!hadLoaded) {
      clearToast();
    }
    setErrorState(null);
    getRunToolCalls(runId)
      .then((response) => {
        if (!cancelled) {
          setToolCalls(response);
          setLoadedRunId(runId);
          setErrorState(null);
          if (runId) {
            setSelectedRunId(runId);
          }
          if (manualRefresh) {
            showToast({ messageKey: "common.dataRefreshed", tone: "success" });
          }
        }
      })
      .catch((nextError: unknown) => {
        if (cancelled) {
          return;
        }
        const displayError = toDisplayError(nextError);
        setErrorState({ runId, error: displayError });
        if (hadLoaded) {
          showToast({ messageKey: "common.refreshFailed", tone: "error" });
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
  }, [runId, refreshToken, showToast, clearToast]);

  const initialLoading = !hasCurrentSnapshot && currentError === null;

  function refreshToolCalls() {
    if (!loading) {
      setRefreshToken((value) => value + 1);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title={t("runToolCalls.title")}
        eyebrow={t("runToolCalls.eyebrow")}
        description={t("runToolCalls.description")}
        actions={
          <ActionButton
            type="button"
            className="action-button--compact"
            onClick={refreshToolCalls}
            aria-busy={loading && hasCurrentSnapshot}
            disabled={loading}
          >
            {t("common.refresh")}
          </ActionButton>
        }
      />
      {initialLoading ? <LoadingState label={t("runToolCalls.loading")} /> : null}
      {currentError ? <ErrorState error={currentError} /> : null}
      {hasCurrentSnapshot ? <ToolCallsTable toolCalls={currentToolCalls} /> : null}
      <Toast toast={hasCurrentSnapshot ? toast : null} />
    </div>
  );
}
