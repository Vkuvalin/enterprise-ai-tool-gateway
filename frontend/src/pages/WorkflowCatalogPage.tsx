import { useApiStatus } from "../features/capabilities/useApiStatus";
import { PageHeader } from "../components/layout/PageHeader";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { WorkflowCard } from "../features/workflows/WorkflowCard";
import { isWorkflowAvailable, workflowRegistry } from "../features/workflows/registry";

export function WorkflowCatalogPage() {
  const { capabilities, loading, error } = useApiStatus();
  const available = capabilities?.workflows ?? null;

  return (
    <div className="page-stack">
      <PageHeader
        title="Workflow Catalog"
        eyebrow="Supported templates"
        description="Only backend-supported workflow submit screens are exposed."
      />
      {loading ? <LoadingState label="Loading capabilities..." /> : null}
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
