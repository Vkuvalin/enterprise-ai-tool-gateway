import type { CapabilitiesResponse, HealthResponse } from "../../api/types";
import { InspectorPanel } from "../../components/data/InspectorPanel";
import { JsonViewer } from "../../components/data/JsonViewer";
import { StatusChip } from "../../components/status/StatusChip";

type CapabilitiesPanelProps = {
  health: HealthResponse | null;
  capabilities: CapabilitiesResponse | null;
};

export function CapabilitiesPanel({ health, capabilities }: CapabilitiesPanelProps) {
  return (
    <InspectorPanel title="API Status">
      <div className="kv-grid">
        <span>Health</span>
        <StatusChip label={health?.status ?? "unknown"} tone={health?.status === "ok" ? "green" : "gray"} />
        <span>Provider mode</span>
        <StatusChip label={capabilities?.provider_mode ?? "unknown"} tone="purple" />
        <span>Model selection</span>
        <StatusChip
          label={capabilities?.model_selection.enabled ? "enabled" : "disabled"}
          tone={capabilities?.model_selection.enabled ? "orange" : "gray"}
        />
        <span>Workflows</span>
        <span>{capabilities?.workflows.length ?? 0}</span>
      </div>
      <JsonViewer value={capabilities ?? null} label="Capabilities response" />
    </InspectorPanel>
  );
}
