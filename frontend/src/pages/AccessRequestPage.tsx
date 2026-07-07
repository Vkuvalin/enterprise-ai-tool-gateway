import { FormEvent, useState } from "react";
import { toDisplayError } from "../api/errors";
import type { AccessSubmitRequest, NormalizedApiError, WorkflowResultResponse } from "../api/types";
import { ErrorState } from "../components/feedback/ErrorState";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { useApiStatus } from "../features/capabilities/useApiStatus";
import { WorkflowResultPanel } from "../features/workflows/WorkflowResultPanel";
import { WorkflowSafetyPanel } from "../features/workflows/WorkflowSafetyPanel";
import { getWorkflowByKey } from "../features/workflows/registry";
import { addKnownRunId } from "../state/knownRuns";

const workflow = getWorkflowByKey("access");

export function AccessRequestPage() {
  const { capabilities } = useApiStatus();
  const approvalModes = capabilities?.approval_modes ?? ["HIGH_RISK_ONLY"];
  const [form, setForm] = useState<AccessSubmitRequest>({
    user_id: "user-1",
    request_text: "Need access to CRM.",
    employee_id: "emp-001",
    system_id: "crm",
    access_level: "READ",
    duration_days: 30,
    justification: "Need access for routine work.",
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
      <PageHeader title="Access Request" eyebrow="Workflow submit" description={workflow.description} />
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
              Employee ID
              <input
                value={form.employee_id ?? ""}
                onChange={(event) => setForm({ ...form, employee_id: event.target.value || null })}
              />
            </label>
            <label>
              System ID
              <input
                value={form.system_id ?? ""}
                onChange={(event) => setForm({ ...form, system_id: event.target.value || null })}
              />
            </label>
            <label>
              Access level
              <select
                value={form.access_level ?? ""}
                onChange={(event) =>
                  setForm({ ...form, access_level: event.target.value as AccessSubmitRequest["access_level"] })
                }
              >
                <option value="READ">READ</option>
                <option value="WRITE">WRITE</option>
                <option value="ADMIN">ADMIN</option>
              </select>
            </label>
            <label>
              Duration days
              <input
                type="number"
                min={1}
                value={form.duration_days ?? ""}
                onChange={(event) =>
                  setForm({ ...form, duration_days: event.target.value ? Number(event.target.value) : null })
                }
              />
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
            Justification
            <textarea
              value={form.justification ?? ""}
              onChange={(event) => setForm({ ...form, justification: event.target.value || null })}
              rows={3}
            />
          </label>
          {error ? <ErrorState error={error} /> : null}
          <ActionButton type="submit" variant="primary" disabled={submitting}>
            {submitting ? "Submitting..." : "Submit access request"}
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
