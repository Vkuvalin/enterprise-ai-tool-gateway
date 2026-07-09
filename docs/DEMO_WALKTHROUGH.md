# Demo Walkthrough

## 1. Demo purpose

This walkthrough shows how to run the local Enterprise AI Tool Gateway demo and
inspect the controlled lifecycle of three synthetic workflows.

After the walkthrough, the reviewer should understand the core control model:

```text
LLM proposes.
Backend validates.
Tools execute through controlled boundaries.
Approval gates risky actions.
Audit records lifecycle evidence.
Frontend displays the controlled lifecycle over /api/v1.
```

The demo is local and synthetic. It demonstrates backend ownership of
validation, tool boundaries, policy checks, approvals, audit records and public
API readback. It is not production SaaS and it does not integrate with real
enterprise systems.

## 2. Before you start

Prerequisites:

* a local checkout of this repository;
* Python and `uv` for the backend;
* Node.js and npm for the frontend;
* frontend dependencies installed if this is the first run;
* no real provider credentials for the default demo.

The default provider mode is `mock`. Real-provider credentials are not needed
for the API, frontend or eval walkthrough.

If frontend dependencies are missing, install them once:

```bash
cd frontend
npm install
```

Fastest Windows start:

```text
run_demo.cmd
```

The runner starts both local services, waits for readiness and opens the
dashboard. Use the manual commands below as the fallback path or when separate
terminals are preferred.

## 3. Start the backend

From the repository root, start the FastAPI backend:

```bash
uv run uvicorn enterprise_ai_tool_gateway.api.http.app:app --reload
```

The local API is versioned under `/api/v1`.

Check backend health and capability metadata:

```text
GET http://127.0.0.1:8000/api/v1/health
GET http://127.0.0.1:8000/api/v1/capabilities
```

Expected health response:

```json
{"status": "ok"}
```

The backend root URL can return 404:

```text
GET http://127.0.0.1:8000/
```

That is normal. The backend does not serve the frontend root page.

## 4. Start the frontend

In a second terminal, start the Vite frontend:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open the main UI:

```text
http://127.0.0.1:5173/dashboard
```

The frontend API client calls `/api/v1` by default. Vite proxies `/api` to the
backend at `http://localhost:8000`, so browser requests to `/api/v1/...` reach
the FastAPI `/api/v1` endpoints.

## 5. First screen: Dashboard and Settings

On `/dashboard`, verify the main local demo indicators:

* `API Health` is `ok`;
* `Provider Mode` is `mock`;
* `Model Selection` is `disabled`;
* `Available Workflows` includes the three backend-supported workflows;
* `Known Runs` and `Pending Approvals` refer only to run IDs known in this
  browser session.

Open `/settings` and inspect `Settings / API Status`:

* `API base URL` should be `/api/v1` unless overridden by environment;
* `Health` should be `ok`;
* `Provider mode` should be `mock`;
* `Model selection` should be `disabled`;
* the capabilities JSON should show `model_selection.enabled: false`,
  `active_profile: "mock"` and `available_profiles: ["mock"]`.

The UI is a local operations console over the backend API. It does not execute
tools, evaluate policy, call providers directly or read the SQLite database.

## 6. Scenario A - Access happy path

Open:

```text
http://127.0.0.1:5173/workflows/access
```

Use the default known-good values:

| Field | Value |
| --- | --- |
| User ID | `user-1` |
| Request text | `Need access to CRM.` |
| Employee ID | `emp-001` |
| System ID | `crm` |
| Access level | `READ` |
| Duration days | `30` |
| Approval mode | `HIGH_RISK_ONLY` |
| Justification | `Need access for routine work.` |

Submit with `Submit access request`.

Expected controlled outcome:

* status: `COMPLETED`;
* `Requires approval`: `no`;
* a synthetic draft output is created by the backend-controlled tool path.

Open the run links from the submit result:

* `Run Detail`;
* `Tool Calls`;
* `Audit Trail`.

In Run Detail, verify the controlled outcome, final summary, risk and record
counts. In Tool Calls, verify that access checks and the draft action are shown
as backend tool records with statuses and redacted payload JSON. In Audit Trail,
verify lifecycle events such as run creation, policy check and completion.

This proves the happy path: the provider proposes a structured access decision,
the backend validates it, read tools run through registered boundaries, policy
allows the draft action and audit records the lifecycle.

If you change `Access level` to `ADMIN`, the same workflow should move into a
controlled approval path instead of directly completing.

## 7. Scenario B - Procurement approval path

Open:

```text
http://127.0.0.1:5173/workflows/procurement
```

Start from the default form and change these fields to the reliable approval
case:

| Field | Value |
| --- | --- |
| Item ID | `item-service` |
| Item name | `Implementation services` |
| Estimated total | `1500` |

Keep the other default values:

| Field | Value |
| --- | --- |
| User ID | `user-1` |
| Request text | `Need to buy equipment.` |
| Requester ID | `req-001` |
| Quantity | `1` |
| Currency | `USD` |
| Cost center | `cc-ops` |
| Preferred vendor | `vendor-approved-001` |
| Approval mode | `HIGH_RISK_ONLY` |
| Justification | `Need equipment.` |

Submit with `Submit procurement request`.

Expected initial controlled outcome:

* status: `WAITING_FOR_APPROVAL`;
* `Requires approval`: `yes`;
* a pending approval is returned;
* the purchase request draft action has not executed yet.

Open:

```text
/runs/{run_id}/approvals
```

Select the pending approval. The form has `Decided by` defaulted to
`manager-001`. Choose one branch:

* click `Approve` to resolve the approval and complete the run;
* click `Reject` to reject the run without a draft;
* click `Cancel` to cancel the approval and reject the run without a draft.

After approving, refresh or open Run Detail and expect final status
`COMPLETED`. After rejecting or cancelling, expect final status `REJECTED`.

Inspect Tool Calls:

* before approval, the draft action should not have succeeded;
* after approval, the draft action can succeed and produce a synthetic draft;
* after rejection or cancellation, no draft is created.

Inspect Audit Trail for approval request, approval decision and final lifecycle
events. This proves that high-value procurement does not create a draft before
approval, and approval resolution is handled by the backend API rather than by
local UI logic.

## 8. Scenario C - Maintenance default/safe path

Open:

```text
http://127.0.0.1:5173/workflows/maintenance
```

Use the default known-good values:

| Field | Value |
| --- | --- |
| User ID | `user-1` |
| Request text | `Routine inspection for Cooling pump 1.` |
| Requester ID | `maint-req-001` |
| Asset ID | `asset-pump-001` |
| Asset name | `Cooling pump 1` |
| Location | `Plant A` |
| Observed severity | `LOW` |
| Approval mode | `HIGH_RISK_ONLY` |
| Issue description | `Routine inspection needed.` |
| Safety concern | unchecked |

Submit with `Submit maintenance request`.

Expected controlled outcome:

* status: `COMPLETED`;
* no pending approval;
* a synthetic maintenance work order draft is created;
* audit/tool records show the low-severity maintenance path.

Use uppercase maintenance severity values from the UI selector:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

The backend validates canonical `MaintenanceSeverity` values. Lowercase or
unknown API payload values are not the documented default UI path.

Do not hide `FAILED_TOOL` when experimenting. If `FAILED_TOOL` appears for
different arbitrary maintenance input, it is a controlled backend failure state
rendered safely by the UI. It is not a UI crash and it should not be presented
as a successful maintenance outcome.

## 9. Inspecting a run

Run-scoped frontend pages:

| Page | Purpose |
| --- | --- |
| `/runs/{run_id}` | Run Detail: controlled outcome, final summary, run metadata, record counts and run JSON. |
| `/runs/{run_id}/approvals` | Run Approvals: pending or terminal approvals for that run, plus approval actions when pending. |
| `/runs/{run_id}/tool-calls` | Run Tool Calls: tool names, tool types, statuses, approval links, safe errors and redacted input/output payloads. |
| `/runs/{run_id}/audit` | Run Audit Trail: chronological audit events, actors and selected event payload JSON. |

The Agent Runs page is a session-known index built from browser-local run IDs.
The backend currently has no global run listing endpoint. The local known-run
index is a demo convenience, not backend truth.

To inspect an existing run, paste its `run_id` into the `Open Run` control on
Dashboard or Settings. If the backend knows the run, the UI adds it to the
local known-run index and opens the run detail page.

## 10. Running evals

Run the deterministic API acceptance suite:

```bash
uv run python scripts/run_eval.py
uv run python scripts/run_eval.py --format json
```

Expected result:

```text
21/21 passed
```

The text report prints:

```text
Total: 21  Passed: 21  Failed: 0
```

The evals prove deterministic backend/API behavior for controlled statuses,
approval gating, no-draft-before-approval behavior, readback endpoints, audit
events, reason codes, redaction-related expectations and failed-validation
handling.

The evals do not prove production security, real provider quality, real
enterprise connector behavior, auth/RBAC/tenant behavior, scalability, full UI
E2E coverage or production monitoring readiness.

## 11. What to notice during the demo

* Backend-controlled lifecycle from workflow submit to final run status.
* Approval boundary for risky state-changing draft actions.
* Draft/no-draft behavior before and after approval decisions.
* Tool-call visibility with registered tool names, statuses and safe errors.
* Audit trail with run-scoped lifecycle evidence.
* Redacted public payload projection in API and UI readback.
* Controlled failure statuses such as `NEEDS_USER_INPUT`, `NEEDS_MANUAL_REVIEW`,
  `REJECTED`, `FAILED_VALIDATION`, `FAILED_TOOL` and `FAILED_PROVIDER`.
* Frontend/API separation: the React client displays backend-controlled
  results over `/api/v1`.

## 12. Troubleshooting

Backend root `/` returns 404:

This is normal. Use `/api/v1/health`, `/api/v1/capabilities` or the frontend
dashboard.

Frontend cannot connect to the API:

Make sure the backend is running on port 8000 and the frontend was started with
the Vite dev server. The frontend calls `/api/v1`, and Vite proxies `/api` to
`http://localhost:8000`.

`npm` is not in PATH on Windows:

Use the full npm path if needed:

```text
C:\Program Files\nodejs\npm.cmd
```

Black screen:

Check the browser console and the Vite terminal. The current frozen prototype
should not blank-screen in the documented default paths.

Maintenance returns `FAILED_TOOL` for non-default arbitrary input:

Treat it as a controlled backend failure state. Use the documented known-good
maintenance values for the default/safe walkthrough, and inspect Tool Calls and
Audit Trail instead of treating it as a UI crash.

Real provider credentials:

They are not required for the default demo. The default provider mode is
`mock`.

## 13. Demo limitations

This demo is intentionally limited:

* local/demo only;
* synthetic workflow data;
* deterministic mock provider by default;
* no auth, RBAC or tenants;
* no real IAM, ERP, 1C, Jira, CRM, CMMS, EAM or other enterprise connectors;
* no provider/model selection;
* no production deployment;
* no global backend run listing or global audit search;
* no full UI E2E test coverage claim.

The demonstrated value is the control pattern: backend validation, controlled
tool boundaries, policy checks, approval gates, audit records and public
run-scoped readback.
