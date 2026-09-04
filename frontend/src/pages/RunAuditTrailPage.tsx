import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getRunAuditEvents } from "../api/runs";
import { toDisplayError } from "../api/errors";
import type { AuditEventResponse, NormalizedApiError } from "../api/types";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Toast, useToast } from "../components/feedback/Toast";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { AuditTimeline } from "../features/audit/AuditTimeline";
import { setSelectedRunId } from "../state/knownRuns";
import { useLocale } from "../i18n/LocaleProvider";

type RunOwnedError = {
  runId: string;
  error: NormalizedApiError;
};

export function RunAuditTrailPage() {
  const { t } = useLocale();
  const { runId = "" } = useParams();
  const [events, setEvents] = useState<AuditEventResponse[]>([]);
  const [loadedRunId, setLoadedRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorState, setErrorState] = useState<RunOwnedError | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const { toast, showToast, clearToast } = useToast();

  const hasCurrentSnapshot = loadedRunId === runId;
  const currentEvents = hasCurrentSnapshot ? events : [];
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
    getRunAuditEvents(runId)
      .then((response) => {
        if (!cancelled) {
          setEvents(response);
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

  function refreshAuditEvents() {
    if (!loading) {
      setRefreshToken((value) => value + 1);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title={t("runAudit.title")}
        eyebrow={t("runAudit.eyebrow")}
        description={t("runAudit.description")}
        actions={
          <ActionButton
            type="button"
            className="action-button--compact"
            onClick={refreshAuditEvents}
            aria-busy={loading && hasCurrentSnapshot}
            disabled={loading}
          >
            {t("common.refresh")}
          </ActionButton>
        }
      />
      {initialLoading ? <LoadingState label={t("runAudit.loading")} /> : null}
      {currentError ? <ErrorState error={currentError} /> : null}
      {hasCurrentSnapshot ? <AuditTimeline events={currentEvents} /> : null}
      <Toast toast={hasCurrentSnapshot ? toast : null} />
    </div>
  );
}
