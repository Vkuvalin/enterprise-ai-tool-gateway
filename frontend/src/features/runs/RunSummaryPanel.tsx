import type { RunResponse } from "../../api/types";
import { InspectorPanel } from "../../components/data/InspectorPanel";
import { RiskBadge } from "../../components/status/RiskBadge";
import { StatusChip } from "../../components/status/StatusChip";
import { getRunStatusPresentation } from "../../components/status/statusPresentation";
import { RunLinks } from "./RunLinks";
import { useLocale } from "../../i18n/LocaleProvider";

type RunSummaryPanelProps = {
  run: RunResponse;
  showDetailLink?: boolean;
  showLinks?: boolean;
};

export function RunSummaryPanel({ run, showDetailLink = true, showLinks = true }: RunSummaryPanelProps) {
  const { t } = useLocale();
  const status = getRunStatusPresentation(run.status, t);

  return (
    <InspectorPanel title={t("runSummary.title")}>
      <div className="kv-grid">
        <span>{t("common.runId")}</span>
        <code>{run.id}</code>
        <span>{t("common.requestType")}</span>
        <code>{run.request_type}</code>
        <span>{t("runSummary.domainTemplate")}</span>
        <code>{run.domain_template}</code>
        <span>{t("common.status")}</span>
        <StatusChip label={status.label} tone={status.tone} title={status.description} />
        <span>{t("common.risk")}</span>
        <RiskBadge risk={run.risk_level} />
        <span>{t("common.approvalMode")}</span>
        <code>{run.approval_mode}</code>
        <span>{t("common.requiresApproval")}</span>
        <span>{run.requires_approval ? t("common.yes") : t("common.no")}</span>
        <span>{t("common.provider")}</span>
        <code>{run.provider_name ?? t("common.notReturned")}</code>
        <span>{t("common.model")}</span>
        <code>{run.model_name ?? t("common.notReturned")}</code>
        <span>{t("common.created")}</span>
        <time>{run.created_at}</time>
        <span>{t("common.updated")}</span>
        <time>{run.updated_at}</time>
      </div>
      {showLinks ? <RunLinks runId={run.id} showDetailLink={showDetailLink} /> : null}
    </InspectorPanel>
  );
}
