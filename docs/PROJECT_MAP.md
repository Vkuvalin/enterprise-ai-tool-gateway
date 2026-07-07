# Project Map

This document maps the current and planned architecture for `enterprise-ai-tool-gateway`.

Current status: Stage 9 modular local/demo web client surface is implemented on
top of the Stage 8 backend API and deterministic acceptance eval surface. The
project remains a backend-first MVP; the API and web client are local/demo
surfaces, not a production platform. Production integrations, auth, workers,
deployment and migrations are not implemented.

## 1. Current Package Map

Implemented source packages under `src/enterprise_ai_tool_gateway/`:

| Package | Status | Ownership |
| ------- | ------ | --------- |
| `contracts/` | implemented | Shared enums and Pydantic create/read contracts used by foundation layers. |
| `llm/` | implemented | Provider boundary, deterministic mock provider, optional/manual GigaChat config/auth/transport, safe provider errors and strict structured decision parsing. |
| `mcp/` | implemented | Optional local fake external tool boundary with typed validation, safe MCP errors and manual smoke; ToolRegistry remains the canonical internal tool boundary. |
| `workflow/` | implemented | Pure event-driven `AgentRun` state kernel and transition allowlist. |
| `tools/` | implemented | Generic `ToolDefinition`, `ToolRegistry` and `ToolExecutor` boundary with Pydantic input/output validation. |
| `policy/` | implemented | Generic policy request/decision primitives and default Stage 4 tool-policy evaluator. |
| `approval/` | implemented | Approval requirement and decision primitives only. |
| `audit/` | implemented | Redacted audit event creation and recursive payload redaction. |
| `db/` | implemented | Minimal async SQLAlchemy + SQLite models, schema bootstrap, session helpers and repository. |
| `access/` | implemented | Access-specific schemas, deterministic tool definitions and handlers for the Stage 5 reference workflow. |
| `procurement/` | implemented | Procurement demo schemas, deterministic tool definitions and handlers for the Stage 7 thin procurement template. |
| `maintenance_lite/` | implemented | Maintenance-lite demo schemas, deterministic tool definitions and handlers for the Stage 7 thin maintenance template. |
| `demo_domain/` | implemented | Deterministic synthetic access, procurement and maintenance data representing future external sources without real connectors. |
| `application/` | implemented | Explicit runtime coordinators for access, procurement and maintenance_lite workflows, plus shared mechanical demo workflow helpers. |
| `api/http/` | implemented | FastAPI inbound adapter with `/api/v1` health, capabilities, submit, approval resolve and run read endpoints. Routes are thin and do not own workflow, policy, approval, tool execution or audit logic. |
| `api/http/schemas/` | implemented | API-facing DTOs for submit requests, workflow responses, capabilities, approvals, runs, tool calls and audit events. |
| `api/http/mappers.py` | implemented | Mapping between API DTOs, application DTOs and serialized API response DTOs. |
| `api/http/dependencies.py` | implemented | Request-scoped DB session, repository and runtime dependency wiring using deterministic mock/fake providers by default. |
| `evals/` | implemented | Deterministic API-level acceptance case definitions, runner logic and JSON/text result models. |

Implemented frontend package at repository root:

```text
frontend/
```

`frontend/` owns the independent React/Vite web client. It is not part of the
Python package and is not mounted into FastAPI in Stage 9.

Frontend ownership:

| Frontend area | Status | Ownership |
| ------------- | ------ | --------- |
| `frontend/src/api/` | implemented | HTTP API client for FastAPI `/api/v1`; all frontend HTTP calls go through this boundary. |
| `frontend/src/features/` | implemented | Workflow, run, approval, tool-call, audit and settings feature modules. |
| `frontend/src/components/` | implemented | Reusable layout, feedback, data, form and status UI components. |
| `frontend/src/pages/` | implemented | Route-level screens for dashboard, workflow catalog, workflow submit, run detail, run-scoped approvals, tool calls, audit trail, session approvals and settings. |
| `frontend/src/state/` | implemented | Browser local known-run index storing run IDs only. |
| `frontend/src/styles/` | implemented | Dark-first local/demo command-center CSS tokens and global styles. |

## 2. Dependency Direction

`contracts/` is the only shared low-level dependency for the Stage 4 foundation.

Allowed direction:

```text
contracts
  -> workflow / tools / policy / approval / audit / db
```

Sibling foundation layers do not coordinate each other directly. For example, `workflow/` does not import `tools/`, `tools/` does not import `policy/`, `policy/` does not import `db/`, and `db/` does not call workflow, policy or audit helpers.

## 3. Runtime Ownership

`workflow/` owns valid `AgentRunStatus` transitions only. It does not execute tools, call providers, persist rows, create audit events, or make policy decisions.

`tools/` owns the controlled tool boundary. Registered tools validate input and output through Pydantic models. Non-read-only tools require explicit execution authorization before handler execution.

`policy/` returns generic policy decisions. It does not execute tools, create approvals, write audit events, or mutate workflow state.

`approval/` models human permission primitives. It does not expose an API, send notifications, write database records, or mutate workflow state.

`audit/` creates redacted `AuditEventCreate` contracts. It does not write persistence, ship logs, store raw provider responses, or classify PII.

`db/` persists already validated facts. `GatewayRepository.update_agent_run_status()` stores a status chosen by another layer and intentionally does not validate workflow transitions.

`llm/` owns provider-specific configuration, transport, auth, safe provider
errors and deterministic structured decision parsing. LLM output is untrusted
until extracted, parsed, validated through `LLMDecisionPayload`, and accepted by
backend runtime validation. Providers must not execute tools or approve actions.

`mcp/` owns the optional external tool boundary. It currently exposes only a
local deterministic fake MCP tool for boundary validation. It is not the
canonical internal tool boundary and it does not replace ToolRegistry.

`access/` owns access-domain schemas and tool definitions only. It does not own workflow, policy, approval, audit, persistence, LLM provider behavior or HTTP routing.

`procurement/` owns procurement-domain schemas and deterministic tool definitions only. It does not own workflow, policy, approval, audit, persistence, LLM provider behavior, MCP behavior, real procurement connectors or HTTP routing.

`maintenance_lite/` owns maintenance-domain schemas and deterministic tool definitions only. It does not own workflow, policy, approval, audit, persistence, LLM provider behavior, MCP behavior, real maintenance / ТОИР / CMMS connectors or HTTP routing.

`demo_domain/` owns local deterministic synthetic access, procurement and maintenance data only. It represents future external sources without implementing real connectors.

`application/` coordinates use cases. The Stage 5 access runtime starts and resumes `ACCESS_REQUEST` workflows, uses the provider boundary for structured decisions, validates backend-owned tool plans, executes access tools through `ToolExecutor`, evaluates policy, creates approvals when needed, persists repository records, and writes redacted audit events.

The Stage 7 procurement runtime coordinates `PROCUREMENT_REQUEST` with synthetic requester/vendor/catalog/budget/duplicate read tools, existing policy/approval/audit foundations, and draft-only purchase request creation persisted through `ToolCall.output_payload`.

The Stage 7 maintenance_lite runtime coordinates `MAINTENANCE_REQUEST` with synthetic requester/asset/severity/duplicate read tools, existing policy/approval/audit foundations, and draft-only work order creation persisted through `ToolCall.output_payload`.

`application/demo_workflow.py` owns shared runtime mechanics only, such as required-field checks, provider tool-name validation, safe tool execution and persistence, audit persistence, policy request construction, approval record handling and runtime record collection. It does not encode procurement or maintenance domain semantics.

`api/http/` owns the local/demo FastAPI adapter layer. It translates HTTP
requests into application DTOs and serializes application/runtime results back
to API DTOs. API routes must stay thin: no business logic, no policy decisions,
no approval state mutation, no tool execution and no audit decision creation in
route handlers. Stage 8 does not add production auth, tenant isolation or RBAC.

`evals/` owns deterministic acceptance checks that exercise the API surface
through FastAPI's in-process test client. Evals use mock/fake providers only and
do not benchmark models, compare providers or call real external services.

`frontend/` owns the Stage 9 local/demo web client. It talks only to FastAPI
`/api/v1` through `frontend/src/api/`, mirrors public API DTO shapes in
TypeScript without importing backend Python internals, and renders controlled
gateway outcomes as UI states. Backend execution remains behind FastAPI
`/api/v1`; the frontend must not execute workflow logic directly.

## 4. Current Entrypoints

Current deterministic test entrypoint:

```bash
uv run pytest
```

Current local/demo API entrypoint:

```bash
uv run uvicorn enterprise_ai_tool_gateway.api.http.app:app --reload
```

Current deterministic API acceptance eval entrypoints:

```bash
uv run python scripts/run_eval.py
uv run python scripts/run_eval.py --format json
```

Current local/demo frontend entrypoint:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000/api`, while the
frontend API client uses `/api/v1` by default.

Current validation commands:

```bash
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
uv run python scripts/run_eval.py
uv run python scripts/run_eval.py --format json
cd frontend
npm install
npm run typecheck
npm run build
```

Manual utilities exist for provider/MCP checks, but real-provider smoke remains
explicit and disabled by default:

```bash
uv run python scripts/mcp_smoke.py
uv run python scripts/manual_gigachat_smoke.py --live --matrix lite,pro,max
```

## 5. Current Non-Entrypoints

There is currently no production FastAPI route layer, production MCP lifecycle,
Alembic migration setup, background worker, real enterprise integration or
production auth layer. The Stage 8 API and Stage 9 web client are local/demo
only and do not implement authenticated users, tenants, RBAC, provider
selection, domain CRUD, global run listing/search/history, global audit search,
global backend approval queue or real connectors. Stage 5 access runtime is not
rewritten to MCP. Stage 7 procurement and maintenance templates add no real
procurement or maintenance connectors, no domain DB tables, and no real purchase
order or work order lifecycle. Their controlled actions create synthetic drafts
only.

## 6. Tests

Current tests are deterministic and offline by default. Stage 4 coverage includes:

* contracts;
* workflow transitions;
* generic tools;
* default policy evaluator;
* approval primitives;
* audit redaction/event creation;
* async SQLite persistence foundation;
* provider and structured-output boundary behavior;
* local fake MCP boundary behavior;
* Stage 5 access tools, access workflow runtime, approval resolution path, approval-mode persistence and Stage 5 import boundaries;
* Stage 7 procurement and maintenance_lite tools, runtime paths, approval paths, missing input, manual review, rejection, unknown tool proposal handling, audit/persistence checks and import boundaries;
* shared Stage 7 demo workflow helper mechanics;
* Stage 8 local/demo API health, capabilities, workflow submit, approval resolve and run read endpoints;
* Stage 8 deterministic API-level acceptance eval runner and 21-case acceptance matrix.
* Stage 9 frontend validation is performed with the frontend package commands:
  `npm install`, `npm run typecheck` and `npm run build`.
