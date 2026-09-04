import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getRunDetail, settleRunReads, type RunReadSummary } from "../api/runs";
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
import { useLocale } from "../i18n/LocaleProvider";
import type { Translator } from "../i18n/messages";
import { addKnownRunId, useKnownRuns } from "../state/knownRuns";

type RunRow = RunDetailResponse["run"];

type AggregateReadState = {
  ownerKey: string;
  summary: RunReadSummary;
};

function getColumns(t: Translator): DataTableColumn<RunRow>[] {
  return [
    { key: "id", header: t("common.runId"), render: (row) => <Link to={`/runs/${row.id}`}>{row.id}</Link> },
    { key: "request", header: t("common.requestType"), render: (row) => <code>{row.request_type}</code> },
    {
      key: "status",
      header: t("common.status"),
      render: (row) => {
        const status = getRunStatusPresentation(row.status, t);
        return <StatusChip label={status.label} tone={status.tone} title={status.description} />;
      }
    },
    { key: "risk", header: t("common.risk"), render: (row) => <RiskBadge risk={row.risk_level} /> },
    { key: "updated", header: t("common.updated"), render: (row) => <time>{row.updated_at}</time> },
    {
      key: "records",
      header: t("sessionRuns.records"),
      render: (row) => (
        <div className="run-links">
          <Link to={`/runs/${row.id}/approvals`}>{t("common.approvals")}</Link>
          <Link to={`/runs/${row.id}/tool-calls`}>{t("common.toolCalls")}</Link>
          <Link to={`/runs/${row.id}/audit`}>{t("common.auditTrail")}</Link>
        </div>
      )
    }
  ];
}

export function SessionRunsPage() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const { knownRunIds } = useKnownRuns();
  const [runRows, setRunRows] = useState<RunRow[]>([]);
  const [snapshotOwnerKey, setSnapshotOwnerKey] = useState<string | null>(null);
  const [readState, setReadState] = useState<AggregateReadState | null>(null);
  const [manualRunId, setManualRunId] = useState("");
  const [loading, setLoading] = useState(false);
  const [openError, setOpenError] = useState<NormalizedApiError | null>(null);
  const [openingRun, setOpeningRun] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const mountedRef = useRef(false);
  const openRequestIdRef = useRef(0);
  const knownRunsKey = knownRunIds.join("\u001f");
  const hasCurrentSnapshot = snapshotOwnerKey === knownRunsKey;
  const currentRunRows = hasCurrentSnapshot ? runRows : [];
  const currentReadSummary = readState?.ownerKey === knownRunsKey ? readState.summary : null;
  const unavailable =
    currentReadSummary !== null && currentReadSummary.attempted > 0 && currentReadSummary.succeeded === 0;
  const partial =
    currentReadSummary !== null && currentReadSummary.succeeded > 0 && currentReadSummary.failures.length > 0;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      openRequestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    settleRunReads(knownRunIds, getRunDetail)
      .then((result) => {
        if (cancelled) {
          return;
        }
        setReadState({ ownerKey: knownRunsKey, summary: result });
        if (result.attempted > 0 && result.succeeded === 0) {
          return;
        }
        setRunRows(result.successes.map(({ value }) => value.run));
        setSnapshotOwnerKey(knownRunsKey);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [knownRunIds, knownRunsKey, refreshToken]);

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

  const initialLoading = knownRunIds.length > 0 && !hasCurrentSnapshot && !unavailable;
  const emptyLabel = unavailable
    ? t("sessionRuns.emptyUnavailable")
    : partial
      ? t("sessionRuns.emptyPartial")
      : t("sessionRuns.empty");
  const columns = getColumns(t);

  return (
    <div className="page-stack">
      <PageHeader
        title={t("sessionRuns.title")}
        eyebrow={t("sessionRuns.eyebrow")}
        description={t("sessionRuns.description")}
        actions={
          <div className="header-actions">
            <form className="inline-form inline-form--compact" onSubmit={openRun}>
              <input
                aria-label={t("common.openRunAria")}
                placeholder={t("common.pasteRunId")}
                value={manualRunId}
                onChange={(event) => setManualRunId(event.target.value)}
              />
              <ActionButton type="submit" variant="primary" className="action-button--compact" disabled={openingRun}>
                {openingRun ? t("common.opening") : t("common.openRun")}
              </ActionButton>
            </form>
            <ActionButton
              type="button"
              className="action-button--compact"
              onClick={() => setRefreshToken((value) => value + 1)}
              aria-busy={loading && hasCurrentSnapshot}
              disabled={loading}
            >
              {t("common.refresh")}
            </ActionButton>
          </div>
        }
      />
      {knownRunIds.length === 0 ? (
        <EmptyState title={t("sessionRuns.noKnownRuns")} detail={t("sessionRuns.noKnownRunsDetail")} />
      ) : null}
      {initialLoading ? <LoadingState label={t("sessionRuns.loading")} /> : null}
      {openError ? <ErrorState error={openError} /> : null}
      {partial || unavailable ? (
        <div
          className={`state-box ${unavailable ? "state-box--error" : "state-box--warning"}`}
          role={unavailable ? "alert" : "status"}
        >
          <strong>{unavailable ? t("sessionRuns.unavailable") : t("sessionRuns.incomplete")}</strong>
          <span>
            {unavailable
              ? `${t("sessionRuns.noneRead", { count: currentReadSummary?.attempted ?? 0 })}${
                  hasCurrentSnapshot ? ` ${t("common.showingLastSnapshot")}` : ""
                }`
              : t("sessionRuns.partial", {
                  failed: currentReadSummary?.failures.length ?? 0,
                  attempted: currentReadSummary?.attempted ?? 0
                })}
          </span>
        </div>
      ) : null}
      {hasCurrentSnapshot && knownRunIds.length > 0 ? <section className="panel">
        <div className="panel__header">
          <h2>{t("sessionRuns.heading")}</h2>
          <span className="muted">{t("sessionRuns.localIds", { count: knownRunIds.length })}</span>
        </div>
        <DataTable columns={columns} rows={currentRunRows} rowKey={(row) => row.id} emptyLabel={emptyLabel} />
      </section> : null}
    </div>
  );
}
