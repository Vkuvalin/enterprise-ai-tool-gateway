import { Link } from "react-router-dom";
import type { WorkflowDefinition } from "./registry";
import { StatusChip } from "../../components/status/StatusChip";

type WorkflowCardProps = {
  workflow: WorkflowDefinition;
  available: boolean;
};

export function WorkflowCard({ workflow, available }: WorkflowCardProps) {
  return (
    <article className="workflow-card">
      <div className="workflow-card__header">
        <div>
          <h2>{workflow.title}</h2>
          <code>{workflow.requestType}</code>
        </div>
        <StatusChip label={available ? "available" : "not returned"} tone={available ? "green" : "gray"} />
      </div>
      <p>{workflow.description}</p>
      <div className="workflow-card__footer">
        <code>{workflow.endpoint}</code>
        <Link className="action-button action-button--primary" to={workflow.route}>
          Open
        </Link>
      </div>
    </article>
  );
}
