import type { CapabilitiesResponse, HealthResponse } from "../../api/types";
import { InspectorPanel } from "../../components/data/InspectorPanel";
import { JsonViewer } from "../../components/data/JsonViewer";
import { StatusChip } from "../../components/status/StatusChip";
import { useLocale } from "../../i18n/LocaleProvider";

type CapabilitiesPanelProps = {
  health: HealthResponse | null;
  capabilities: CapabilitiesResponse | null;
  stale?: boolean;
};

export function CapabilitiesPanel({ health, capabilities, stale = false }: CapabilitiesPanelProps) {
  const { t } = useLocale();
  return (
    <InspectorPanel title={t("capabilities.title")}>
      <div className="kv-grid">
        <span>{t("common.health")}</span>
        <StatusChip
          label={`${health?.status ?? t("common.unknown")}${stale ? ` (${t("common.stale")})` : ""}`}
          tone={stale ? "orange" : health?.status === "ok" ? "green" : "gray"}
          title={stale ? t("capabilities.lastRefreshFailed") : undefined}
        />
        <span>{t("common.providerMode")}</span>
        <StatusChip label={capabilities?.provider_mode ?? t("common.unknown")} tone="purple" />
        <span>{t("common.modelSelection")}</span>
        <StatusChip
          label={capabilities?.model_selection.enabled ? t("common.enabled") : t("common.disabled")}
          tone={capabilities?.model_selection.enabled ? "orange" : "gray"}
        />
        <span>{t("common.workflows")}</span>
        <span>{capabilities?.workflows.length ?? 0}</span>
      </div>
      <JsonViewer value={capabilities ?? null} label={t("capabilities.response")} />
    </InspectorPanel>
  );
}
