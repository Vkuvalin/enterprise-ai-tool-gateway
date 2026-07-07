import { Link } from "react-router-dom";

type RunLinksProps = {
  runId: string;
  showDetailLink?: boolean;
};

export function RunLinks({ runId, showDetailLink = true }: RunLinksProps) {
  return (
    <div className="run-links">
      {showDetailLink ? <Link to={`/runs/${runId}`}>Run Detail</Link> : null}
      <Link to={`/runs/${runId}/approvals`}>Approvals</Link>
      <Link to={`/runs/${runId}/tool-calls`}>Tool Calls</Link>
      <Link to={`/runs/${runId}/audit`}>Audit Trail</Link>
    </div>
  );
}
