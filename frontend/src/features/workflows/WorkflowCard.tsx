import { Link } from "react-router-dom";
import type { WorkflowDefinition } from "./registry";
import { StatusChip } from "../../components/status/StatusChip";
import { useLocale } from "../../i18n/LocaleProvider";

type WorkflowCardProps = {
  workflow: WorkflowDefinition;
  available: boolean;
};

export function WorkflowCard({ workflow, available }: WorkflowCardProps) {
  const { t } = useLocale();
  return (
    <article className="workflow-card">
      <div className="workflow-card__header">
        <div>
          <h2>{t(workflow.titleKey)}</h2>
          <code>{workflow.requestType}</code>
        </div>
        <StatusChip
          label={available ? t("workflows.card.available") : t("workflows.card.notReturned")}
          tone={available ? "green" : "gray"}
        />
      </div>
      <p>{t(workflow.descriptionKey)}</p>
      <div className="workflow-card__footer">
        <code>{workflow.endpoint}</code>
        <Link className="action-button action-button--primary" to={workflow.route}>
          {t("workflows.card.open")}
        </Link>
      </div>
    </article>
  );
}
