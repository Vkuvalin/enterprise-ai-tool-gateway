import type { WorkflowDefinition } from "./registry";
import { InspectorPanel } from "../../components/data/InspectorPanel";
import { StatusChip } from "../../components/status/StatusChip";
import { useLocale } from "../../i18n/LocaleProvider";

type WorkflowSafetyPanelProps = {
  workflow: WorkflowDefinition;
  approvalModes: string[];
};

export function WorkflowSafetyPanel({ workflow, approvalModes }: WorkflowSafetyPanelProps) {
  const { t } = useLocale();
  return (
    <InspectorPanel title={t("workflows.safety.title")}>
      <div className="kv-grid">
        <span>{t("workflows.safety.endpoint")}</span>
        <code>{workflow.endpoint}</code>
        <span>{t("workflows.safety.requestType")}</span>
        <code>{workflow.requestType}</code>
        <span>{t("workflows.safety.approvalModes")}</span>
        <span>{approvalModes.join(", ") || t("workflows.safety.notLoaded")}</span>
        <span>{t("workflows.safety.providerFields")}</span>
        <StatusChip label={t("workflows.safety.notInPayload")} tone="gray" />
      </div>
      <div className="note-list">
        {workflow.safetyNoteKeys.map((noteKey) => (
          <p key={noteKey}>{t(noteKey)}</p>
        ))}
      </div>
    </InspectorPanel>
  );
}
