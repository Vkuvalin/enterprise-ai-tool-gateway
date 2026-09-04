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
import { useLocale } from "../i18n/LocaleProvider";
import { getApprovalModeLabel } from "../i18n/presentation";
import { addKnownRunId } from "../state/knownRuns";

const workflow = getWorkflowByKey("procurement");

export function ProcurementRequestPage() {
  const { t } = useLocale();
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
      <PageHeader
        title={t(workflow.titleKey)}
        eyebrow={t("workflows.form.eyebrow")}
        description={t(workflow.descriptionKey)}
      />
      <div className="content-with-inspector">
        <form className="form-panel" onSubmit={(event) => void onSubmit(event)}>
          <label>
            {t("workflows.form.userId")}
            <input value={form.user_id} onChange={(event) => setForm({ ...form, user_id: event.target.value })} />
          </label>
          <label>
            {t("workflows.form.requestText")}
            <textarea
              value={form.request_text}
              onChange={(event) => setForm({ ...form, request_text: event.target.value })}
              rows={4}
            />
          </label>
          <div className="form-grid">
            <label>
              {t("workflows.procurement.requesterId")}
              <input
                value={form.requester_id ?? ""}
                onChange={(event) => setForm({ ...form, requester_id: event.target.value || null })}
              />
            </label>
            <label>
              {t("workflows.procurement.itemId")}
              <input
                value={form.item_id ?? ""}
                onChange={(event) => setForm({ ...form, item_id: event.target.value || null })}
              />
            </label>
            <label>
              {t("workflows.procurement.itemName")}
              <input
                value={form.item_name ?? ""}
                onChange={(event) => setForm({ ...form, item_name: event.target.value || null })}
              />
            </label>
            <label>
              {t("workflows.procurement.quantity")}
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
              {t("workflows.procurement.estimatedTotal")}
              <input
                type="number"
                min={0}
                step="any"
                value={form.estimated_total ?? ""}
                onChange={(event) =>
                  setForm({ ...form, estimated_total: event.target.value ? Number(event.target.value) : null })
                }
              />
            </label>
            <label>
              {t("workflows.procurement.currency")}
              <input value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value })} />
            </label>
            <label>
              {t("workflows.procurement.costCenter")}
              <input
                value={form.cost_center ?? ""}
                onChange={(event) => setForm({ ...form, cost_center: event.target.value || null })}
              />
            </label>
            <label>
              {t("workflows.procurement.preferredVendor")}
              <input
                value={form.preferred_vendor_id ?? ""}
                onChange={(event) => setForm({ ...form, preferred_vendor_id: event.target.value || null })}
              />
            </label>
            <label>
              {t("workflows.form.approvalMode")}
              <select
                value={form.approval_mode}
                onChange={(event) => setForm({ ...form, approval_mode: event.target.value })}
              >
                {approvalModes.map((mode) => (
                  <option key={mode} value={mode}>
                    {getApprovalModeLabel(mode, t)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            {t("workflows.form.justification")}
            <textarea
              value={form.justification ?? ""}
              onChange={(event) => setForm({ ...form, justification: event.target.value || null })}
              rows={3}
            />
          </label>
          {error ? <ErrorState error={error} /> : null}
          <ActionButton type="submit" variant="primary" disabled={submitting}>
            {submitting ? t("workflows.form.submitting") : t("workflows.procurement.submit")}
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
