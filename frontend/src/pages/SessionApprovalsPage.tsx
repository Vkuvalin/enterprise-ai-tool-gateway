import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getRunApprovals, settleRunReads, type RunReadSummary } from "../api/runs";
import type { ApprovalResponse } from "../api/types";
import { DataTable, type DataTableColumn } from "../components/data/DataTable";
import { InspectorPanel } from "../components/data/InspectorPanel";
import { JsonViewer } from "../components/data/JsonViewer";
import { EmptyState } from "../components/feedback/EmptyState";
import { LoadingState } from "../components/feedback/LoadingState";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { StatusChip } from "../components/status/StatusChip";
import { toneForApproval } from "../components/status/statusPresentation";
import {
  ApprovalActionsPanel,
  type ApprovalResolveOutcome
} from "../features/approvals/ApprovalActionsPanel";
import { useKnownRuns } from "../state/knownRuns";
import { useLocale } from "../i18n/LocaleProvider";
import type { Translator } from "../i18n/messages";
import { getApprovalStatusLabel } from "../i18n/presentation";

type AggregateReadState = {
  ownerKey: string;
  summary: RunReadSummary;
};

function getColumns(t: Translator): DataTableColumn<ApprovalResponse>[] {
  return [
    {
      key: "status",
      header: t("common.status"),
      render: (row) => <StatusChip label={getApprovalStatusLabel(row.status, t)} tone={toneForApproval(row.status)} />
    },
    { key: "run", header: t("common.runId"), render: (row) => <Link to={`/runs/${row.run_id}`}>{row.run_id}</Link> },
    { key: "role", header: t("sessionApprovals.approverRole"), render: (row) => row.required_approver_role },
    { key: "summary", header: t("common.summary"), render: (row) => row.summary }
  ];
}

export function SessionApprovalsPage() {
  const { t } = useLocale();
  const { knownRunIds } = useKnownRuns();
  const [approvals, setApprovals] = useState<ApprovalResponse[]>([]);
  const [snapshotOwnerKey, setSnapshotOwnerKey] = useState<string | null>(null);
  const [readState, setReadState] = useState<AggregateReadState | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastResolveOutcome, setLastResolveOutcome] = useState<ApprovalResolveOutcome | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const knownRunsKey = knownRunIds.join("\u001f");
  const hasCurrentSnapshot = snapshotOwnerKey === knownRunsKey;
  const currentApprovals = hasCurrentSnapshot ? approvals : [];
  const currentReadSummary = readState?.ownerKey === knownRunsKey ? readState.summary : null;
  const unavailable =
    currentReadSummary !== null && currentReadSummary.attempted > 0 && currentReadSummary.succeeded === 0;
  const partial =
    currentReadSummary !== null && currentReadSummary.succeeded > 0 && currentReadSummary.failures.length > 0;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    settleRunReads(knownRunIds, getRunApprovals)
      .then((result) => {
        if (cancelled) {
          return;
        }
        setReadState({ ownerKey: knownRunsKey, summary: result });
        if (result.attempted > 0 && result.succeeded === 0) {
          return;
        }
        const pending = result.successes
          .flatMap(({ value }) => value)
          .filter((approval) => approval.status === "PENDING");
        setApprovals(pending);
        setSnapshotOwnerKey(knownRunsKey);
        setSelectedId((current) =>
          current && pending.some((approval) => approval.id === current)
            ? current
            : pending[0]?.id ?? null
        );
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

  const selected = currentApprovals.find((approval) => approval.id === selectedId) ?? null;
  const initialLoading = knownRunIds.length > 0 && !hasCurrentSnapshot && !unavailable;
  const emptyLabel = unavailable
    ? t("sessionApprovals.emptyUnavailable")
    : partial
      ? t("sessionApprovals.emptyPartial")
      : t("sessionApprovals.empty");
  const columns = getColumns(t);

  function onResolved(outcome: ApprovalResolveOutcome) {
    setLastResolveOutcome(outcome);
    setRefreshToken((value) => value + 1);
  }

  return (
    <div className="page-stack">
      <PageHeader
        title={t("sessionApprovals.title")}
        eyebrow={t("sessionApprovals.eyebrow")}
        description={t("sessionApprovals.description")}
        actions={
          <ActionButton
            type="button"
            onClick={() => setRefreshToken((value) => value + 1)}
            aria-busy={loading && hasCurrentSnapshot}
            disabled={loading}
          >
            {t("common.refresh")}
          </ActionButton>
        }
      />
      {knownRunIds.length === 0 ? (
        <EmptyState
          title={t("sessionApprovals.noKnownRuns")}
          detail={t("sessionApprovals.noKnownRunsDetail")}
        />
      ) : null}
      {initialLoading ? <LoadingState label={t("sessionApprovals.loading")} /> : null}
      {partial || unavailable ? (
        <div
          className={`state-box ${unavailable ? "state-box--error" : "state-box--warning"}`}
          role={unavailable ? "alert" : "status"}
        >
          <strong>
            {unavailable ? t("sessionApprovals.unavailable") : t("sessionApprovals.incomplete")}
          </strong>
          <span>
            {unavailable
              ? `${t("sessionApprovals.noneRead", { count: currentReadSummary?.attempted ?? 0 })}${
                  hasCurrentSnapshot ? ` ${t("common.showingLastSnapshot")}` : ""
                }`
              : t("sessionApprovals.partial", {
                  failed: currentReadSummary?.failures.length ?? 0,
                  attempted: currentReadSummary?.attempted ?? 0
                })}
          </span>
        </div>
      ) : null}
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
              emptyLabel={emptyLabel}
            />
          </section>
          <InspectorPanel title={t("sessionApprovals.decisionPanel")}>
            {selected ? (
              <div className="stack">
                <div className="kv-grid">
                  <span>{t("common.runId")}</span>
                  <code>{selected.run_id}</code>
                  <span>{t("common.approvalId")}</span>
                  <code>{selected.id}</code>
                  <span>{t("common.status")}</span>
                  <StatusChip
                    label={getApprovalStatusLabel(selected.status, t)}
                    tone={toneForApproval(selected.status)}
                  />
                </div>
                <ApprovalActionsPanel
                  key={`${selected.run_id}:${selected.id}`}
                  approval={selected}
                  onResolved={onResolved}
                />
              </div>
            ) : (
              <p className="muted">{t("sessionApprovals.selectPending")}</p>
            )}
          </InspectorPanel>
        </div>
      ) : null}
      {lastResolveOutcome ? (
        <section className="panel">
          <div className="panel__header">
            <h2>{t("sessionApprovals.lastOutcome")}</h2>
            <Link to={`/runs/${lastResolveOutcome.runId}`}>{t("common.openRunLower")}</Link>
          </div>
          <div className="kv-grid">
            <span>{t("common.approvalId")}</span>
            <code>{lastResolveOutcome.approvalId}</code>
            <span>{t("common.runId")}</span>
            <code>{lastResolveOutcome.runId}</code>
          </div>
          <JsonViewer value={lastResolveOutcome.result} label={t("sessionApprovals.latestResponse")} />
        </section>
      ) : null}
    </div>
  );
}
