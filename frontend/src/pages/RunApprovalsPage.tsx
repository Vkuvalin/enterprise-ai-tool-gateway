import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { getRunApprovals } from "../api/runs";
import { toDisplayError } from "../api/errors";
import type { ApprovalResponse, NormalizedApiError } from "../api/types";
import { DataTable, type DataTableColumn } from "../components/data/DataTable";
import { InspectorPanel } from "../components/data/InspectorPanel";
import { JsonViewer } from "../components/data/JsonViewer";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Toast, useToast } from "../components/feedback/Toast";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { StatusChip } from "../components/status/StatusChip";
import { toneForApproval } from "../components/status/statusPresentation";
import {
  ApprovalActionsPanel,
  type ApprovalResolveOutcome
} from "../features/approvals/ApprovalActionsPanel";
import { setSelectedRunId } from "../state/knownRuns";
import { useLocale } from "../i18n/LocaleProvider";
import type { Translator } from "../i18n/messages";
import { getApprovalStatusLabel } from "../i18n/presentation";

type RunOwnedError = {
  runId: string;
  error: NormalizedApiError;
};

function getColumns(t: Translator): DataTableColumn<ApprovalResponse>[] {
  return [
    {
      key: "status",
      header: t("common.status"),
      render: (row) => <StatusChip label={getApprovalStatusLabel(row.status, t)} tone={toneForApproval(row.status)} />
    },
    { key: "role", header: t("runApprovals.approverRole"), render: (row) => row.required_approver_role },
    { key: "summary", header: t("common.summary"), render: (row) => row.summary },
    { key: "created", header: t("common.created"), render: (row) => <time>{row.created_at}</time> },
    { key: "decision", header: t("runApprovals.decision"), render: (row) => row.decided_by ?? t("common.pending") }
  ];
}

export function RunApprovalsPage() {
  const { t } = useLocale();
  const { runId = "" } = useParams();
  const [approvals, setApprovals] = useState<ApprovalResponse[]>([]);
  const [loadedRunId, setLoadedRunId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorState, setErrorState] = useState<RunOwnedError | null>(null);
  const [lastResolveOutcome, setLastResolveOutcome] = useState<ApprovalResolveOutcome | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const { toast, showToast, clearToast } = useToast();
  const currentRunIdRef = useRef(runId);
  currentRunIdRef.current = runId;

  const hasCurrentSnapshot = loadedRunId === runId;
  const currentApprovals = hasCurrentSnapshot ? approvals : [];
  const currentError = errorState?.runId === runId ? errorState.error : null;
  const currentResolveOutcome =
    lastResolveOutcome?.runId === runId && lastResolveOutcome.approvalId === selectedId
      ? lastResolveOutcome
      : null;

  useEffect(() => {
    let cancelled = false;
    const hadLoaded = loadedRunId === runId;
    const manualRefresh = hadLoaded && refreshToken > 0;
    setLoading(true);
    if (!hadLoaded) {
      clearToast();
    }
    setErrorState(null);
    getRunApprovals(runId)
      .then((response) => {
        if (!cancelled) {
          setApprovals(response);
          setLoadedRunId(runId);
          setSelectedId((current) =>
            hadLoaded && current && response.some((approval) => approval.id === current)
              ? current
              : response[0]?.id ?? null
          );
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

  const selected = currentApprovals.find((approval) => approval.id === selectedId) ?? null;
  const initialLoading = !hasCurrentSnapshot && currentError === null;
  const columns = getColumns(t);

  function onResolved(outcome: ApprovalResolveOutcome) {
    if (outcome.runId !== currentRunIdRef.current) {
      return;
    }
    setLastResolveOutcome(outcome);
    setRefreshToken((value) => value + 1);
  }

  function refreshApprovals() {
    if (!loading) {
      setRefreshToken((value) => value + 1);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title={t("runApprovals.title")}
        eyebrow={t("runApprovals.eyebrow")}
        description={t("runApprovals.description")}
        actions={
          <ActionButton
            type="button"
            className="action-button--compact"
            onClick={refreshApprovals}
            aria-busy={loading && hasCurrentSnapshot}
            disabled={loading}
          >
            {t("common.refresh")}
          </ActionButton>
        }
      />
      {initialLoading ? <LoadingState label={t("runApprovals.loading")} /> : null}
      {currentError ? <ErrorState error={currentError} /> : null}
      {hasCurrentSnapshot ? (
        <div className="content-with-inspector">
          <section className="panel">
            <DataTable
              columns={[
                ...columns,
                {
                  key: "inspect",
                  header: t("common.inspect"),
                  render: (row) => (
                    <button className="ghost-button" type="button" onClick={() => setSelectedId(row.id)}>
                      {t("common.select")}
                    </button>
                  )
                }
              ]}
              rows={currentApprovals}
              rowKey={(row) => row.id}
              emptyLabel={t("runApprovals.empty")}
            />
          </section>
          <InspectorPanel title={t("runApprovals.details")}>
            {selected ? (
              <div className="stack">
                <div className="kv-grid">
                  <span>{t("common.approvalId")}</span>
                  <code>{selected.id}</code>
                  <span>{t("common.status")}</span>
                  <StatusChip
                    label={getApprovalStatusLabel(selected.status, t)}
                    tone={toneForApproval(selected.status)}
                  />
                  <span>{t("common.reason")}</span>
                  <span>{selected.reason ?? t("common.notReturned")}</span>
                  <span>{t("common.decidedBy")}</span>
                  <span>{selected.decided_by ?? t("common.pending")}</span>
                  <span>{t("common.comment")}</span>
                  <span>{selected.decision_comment ?? t("common.none")}</span>
                </div>
                <ApprovalActionsPanel
                  key={`${selected.run_id}:${selected.id}`}
                  approval={selected}
                  onResolved={onResolved}
                />
              </div>
            ) : (
              <p className="muted">{t("runApprovals.select")}</p>
            )}
            {currentResolveOutcome ? (
              <div className="stack">
                <div className="kv-grid">
                  <span>{t("runApprovals.latest")}</span>
                  <code>{currentResolveOutcome.approvalId}</code>
                  <span>{t("common.runId")}</span>
                  <code>{currentResolveOutcome.runId}</code>
                </div>
                <JsonViewer value={currentResolveOutcome.result} label={t("runApprovals.latestResponse")} />
              </div>
            ) : null}
          </InspectorPanel>
        </div>
      ) : null}
      <Toast toast={hasCurrentSnapshot ? toast : null} />
    </div>
  );
}
