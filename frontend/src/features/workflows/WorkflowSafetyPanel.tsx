import type { WorkflowDefinition } from "./registry";
import { InspectorPanel } from "../../components/data/InspectorPanel";
import { StatusChip } from "../../components/status/StatusChip";

type WorkflowSafetyPanelProps = {
  workflow: WorkflowDefinition;
  approvalModes: string[];
};

export function WorkflowSafetyPanel({ workflow, approvalModes }: WorkflowSafetyPanelProps) {
  return (
    <InspectorPanel title="Control Boundary">
      <div className="kv-grid">
        <span>Endpoint</span>
        <code>{workflow.endpoint}</code>
        <span>Request type</span>
        <code>{workflow.requestType}</code>
        <span>Approval modes</span>
        <span>{approvalModes.join(", ") || "not loaded"}</span>
        <span>Provider fields</span>
        <StatusChip label="not in payload" tone="gray" />
      </div>
      <div className="note-list">
        {workflow.safetyNotes.map((note) => (
          <p key={note}>{note}</p>
        ))}
      </div>
    </InspectorPanel>
  );
}
