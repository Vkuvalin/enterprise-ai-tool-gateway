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
import { useLocale } from "../i18n/LocaleProvider";
import { getAccessLevelLabel, getApprovalModeLabel } from "../i18n/presentation";
import { addKnownRunId } from "../state/knownRuns";

const workflow = getWorkflowByKey("access");

export function AccessRequestPage() {
  const { t } = useLocale();
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
              {t("workflows.access.employeeId")}
              <input
                value={form.employee_id ?? ""}
                onChange={(event) => setForm({ ...form, employee_id: event.target.value || null })}
              />
            </label>
            <label>
              {t("workflows.access.systemId")}
              <input
                value={form.system_id ?? ""}
                onChange={(event) => setForm({ ...form, system_id: event.target.value || null })}
              />
            </label>
            <label>
              {t("workflows.access.accessLevel")}
              <select
                value={form.access_level ?? ""}
                onChange={(event) =>
                  setForm({ ...form, access_level: event.target.value as AccessSubmitRequest["access_level"] })
                }
              >
                <option value="READ">{getAccessLevelLabel("READ", t)}</option>
                <option value="WRITE">{getAccessLevelLabel("WRITE", t)}</option>
                <option value="ADMIN">{getAccessLevelLabel("ADMIN", t)}</option>
              </select>
            </label>
            <label>
              {t("workflows.access.durationDays")}
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
            {submitting ? t("workflows.form.submitting") : t("workflows.access.submit")}
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
