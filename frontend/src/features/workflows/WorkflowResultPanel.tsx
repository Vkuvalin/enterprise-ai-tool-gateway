import type { WorkflowResultResponse } from "../../api/types";
import { InspectorPanel } from "../../components/data/InspectorPanel";
import { JsonViewer } from "../../components/data/JsonViewer";
import { RiskBadge } from "../../components/status/RiskBadge";
import { StatusChip } from "../../components/status/StatusChip";
import { getRunStatusPresentation } from "../../components/status/statusPresentation";
import { useLocale } from "../../i18n/LocaleProvider";
import { RunLinks } from "../runs/RunLinks";

type WorkflowResultPanelProps = {
  result: WorkflowResultResponse | null;
};

export function WorkflowResultPanel({ result }: WorkflowResultPanelProps) {
  const { t } = useLocale();
  if (!result) {
    return (
      <InspectorPanel title={t("workflows.result.title")}>
        <p className="muted">{t("workflows.result.emptyHint")}</p>
      </InspectorPanel>
    );
  }

  const status = getRunStatusPresentation(result.run.status, t);

  return (
    <InspectorPanel title={t("workflows.result.title")}>
      <div className="kv-grid">
        <span>{t("common.runId")}</span>
        <code>{result.run.id}</code>
        <span>{t("common.status")}</span>
        <StatusChip label={status.label} tone={status.tone} title={status.description} />
        <span>{t("common.risk")}</span>
        <RiskBadge risk={result.run.risk_level} />
        <span>{t("common.requiresApproval")}</span>
        <span>{result.requires_approval ? t("common.yes") : t("common.no")}</span>
        <span>{t("common.toolCalls")}</span>
        <span>{result.tool_calls.length}</span>
        <span>{t("common.auditEvents")}</span>
        <span>{result.audit_events.length}</span>
      </div>
      {result.run.status === "FAILED_TOOL" ? (
        <div className="state-box state-box--error">
          <strong>{t("workflows.result.controlledToolFailure")}</strong>
          <span>{t("workflows.result.controlledToolFailureDescription")}</span>
        </div>
      ) : null}
      {result.final_summary ? <p>{result.final_summary}</p> : null}
      <RunLinks runId={result.run.id} />
      {result.approval ? <JsonViewer value={result.approval} label={t("workflows.result.approval")} /> : null}
    </InspectorPanel>
  );
}
