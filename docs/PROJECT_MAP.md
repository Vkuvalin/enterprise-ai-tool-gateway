# Project Map

This document maps the current and planned architecture for `enterprise-ai-tool-gateway`.

Current status: Stage 4 core gateway foundation implemented. The project remains a backend-first MVP; business workflows, API routes, Web UI, production integrations, auth, workers and migrations are not implemented yet.

## 1. Current Package Map

Implemented source packages under `src/enterprise_ai_tool_gateway/`:

| Package | Status | Ownership |
| ------- | ------ | --------- |
| `contracts/` | implemented | Shared enums and Pydantic create/read contracts used by foundation layers. |
| `llm/` | Stage 3 spike | Provider port, deterministic mock provider, GigaChat/Yandex settings and smoke helpers. |
| `mcp/` | Stage 3 spike | Minimal local MCP feasibility smoke only; not the production tool boundary. |
| `workflow/` | implemented | Pure event-driven `AgentRun` state kernel and transition allowlist. |
| `tools/` | implemented | Generic `ToolDefinition`, `ToolRegistry` and `ToolExecutor` boundary with Pydantic input/output validation. |
| `policy/` | implemented | Generic policy request/decision primitives and default Stage 4 tool-policy evaluator. |
| `approval/` | implemented | Approval requirement and decision primitives only. |
| `audit/` | implemented | Redacted audit event creation and recursive payload redaction. |
| `db/` | implemented | Minimal async SQLAlchemy + SQLite models, schema bootstrap, session helpers and repository. |

Planned later packages remain subject to their own Stage Briefs:

```text
demo_domain
application
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

`llm/` remains a provider boundary. LLM output is untrusted until backend validation accepts it, and providers must not execute tools.

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

Manual spike utilities currently exist for provider/MCP checks, but real-provider smoke remains explicit and disabled by default:

```bash
uv run python scripts/mcp_smoke.py
uv run python scripts/manual_gigachat_smoke.py
```

## 5. Current Non-Entrypoints

There is currently no production FastAPI route layer, application orchestrator, ACCESS_REQUEST workflow, domain tool implementation, approval UI/API, production MCP lifecycle, Alembic migration setup, background worker, real enterprise integration or production auth layer.

## 6. Tests

Current tests are deterministic and offline by default. Stage 4 coverage includes:

* contracts;
* workflow transitions;
* generic tools;
* default policy evaluator;
* approval primitives;
* audit redaction/event creation;
* async SQLite persistence foundation;
* existing provider and MCP spike behavior.
