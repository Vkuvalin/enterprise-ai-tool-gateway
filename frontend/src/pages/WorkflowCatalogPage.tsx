import { useApiStatus } from "../features/capabilities/useApiStatus";
import { PageHeader } from "../components/layout/PageHeader";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { WorkflowCard } from "../features/workflows/WorkflowCard";
import { isWorkflowAvailable, workflowRegistry } from "../features/workflows/registry";
import { useLocale } from "../i18n/LocaleProvider";

export function WorkflowCatalogPage() {
  const { t } = useLocale();
  const { capabilities, loading, error } = useApiStatus();
  const available = capabilities?.workflows ?? null;

  return (
    <div className="page-stack">
      <PageHeader
        title={t("workflows.catalog.title")}
        eyebrow={t("workflows.catalog.eyebrow")}
        description={t("workflows.catalog.description")}
      />
      {loading ? <LoadingState label={t("workflows.catalog.loading")} /> : null}
      {error ? <ErrorState error={error} /> : null}
      <div className="workflow-grid">
        {workflowRegistry.map((workflow) => (
          <WorkflowCard
            key={workflow.key}
            workflow={workflow}
            available={isWorkflowAvailable(workflow, available)}
          />
        ))}
      </div>
    </div>
  );
}
