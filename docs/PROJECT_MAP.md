# Project Map

This document maps the current and planned architecture for `enterprise-ai-tool-gateway`.

Current status: Stage 6 GigaChat and MCP boundary hardening is implemented on
top of the Stage 5 access request reference workflow. The project remains a
backend-first MVP; API routes, Web UI, production integrations, auth, workers
and migrations are not implemented yet.

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
| `demo_domain/` | implemented | Deterministic synthetic access data representing future HR/catalog/policy/ticket sources. |
| `application/` | implemented | Access workflow runtime coordinator that connects provider, workflow, tools, policy, approval, audit and persistence boundaries. |

Planned later packages remain subject to their own Stage Briefs:

```text
api/http
evals
web/static
scripts
```

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

`demo_domain/` owns local deterministic synthetic access data only. It represents future external sources without implementing real connectors.

`application/` coordinates use cases. The Stage 5 access runtime starts and resumes `ACCESS_REQUEST` workflows, uses the provider boundary for structured decisions, validates backend-owned tool plans, executes access tools through `ToolExecutor`, evaluates policy, creates approvals when needed, persists repository records, and writes redacted audit events.

## 4. Current Entrypoints

Current deterministic test entrypoint:

```bash
uv run pytest
```

Current validation commands:

```bash
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
```

Manual utilities exist for provider/MCP checks, but real-provider smoke remains
explicit and disabled by default:

```bash
uv run python scripts/mcp_smoke.py
uv run python scripts/manual_gigachat_smoke.py --live --matrix lite,pro,max
```

## 5. Current Non-Entrypoints

There is currently no production FastAPI route layer, approval UI/API,
production MCP lifecycle, Alembic migration setup, background worker, real
enterprise integration or production auth layer. Stage 5 access runtime is not
rewritten to MCP.

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
* Stage 5 access tools, access workflow runtime, approval resolution path, approval-mode persistence and Stage 5 import boundaries.
