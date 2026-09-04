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
import { useLocale } from "../i18n/LocaleProvider";
import { addKnownRunId } from "../state/knownRuns";

type RunOwnedError = {
  runId: string;
  error: NormalizedApiError;
};

export function RunDetailPage() {
  const { t } = useLocale();
  const { runId = "" } = useParams();
  const [detail, setDetail] = useState<RunDetailResponse | null>(null);
  const [loadedRunId, setLoadedRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorState, setErrorState] = useState<RunOwnedError | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const { toast, showToast, clearToast } = useToast();

  const currentDetail = loadedRunId === runId ? detail : null;
  const currentError = errorState?.runId === runId ? errorState.error : null;

  useEffect(() => {
    let cancelled = false;
    const hadDetail = loadedRunId === runId && detail !== null;
    const manualRefresh = hadDetail && refreshToken > 0;
    setLoading(true);
    if (!hadDetail) {
      clearToast();
    }
    setErrorState(null);
    getRunDetail(runId)
      .then((response) => {
        if (cancelled) {
          return;
        }
        addKnownRunId(response.run.id);
        setDetail(response);
        setLoadedRunId(runId);
        setErrorState(null);
        if (manualRefresh) {
          showToast({ messageKey: "common.dataRefreshed", tone: "success" });
        }
      })
      .catch((nextError: unknown) => {
        if (cancelled) {
          return;
        }
        const displayError = toDisplayError(nextError);
        setErrorState({ runId, error: displayError });
        if (hadDetail) {
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

  const status = currentDetail ? getRunStatusPresentation(currentDetail.run.status, t) : null;
  const initialLoading = currentDetail === null && currentError === null;

  function refreshDetail() {
    if (!loading) {
      setRefreshToken((value) => value + 1);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title={t("runDetail.title")}
        eyebrow={t("runDetail.eyebrow")}
        description={t("runDetail.description")}
        actions={
          <ActionButton
            type="button"
            className="action-button--compact"
            onClick={refreshDetail}
            aria-busy={loading && currentDetail !== null}
            disabled={loading}
          >
            {t("common.refresh")}
          </ActionButton>
        }
      />
      {initialLoading ? <LoadingState label={t("runDetail.loading")} /> : null}
      {currentError ? <ErrorState error={currentError} /> : null}
      {currentDetail ? (
        <>
          <div className="run-detail-grid">
            <div className="run-detail-grid__main">
              <section className="panel">
                <div className="panel__header">
                  <h2>{t("runDetail.outcome")}</h2>
                  {status ? <StatusChip label={status.label} tone={status.tone} title={status.description} /> : null}
                </div>
                <p>{status?.description}</p>
                {currentDetail.final_summary ? <p>{currentDetail.final_summary}</p> : null}
                {currentDetail.run.error_message ? (
                  <div className="state-box state-box--error">
                    <strong>{currentDetail.run.error_type ?? "run_error"}</strong>
                    <span>{currentDetail.run.error_message}</span>
                  </div>
                ) : null}
              </section>
              <section className="panel">
                <div className="panel__header">
                  <h2>{t("runDetail.records")}</h2>
                  <div className="run-links">
                    <Link to={`/runs/${currentDetail.run.id}/approvals`}>{t("common.approvals")}</Link>
                    <Link to={`/runs/${currentDetail.run.id}/tool-calls`}>{t("common.toolCalls")}</Link>
                    <Link to={`/runs/${currentDetail.run.id}/audit`}>{t("common.auditTrail")}</Link>
                  </div>
                </div>
                <p className="muted">{t("runDetail.recordsDescription")}</p>
                <div className="metric-grid">
                  <div className="mini-metric">
                    <span>{t("common.approvals")}</span>
                    <strong>{currentDetail.approval ? 1 : 0}</strong>
                  </div>
                  <div className="mini-metric">
                    <span>{t("common.toolCalls")}</span>
                    <strong>{currentDetail.tool_calls.length}</strong>
                  </div>
                  <div className="mini-metric">
                    <span>{t("common.auditEvents")}</span>
                    <strong>{currentDetail.audit_events.length}</strong>
                  </div>
                </div>
              </section>
              <ToolCallsTable toolCalls={currentDetail.tool_calls.slice(0, 3)} />
            </div>
            <RunSummaryPanel run={currentDetail.run} showLinks={false} />
          </div>
          <InspectorPanel title={t("runDetail.json")}>
            <JsonViewer value={currentDetail} />
          </InspectorPanel>
        </>
      ) : null}
      <Toast toast={currentDetail ? toast : null} />
    </div>
  );
}
