import type { RunResponse } from "../../api/types";
import { InspectorPanel } from "../../components/data/InspectorPanel";
import { RiskBadge } from "../../components/status/RiskBadge";
import { StatusChip } from "../../components/status/StatusChip";
import { getRunStatusPresentation } from "../../components/status/statusPresentation";
import { RunLinks } from "./RunLinks";

type RunSummaryPanelProps = {
  run: RunResponse;
  showDetailLink?: boolean;
  showLinks?: boolean;
};

export function RunSummaryPanel({ run, showDetailLink = true, showLinks = true }: RunSummaryPanelProps) {
  const status = getRunStatusPresentation(run.status);

  return (
    <InspectorPanel title="Run Summary">
      <div className="kv-grid">
        <span>Run ID</span>
        <code>{run.id}</code>
        <span>Request type</span>
        <code>{run.request_type}</code>
        <span>Domain template</span>
        <code>{run.domain_template}</code>
        <span>Status</span>
        <StatusChip label={status.label} tone={status.tone} title={status.description} />
        <span>Risk</span>
        <RiskBadge risk={run.risk_level} />
        <span>Approval mode</span>
        <code>{run.approval_mode}</code>
        <span>Requires approval</span>
        <span>{run.requires_approval ? "yes" : "no"}</span>
        <span>Provider</span>
        <code>{run.provider_name ?? "not returned"}</code>
        <span>Model</span>
        <code>{run.model_name ?? "not returned"}</code>
        <span>Created</span>
        <time>{run.created_at}</time>
        <span>Updated</span>
        <time>{run.updated_at}</time>
      </div>
      {showLinks ? <RunLinks runId={run.id} showDetailLink={showDetailLink} /> : null}
    </InspectorPanel>
  );
}
