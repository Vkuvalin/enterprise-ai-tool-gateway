# Project Context

## 1. Project thesis

Enterprise AI Tool Gateway is a local/demo prototype of controlled LLM tool
execution for synthetic enterprise workflows.

The core claim is simple:

```text
LLM proposes.
Backend validates.
Tools execute only through controlled boundaries.
Approval gates risky actions.
Audit records meaningful lifecycle events.
Frontend displays the controlled workflow through /api/v1.
```

The project is not a chatbot and not a production SaaS product. It demonstrates
how backend-owned contracts, policy checks, approval gates, tool boundaries and
audit records can govern LLM-proposed actions.

## 2. What this prototype demonstrates

The prototype demonstrates an engineering pattern for governed LLM tool use:

* controlled LLM tool execution through backend-owned runtime logic;
* strict validation of structured provider decisions before tool execution;
* registered tool execution through `ToolRegistry` and `ToolExecutor`;
* policy checks before state-changing draft actions;
* approval control for risky actions before those actions execute;
* run-scoped visibility into tool calls, approvals and audit events;
* separation between the FastAPI `/api/v1` backend and the React/Vite frontend;
* deterministic, offline acceptance testing over the API surface.

The primary lifecycle is:

```text
request
-> backend run creation
-> provider decision
-> backend validation
-> read tools
-> policy check
-> approval if required
-> controlled draft action or controlled stop
-> audit events
-> final run outcome
```

## 3. Current frozen prototype state

Implemented layers:

* Backend: Python package under `src/enterprise_ai_tool_gateway/`.
* API: FastAPI adapter versioned under `/api/v1`.
* Workflows: three synthetic enterprise workflows:
  `ACCESS_REQUEST`, `PROCUREMENT_REQUEST` and `MAINTENANCE_REQUEST`.
* Frontend: independent React + TypeScript + Vite client under `frontend/`.
* Evals: deterministic acceptance runner with a 21-case suite.
* Persistence: local SQLite persistence through async SQLAlchemy.
* Provider mode: deterministic mock/fake provider path by default.

Implemented backend areas include contracts, workflow transitions, provider
ports, tool registry/executor, policy decisions, approval primitives, audit
redaction/events, persistence, application runtimes, FastAPI routes and evals.

Implemented frontend areas include a dashboard, workflow submission pages,
agent run views, run-scoped approvals, tool calls, audit trail, settings, API
status and a local known-run index.

## 4. Implemented workflows

### ACCESS_REQUEST

Purpose: demonstrate an access-control request through a controlled gateway.

What it demonstrates:

* employee, system, access-policy and existing-ticket read checks;
* backend validation of the provider decision and allowed access tools;
* policy decisions before creating an access request draft;
* approval for high-risk access changes, such as admin access;
* safe rejection or manual review when synthetic policy/data checks fail.

Possible controlled outcomes:

* completed synthetic access request draft;
* waiting for approval, then completed or rejected after approval resolution;
* needs user input for missing required fields;
* needs manual review for unverifiable data or duplicate/open-ticket risks;
* rejected by policy;
* failed validation for invalid provider output or unknown tool proposals.

This is not a real IAM integration.

### PROCUREMENT_REQUEST

Purpose: demonstrate spend/vendor/budget control through the same gateway
pattern.

What it demonstrates:

* synthetic requester, vendor, catalog item, budget/policy and duplicate-request
  checks;
* backend validation of procurement request type, domain template and tool names;
* policy control before creating a purchase request draft;
* approval for high-value or approval-required draft actions;
* manual review or rejection for blocked vendors, restricted items, budget
  issues, duplicates or missing synthetic data.

Possible controlled outcomes:

* completed synthetic purchase request draft;
* waiting for approval, then completed or rejected after approval resolution;
* needs user input for missing required fields;
* needs manual review for synthetic data/policy uncertainty;
* rejected by policy;
* failed validation for invalid provider output or unknown tool proposals.

This is not a real procurement, ERP, vendor or tender workflow.

### MAINTENANCE_REQUEST

Purpose: demonstrate asset/severity/safety control through a lightweight
maintenance workflow.

What it demonstrates:

* synthetic requester, asset, severity classification, duplicate-ticket and
  maintenance-policy checks;
* canonical `MaintenanceSeverity` handling with uppercase enum values;
* backend validation of maintenance request type, domain template and tool names;
* policy control before creating a work order draft;
* approval for high-severity work order drafts;
* manual review or rejection for safety concerns, critical/manual-review cases
  or forbidden maintenance instructions.

Possible controlled outcomes:

* completed synthetic work order draft;
* waiting for approval, then completed or rejected after approval resolution;
* needs user input for missing required fields;
* needs manual review for safety or synthetic data/policy uncertainty;
* rejected by policy;
* failed validation for invalid provider output or unknown tool proposals.

This is not a real CMMS, EAM or maintenance/TOIR integration.

## 5. Backend/API status

The backend exposes a local/demo FastAPI API under `/api/v1`.

Implemented endpoint groups:

* `GET /api/v1/health`;
* `GET /api/v1/capabilities`;
* `POST /api/v1/access-requests`;
* `POST /api/v1/procurement-requests`;
* `POST /api/v1/maintenance-requests`;
* `POST /api/v1/approvals/{approval_id}/resolve`;
* `GET /api/v1/runs/{run_id}`;
* `GET /api/v1/runs/{run_id}/tool-calls`;
* `GET /api/v1/runs/{run_id}/approvals`;
* `GET /api/v1/runs/{run_id}/audit-events`.

Business outcomes are modeled as controlled run statuses, not as generic HTTP
failures. For example, rejected, manual-review, user-input and failed-validation
outcomes can return HTTP 200 with a run status that explains the controlled
stop. HTTP errors are still used for malformed request bodies, unknown run or
approval IDs, invalid approval decisions and state conflicts.

Public API responses use a redacted projection for tool payloads and approval
free-text fields. Backend runtime objects may contain more internal detail than
the public response DTOs expose.

## 6. Frontend status

The frontend is an independent React/Vite client under `frontend/`. It talks to
the backend only through the `/api/v1` HTTP API client in `frontend/src/api/`.

The UI is best understood as a local Gateway Operations Console. It includes:

* Dashboard;
* Workflows;
* workflow submit pages for access, procurement and maintenance;
* Agent Runs;
* run detail;
* Approvals;
* run-scoped Tool Calls;
* run-scoped Audit Trail;
* Settings and API status.

The frontend keeps a browser-local known-run index that stores run IDs for the
current demo session. It does not implement global backend search, a global audit
search, a production approval queue, requester/admin role separation or business
logic execution.

This is not a production requester portal, operator portal, admin portal or
monitoring product.

## 7. Provider/model status

The default demo and test path uses deterministic mock/fake providers. The API
capabilities endpoint reports `provider_mode` as `mock`.

Real-provider smoke is not the default demo path and must remain explicit and
manual. There is no silent fallback from a failed real provider to mock.

API capabilities expose model selection as disabled:

```text
model_selection.enabled = false
active_profile = "mock"
available_profiles = ["mock"]
```

No OpenRouter, Yandex, provider marketplace, provider fallback routing,
streaming, quota/billing or frontend model selector is implemented.

## 8. Data, audit and safety status

The prototype uses local SQLite persistence for gateway records:

* agent runs;
* validated LLM decisions;
* tool calls;
* approvals;
* audit events.

Tool calls, approvals and audit events are run-scoped and visible through the
public API read endpoints. Audit events record meaningful lifecycle events such
as run creation, provider selection, decision validation, tool execution, policy
checks, approval requests/decisions, manual review, rejection, completion and
failure.

Safety-related behavior in the frozen prototype includes:

* public API redaction for tool payloads and approval text;
* controlled public projection of run, tool, approval and audit records;
* an approval safety floor so `AUTO_APPROVE` does not bypass high-risk,
  critical-risk or default-approval state-changing controls;
* strict domain-template validation before dispatching workflow actions;
* canonical maintenance severity validation through `MaintenanceSeverity`;
* no provider/model selection fields accepted in workflow submit bodies;
* no secrets intended in public API responses.

## 9. What is intentionally not implemented

The prototype intentionally does not implement:

* production authentication;
* RBAC;
* tenants;
* real enterprise connectors;
* real IAM, ERP, 1C, Jira, CRM, CMMS or EAM integrations;
* provider/model selection;
* global run search or history;
* global audit search;
* deployment or hosting;
* payment;
* desktop app;
* workflow builder;
* policy editor;
* organization administration;
* production background workers;
* production observability;
* production security hardening.

## 10. Future directions

Potential future backlog, not committed scope:

* real integrations through API or MCP-style boundaries;
* provider profiles and explicit provider selection;
* authentication, RBAC and tenant isolation;
* deployment packaging and hosted environments;
* richer admin/operator UI surfaces;
* workflow-builder concepts;
* monitoring, analytics and operational reporting.

Any future expansion should preserve the control model: backend validation,
explicit tool boundaries, policy checks, approval gates and auditability.

## 11. Related documents

Existing companion documents:

* [PROJECT_MAP.md](PROJECT_MAP.md) - architecture map, package ownership,
  runtime ownership and entrypoints.
* [README.md](../README.md) - public quickstart and validation commands.

* [ARCHITECTURE.md](ARCHITECTURE.md) - architecture, lifecycle, boundaries,
  failure model and limitations.
* [API_AND_EVALS.md](API_AND_EVALS.md) - public API surface, controlled
  outcomes and deterministic eval suite.
* [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) - local demo walkthrough for the
  backend, frontend and eval runner.
* [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) - setup, validation and safe
  development workflow.
