import { FormEvent, useState } from "react";
import { toDisplayError } from "../api/errors";
import type { NormalizedApiError, ProcurementSubmitRequest, WorkflowResultResponse } from "../api/types";
import { ErrorState } from "../components/feedback/ErrorState";
import { ActionButton } from "../components/forms/ActionButton";
import { PageHeader } from "../components/layout/PageHeader";
import { useApiStatus } from "../features/capabilities/useApiStatus";
import { WorkflowResultPanel } from "../features/workflows/WorkflowResultPanel";
import { WorkflowSafetyPanel } from "../features/workflows/WorkflowSafetyPanel";
import { getWorkflowByKey } from "../features/workflows/registry";
import { addKnownRunId } from "../state/knownRuns";

const workflow = getWorkflowByKey("procurement");

export function ProcurementRequestPage() {
  const { capabilities } = useApiStatus();
  const approvalModes = capabilities?.approval_modes ?? ["HIGH_RISK_ONLY"];
  const [form, setForm] = useState<ProcurementSubmitRequest>({
    user_id: "user-1",
    request_text: "Need to buy equipment.",
    requester_id: "req-001",
    item_id: "item-laptop",
    item_name: "Laptop",
    quantity: 1,
    estimated_total: 900,
    currency: "USD",
    cost_center: "cc-ops",
    justification: "Need equipment.",
    preferred_vendor_id: "vendor-approved-001",
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
      <PageHeader title="Procurement Request" eyebrow="Workflow submit" description={workflow.description} />
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
              Item ID
              <input
                value={form.item_id ?? ""}
                onChange={(event) => setForm({ ...form, item_id: event.target.value || null })}
              />
            </label>
            <label>
              Item name
              <input
                value={form.item_name ?? ""}
                onChange={(event) => setForm({ ...form, item_name: event.target.value || null })}
              />
            </label>
            <label>
              Quantity
              <input
                type="number"
                min={1}
                value={form.quantity ?? ""}
                onChange={(event) =>
                  setForm({ ...form, quantity: event.target.value ? Number(event.target.value) : null })
                }
              />
            </label>
            <label>
              Estimated total
              <input
                type="number"
                min={0}
                value={form.estimated_total ?? ""}
                onChange={(event) =>
                  setForm({ ...form, estimated_total: event.target.value ? Number(event.target.value) : null })
                }
              />
            </label>
            <label>
              Currency
              <input value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value })} />
            </label>
            <label>
              Cost center
              <input
                value={form.cost_center ?? ""}
                onChange={(event) => setForm({ ...form, cost_center: event.target.value || null })}
              />
            </label>
            <label>
              Preferred vendor
              <input
                value={form.preferred_vendor_id ?? ""}
                onChange={(event) => setForm({ ...form, preferred_vendor_id: event.target.value || null })}
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
            {submitting ? "Submitting..." : "Submit procurement request"}
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
