import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiBaseUrl } from "../api/client";
import { getRunApprovals, getRunDetail, settleRunReads, type RunReadSummary } from "../api/runs";
import { toDisplayError } from "../api/errors";
import type { ApprovalResponse, NormalizedApiError, RunDetailResponse } from "../api/types";
import { DataTable, type DataTableColumn } from "../components/data/DataTable";
import { MetricCard } from "../components/data/MetricCard";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { RiskBadge } from "../components/status/RiskBadge";
import { StatusChip } from "../components/status/StatusChip";
import { getRunStatusPresentation } from "../components/status/statusPresentation";
import { CapabilitiesPanel } from "../features/capabilities/CapabilitiesPanel";
import { useApiStatus } from "../features/capabilities/useApiStatus";
import { WorkflowCard } from "../features/workflows/WorkflowCard";
import { isWorkflowAvailable, workflowRegistry } from "../features/workflows/registry";
import { useLocale } from "../i18n/LocaleProvider";
import type { Translator } from "../i18n/messages";
import { addKnownRunId, useKnownRuns } from "../state/knownRuns";

type RunRow = RunDetailResponse["run"];

type AggregateReadState = {
  ownerKey: string;
  summary: RunReadSummary;
};

function getRunColumns(t: Translator): DataTableColumn<RunRow>[] {
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
    { key: "updated", header: t("common.updated"), render: (row) => <time>{row.updated_at}</time> }
  ];
}

export function DashboardPage() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const { knownRunIds } = useKnownRuns();
  const { health, capabilities, loading: apiLoading, stale: apiStale, error: apiError } = useApiStatus();
  const [runRows, setRunRows] = useState<RunRow[]>([]);
  const [runSnapshotOwnerKey, setRunSnapshotOwnerKey] = useState<string | null>(null);
  const [runReadState, setRunReadState] = useState<AggregateReadState | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalResponse[]>([]);
  const [approvalSnapshotOwnerKey, setApprovalSnapshotOwnerKey] = useState<string | null>(null);
  const [approvalReadState, setApprovalReadState] = useState<AggregateReadState | null>(null);
  const [manualRunId, setManualRunId] = useState("");
  const [runsLoading, setRunsLoading] = useState(false);
  const [openError, setOpenError] = useState<NormalizedApiError | null>(null);
  const [openingRun, setOpeningRun] = useState(false);
  const mountedRef = useRef(false);
  const openRequestIdRef = useRef(0);
  const available = capabilities?.workflows ?? null;
  const knownRunsKey = knownRunIds.join("\u001f");
  const hasCurrentRunSnapshot = runSnapshotOwnerKey === knownRunsKey;
  const hasCurrentApprovalSnapshot = approvalSnapshotOwnerKey === knownRunsKey;
  const currentRunRows = hasCurrentRunSnapshot ? runRows : [];
  const currentPendingApprovals = hasCurrentApprovalSnapshot ? pendingApprovals : [];
  const currentRunReadSummary = runReadState?.ownerKey === knownRunsKey ? runReadState.summary : null;
  const currentApprovalReadSummary =
    approvalReadState?.ownerKey === knownRunsKey ? approvalReadState.summary : null;
  const runsUnavailable =
    currentRunReadSummary !== null && currentRunReadSummary.attempted > 0 && currentRunReadSummary.succeeded === 0;
  const runsPartial =
    currentRunReadSummary !== null && currentRunReadSummary.succeeded > 0 && currentRunReadSummary.failures.length > 0;
  const approvalsUnavailable =
    currentApprovalReadSummary !== null &&
    currentApprovalReadSummary.attempted > 0 &&
    currentApprovalReadSummary.succeeded === 0;
  const approvalsPartial =
    currentApprovalReadSummary !== null &&
    currentApprovalReadSummary.succeeded > 0 &&
    currentApprovalReadSummary.failures.length > 0;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      openRequestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setRunsLoading(true);

    Promise.all([
      settleRunReads(knownRunIds, getRunDetail),
      settleRunReads(knownRunIds, getRunApprovals)
    ])
      .then(([details, approvals]) => {
        if (cancelled) {
          return;
        }
        setRunReadState({ ownerKey: knownRunsKey, summary: details });
        if (details.attempted === 0 || details.succeeded > 0) {
          setRunRows(details.successes.map(({ value }) => value.run));
          setRunSnapshotOwnerKey(knownRunsKey);
        }

        setApprovalReadState({ ownerKey: knownRunsKey, summary: approvals });
        if (approvals.attempted === 0 || approvals.succeeded > 0) {
          setPendingApprovals(
            approvals.successes
              .flatMap(({ value }) => value)
              .filter((approval) => approval.status === "PENDING")
          );
          setApprovalSnapshotOwnerKey(knownRunsKey);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setRunsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [knownRunIds, knownRunsKey]);

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

  const lastKnownRun = currentRunRows[0] ?? null;
  const lastKnownStatus = lastKnownRun ? getRunStatusPresentation(lastKnownRun.status, t) : null;
  const runColumns = getRunColumns(t);
  const pendingApprovalsValue = approvalsUnavailable
    ? hasCurrentApprovalSnapshot
      ? `${currentPendingApprovals.length} (${t("common.stale")})`
      : t("dashboard.unavailable")
    : approvalsPartial
      ? `${currentPendingApprovals.length}+`
      : !hasCurrentApprovalSnapshot && knownRunIds.length > 0
        ? t("dashboard.checkingTitle")
        : currentPendingApprovals.length;
  const pendingApprovalsHelper = approvalsUnavailable
    ? hasCurrentApprovalSnapshot
      ? t("dashboard.lastKnownReadsFailed")
      : t("dashboard.approvalReadsFailedShort")
    : approvalsPartial
      ? t("dashboard.runsReadIncomplete", {
          succeeded: currentApprovalReadSummary?.succeeded ?? 0,
          attempted: currentApprovalReadSummary?.attempted ?? 0
        })
      : t("dashboard.localApprovalsOnly");

  return (
    <div className="page-stack">
      <PageHeader
        title={t("dashboard.title")}
        eyebrow={t("dashboard.eyebrow")}
        description={t("dashboard.description")}
        actions={
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
        }
      />
      {apiError ? <ErrorState error={apiError} /> : null}
      {openError ? <ErrorState error={openError} /> : null}
      {approvalsPartial || approvalsUnavailable ? (
        <div
          className={`state-box ${approvalsUnavailable ? "state-box--error" : "state-box--warning"}`}
          role={approvalsUnavailable ? "alert" : "status"}
        >
          <strong>
            {approvalsUnavailable
              ? t("dashboard.approvalCountsUnavailable")
              : t("dashboard.approvalCountsIncomplete")}
          </strong>
          <span>
            {approvalsUnavailable
              ? `${t("dashboard.noApprovalData", { count: currentApprovalReadSummary?.attempted ?? 0 })}${
                  hasCurrentApprovalSnapshot ? ` ${t("common.showingLastCount")}` : ""
                }`
              : t("dashboard.approvalReadsFailed", {
                  failed: currentApprovalReadSummary?.failures.length ?? 0,
                  attempted: currentApprovalReadSummary?.attempted ?? 0
                })}
          </span>
        </div>
      ) : null}
      <div className="metric-grid">
        <MetricCard
          label={t("dashboard.apiHealth")}
          value={
            apiLoading
              ? t("dashboard.checking")
              : `${health?.status ?? t("common.unknown")}${apiStale ? ` (${t("common.stale")})` : ""}`
          }
          helper={apiStale ? `${apiBaseUrl} / ${t("dashboard.lastRefreshFailed")}` : apiBaseUrl}
          tone={apiStale ? "warn" : health?.status === "ok" ? "good" : "warn"}
        />
        <MetricCard
          label={t("dashboard.providerMode")}
          value={capabilities?.provider_mode ?? t("common.unknown")}
          helper={t("dashboard.fromCapabilities")}
          tone={capabilities?.provider_mode === "mock" ? "info" : "warn"}
        />
        <MetricCard
          label={t("dashboard.modelSelection")}
          value={capabilities?.model_selection.enabled ? t("common.enabled") : t("common.disabled")}
          helper={t("dashboard.modelSelectorHidden")}
          tone={capabilities?.model_selection.enabled ? "warn" : "default"}
        />
        <MetricCard
          label={t("dashboard.availableWorkflows")}
          value={capabilities?.workflows.length ?? 0}
          helper={t("dashboard.backendTemplates")}
          tone="default"
        />
        <MetricCard
          label={t("dashboard.knownRuns")}
          value={knownRunIds.length}
          helper={t("dashboard.localRunIdsOnly")}
          tone="info"
        />
        <MetricCard
          label={t("dashboard.pendingApprovals")}
          value={pendingApprovalsValue}
          helper={pendingApprovalsHelper}
          tone={approvalsUnavailable || approvalsPartial || currentPendingApprovals.length > 0 ? "warn" : "default"}
        />
      </div>
      <div className="content-with-inspector">
        <section className="panel">
          <div className="panel__header">
            <h2>{t("dashboard.sessionSnapshot")}</h2>
            <Link to="/runs">{t("dashboard.openAgentRuns")}</Link>
          </div>
          {runsLoading && !hasCurrentRunSnapshot && !runsUnavailable ? (
            <LoadingState label={t("dashboard.loadingRuns")} />
          ) : null}
          {runsPartial || runsUnavailable ? (
            <div
              className={`state-box ${runsUnavailable ? "state-box--error" : "state-box--warning"}`}
              role={runsUnavailable ? "alert" : "status"}
            >
              <strong>
                {runsUnavailable ? t("dashboard.runSnapshotUnavailable") : t("dashboard.runSnapshotIncomplete")}
              </strong>
              <span>
                {runsUnavailable
                  ? `${t("dashboard.noRunsRead", { count: currentRunReadSummary?.attempted ?? 0 })}${
                      hasCurrentRunSnapshot ? ` ${t("common.showingLastSnapshot")}` : ""
                    }`
                  : t("dashboard.runReadsFailed", {
                      failed: currentRunReadSummary?.failures.length ?? 0,
                      attempted: currentRunReadSummary?.attempted ?? 0
                    })}
              </span>
            </div>
          ) : null}
          {hasCurrentRunSnapshot ? (
            <DataTable
              columns={runColumns}
              rows={currentRunRows}
              rowKey={(row) => row.id}
              emptyLabel={
                runsPartial
                  ? t("dashboard.noReadableSuccessfulRuns")
                  : t("dashboard.noKnownRunsYet")
              }
            />
          ) : null}
        </section>
        <div className="stack">
          <CapabilitiesPanel health={health} capabilities={capabilities} stale={apiStale} />
          <section className="panel">
            <h2>{t("dashboard.lastKnownRun")}</h2>
            {lastKnownRun ? (
              <div className="kv-grid">
                <span>{t("common.runId")}</span>
                <Link to={`/runs/${lastKnownRun.id}`}>{lastKnownRun.id}</Link>
                <span>{t("common.status")}</span>
                <StatusChip
                  label={lastKnownStatus?.label ?? t("common.unknown")}
                  tone={lastKnownStatus?.tone ?? "gray"}
                />
                <span>{t("common.updated")}</span>
                <time>{lastKnownRun.updated_at}</time>
              </div>
            ) : (
              <p className="muted">{t("dashboard.populateLastRun")}</p>
            )}
          </section>
        </div>
      </div>
      <section className="panel">
        <div className="panel__header">
          <h2>{t("dashboard.quickLaunch")}</h2>
          <Link to="/workflows">{t("dashboard.workflowCatalog")}</Link>
        </div>
        <div className="workflow-grid">
          {workflowRegistry.map((workflow) => (
            <WorkflowCard
              key={workflow.key}
              workflow={workflow}
              available={isWorkflowAvailable(workflow, available)}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
