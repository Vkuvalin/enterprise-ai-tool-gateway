import { FormEvent, useState } from "react";
import { toDisplayError } from "../api/errors";
import type { MaintenanceSubmitRequest, NormalizedApiError, WorkflowResultResponse } from "../api/types";
import { ErrorState } from "../components/feedback/ErrorState";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { useApiStatus } from "../features/capabilities/useApiStatus";
import { WorkflowResultPanel } from "../features/workflows/WorkflowResultPanel";
import { WorkflowSafetyPanel } from "../features/workflows/WorkflowSafetyPanel";
import { getWorkflowByKey } from "../features/workflows/registry";
import { addKnownRunId } from "../state/knownRuns";

const workflow = getWorkflowByKey("maintenance");

export function MaintenanceRequestPage() {
  const { capabilities } = useApiStatus();
  const approvalModes = capabilities?.approval_modes ?? ["HIGH_RISK_ONLY"];
  const [form, setForm] = useState<MaintenanceSubmitRequest>({
    user_id: "user-1",
    request_text: "Routine inspection for Cooling pump 1.",
    requester_id: "maint-req-001",
    asset_id: "asset-pump-001",
    asset_name: "Cooling pump 1",
    issue_description: "Routine inspection needed.",
    location: "Plant A",
    observed_severity: "LOW",
    safety_concern: false,
    approval_mode: "HIGH_RISK_ONLY"
  });
  const [result, setResult] = useState<WorkflowResultResponse | null>(null);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await workflow.submit(form);
      addKnownRunId(response.run.id);
      setResult(response);
    } catch (nextError) {
      setError(toDisplayError(nextError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="Maintenance Request"
        eyebrow="Workflow submit"
        description={`${workflow.description} Defaults use an active requester, active asset, low severity, and no safety concern for a successful demo path.`}
      />
      <div className="content-with-inspector">
        <form className="form-panel" onSubmit={(event) => void onSubmit(event)}>
          <label>
            User ID
            <input value={form.user_id} onChange={(event) => setForm({ ...form, user_id: event.target.value })} />
          </label>
          <label>
            Request text
            <textarea
              value={form.request_text}
              onChange={(event) => setForm({ ...form, request_text: event.target.value })}
              rows={4}
            />
          </label>
          <div className="form-grid">
            <label>
              Requester ID
              <input
                value={form.requester_id ?? ""}
                onChange={(event) => setForm({ ...form, requester_id: event.target.value || null })}
              />
            </label>
            <label>
              Asset ID
              <input
                value={form.asset_id ?? ""}
                onChange={(event) => setForm({ ...form, asset_id: event.target.value || null })}
              />
            </label>
            <label>
              Asset name
              <input
                value={form.asset_name ?? ""}
                onChange={(event) => setForm({ ...form, asset_name: event.target.value || null })}
              />
            </label>
            <label>
              Location
              <input
                value={form.location ?? ""}
                onChange={(event) => setForm({ ...form, location: event.target.value || null })}
              />
            </label>
            <label>
              Observed severity
              <select
                value={form.observed_severity ?? ""}
                onChange={(event) =>
                  setForm({
                    ...form,
                    observed_severity: event.target.value
                      ? (event.target.value as MaintenanceSubmitRequest["observed_severity"])
                      : null
                  })
                }
              >
                <option value="LOW">LOW</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HIGH">HIGH</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
            </label>
            <label>
              Approval mode
              <select
                value={form.approval_mode}
                onChange={(event) => setForm({ ...form, approval_mode: event.target.value })}
              >
                {approvalModes.map((mode) => (
                  <option key={mode} value={mode}>
                    {mode}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Issue description
            <textarea
              value={form.issue_description ?? ""}
              onChange={(event) => setForm({ ...form, issue_description: event.target.value || null })}
              rows={3}
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={Boolean(form.safety_concern)}
              onChange={(event) => setForm({ ...form, safety_concern: event.target.checked })}
            />
            Safety concern
          </label>
          {error ? <ErrorState error={error} /> : null}
          <ActionButton type="submit" variant="primary" disabled={submitting}>
            {submitting ? "Submitting..." : "Submit maintenance request"}
          </ActionButton>
        </form>
        <div className="stack">
          <WorkflowSafetyPanel workflow={workflow} approvalModes={approvalModes} />
          <WorkflowResultPanel result={result} />
        </div>
      </div>
    </div>
  );
}
