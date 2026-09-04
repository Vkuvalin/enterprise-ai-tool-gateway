import { FormEvent, useEffect, useRef, useState } from "react";
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
import { useLocale } from "../i18n/LocaleProvider";
import { addKnownRunId, clearKnownRuns, removeKnownRunId, useKnownRuns } from "../state/knownRuns";

export function SettingsPage() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const { knownRunIds } = useKnownRuns();
  const { toast, showToast } = useToast();
  const { health, capabilities, loading, hasLoaded, stale, error, refresh } = useApiStatus({
    onRefreshSuccess: () => showToast({ messageKey: "common.dataRefreshed", tone: "success" }),
    onRefreshError: () => showToast({ messageKey: "common.refreshFailed", tone: "error" })
  });
  const [manualRunId, setManualRunId] = useState("");
  const [openError, setOpenError] = useState<NormalizedApiError | null>(null);
  const [openingRun, setOpeningRun] = useState(false);
  const mountedRef = useRef(false);
  const openRequestIdRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      openRequestIdRef.current += 1;
    };
  }, []);

  async function openRun(event: FormEvent) {
    event.preventDefault();
    const candidateRunId = manualRunId.trim();
    if (!candidateRunId) {
      return;
    }
    const requestId = ++openRequestIdRef.current;
    setOpeningRun(true);
    setOpenError(null);
    try {
      const response = await getRunDetail(candidateRunId);
      if (!mountedRef.current || openRequestIdRef.current !== requestId) {
        return;
      }
      addKnownRunId(response.run.id);
      setManualRunId("");
      navigate(`/runs/${response.run.id}`);
    } catch (nextError) {
      if (mountedRef.current && openRequestIdRef.current === requestId) {
        setOpenError(toDisplayError(nextError));
      }
    } finally {
      if (mountedRef.current && openRequestIdRef.current === requestId) {
        setOpeningRun(false);
      }
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
        title={t("settings.title")}
        eyebrow={t("settings.eyebrow")}
        description={t("settings.description")}
        actions={
          <ActionButton
            type="button"
            className="action-button--compact"
            onClick={refreshApiStatus}
            aria-busy={loading && hasLoaded}
          >
            {t("settings.refreshApi")}
          </ActionButton>
        }
      />
      {initialLoading ? <LoadingState label={t("settings.loading")} /> : null}
      {error ? <ErrorState error={error} /> : null}
      <div className="content-with-inspector">
        <section className="panel">
          <h2>{t("settings.clientBoundary")}</h2>
          <div className="kv-grid">
            <span>{t("settings.apiBaseUrl")}</span>
            <code>{apiBaseUrl}</code>
            <span>{t("common.health")}</span>
            <StatusChip
              label={`${health?.status ?? t("common.unknown")}${stale ? ` (${t("common.stale")})` : ""}`}
              tone={stale ? "orange" : health?.status === "ok" ? "green" : "gray"}
              title={stale ? t("capabilities.lastRefreshFailed") : undefined}
            />
            <span>{t("common.providerMode")}</span>
            <StatusChip label={capabilities?.provider_mode ?? t("common.unknown")} tone="purple" />
            <span>{t("common.modelSelection")}</span>
            <StatusChip
              label={capabilities?.model_selection.enabled ? t("common.enabled") : t("common.disabled")}
              tone={capabilities?.model_selection.enabled ? "orange" : "gray"}
            />
          </div>
          <p className="muted">{t("settings.boundaryDescription")}</p>
          <JsonViewer
            value={{
              health,
              capabilities
            }}
            label={t("settings.apiPayloads")}
          />
        </section>
        <CapabilitiesPanel health={health} capabilities={capabilities} stale={stale} />
      </div>
      <section className="panel">
        <div className="panel__header">
          <h2>{t("settings.knownRunIndex")}</h2>
        </div>
        <div className="known-run-actions">
          <form className="inline-form inline-form--compact" onSubmit={openRun}>
            <input
              aria-label={t("common.addRunAria")}
              placeholder={t("common.pasteRunId")}
              value={manualRunId}
              onChange={(event) => setManualRunId(event.target.value)}
            />
            <ActionButton type="submit" variant="primary" className="action-button--compact" disabled={openingRun}>
              {openingRun ? t("common.opening") : t("common.openRun")}
            </ActionButton>
          </form>
          <ActionButton type="button" className="action-button--compact" onClick={clearKnownRuns}>
            {t("settings.clearKnownRuns")}
          </ActionButton>
        </div>
        {openError ? <ErrorState error={openError} /> : null}
        <div className="run-id-list">
          {knownRunIds.length === 0 ? <p className="muted">{t("settings.noRunIds")}</p> : null}
          {knownRunIds.map((runId) => (
            <div className="run-id-list__row" key={runId}>
              <Link to={`/runs/${runId}`}>
                <code>{runId}</code>
              </Link>
              <button className="ghost-button" type="button" onClick={() => removeKnownRunId(runId)}>
                {t("settings.remove")}
              </button>
            </div>
          ))}
        </div>
      </section>
      <Toast toast={toast} />
    </div>
  );
}
