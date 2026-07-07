import type { WorkflowResultResponse } from "../../api/types";
import { InspectorPanel } from "../../components/data/InspectorPanel";
import { JsonViewer } from "../../components/data/JsonViewer";
import { RiskBadge } from "../../components/status/RiskBadge";
import { StatusChip } from "../../components/status/StatusChip";
import { getRunStatusPresentation } from "../../components/status/statusPresentation";
import { RunLinks } from "../runs/RunLinks";

type WorkflowResultPanelProps = {
  result: WorkflowResultResponse | null;
};

export function WorkflowResultPanel({ result }: WorkflowResultPanelProps) {
  if (!result) {
    return (
      <InspectorPanel title="Submit Result">
        <p className="muted">Submit a workflow to create or inspect a controlled backend run.</p>
      </InspectorPanel>
    );
  }

  const status = getRunStatusPresentation(result.run.status);

  return (
    <InspectorPanel title="Submit Result">
      <div className="kv-grid">
        <span>Run ID</span>
        <code>{result.run.id}</code>
        <span>Status</span>
        <StatusChip label={status.label} tone={status.tone} title={status.description} />
        <span>Risk</span>
        <RiskBadge risk={result.run.risk_level} />
        <span>Requires approval</span>
        <span>{result.requires_approval ? "yes" : "no"}</span>
        <span>Tool calls</span>
        <span>{result.tool_calls.length}</span>
        <span>Audit events</span>
        <span>{result.audit_events.length}</span>
      </div>
      {result.run.status === "FAILED_TOOL" ? (
        <div className="state-box state-box--error">
          <strong>Controlled tool failure</strong>
          <span>
            The backend kept execution inside the gateway boundary and returned a safe tool-failure state instead of
            hiding or retrying the failure in the client.
          </span>
        </div>
      ) : null}
      {result.final_summary ? <p>{result.final_summary}</p> : null}
      <RunLinks runId={result.run.id} />
      {result.approval ? <JsonViewer value={result.approval} label="Approval" /> : null}
    </InspectorPanel>
  );
}
