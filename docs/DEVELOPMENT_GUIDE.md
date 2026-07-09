# Development Guide

## 1. Purpose

This guide explains how to develop, validate and safely change the frozen local
prototype. It is a practical checklist for running the backend, running the
frontend, executing deterministic evals, collecting review diffs and preserving
the project boundaries that make the gateway safe to inspect.

The prototype is local/demo software. It demonstrates backend-controlled
LLM-proposed tool execution for synthetic access, procurement and maintenance
workflows. It is not a production deployment guide.

## 2. Prerequisites

Required local tools:

* Python compatible with the project requirement in `pyproject.toml`. The
  current project requirement is Python `>=3.14`.
* `uv` for Python dependency management and command execution.
* Node.js and npm for the React/Vite frontend.
* A local checkout of this repository.

Default validation and demo runs do not require real provider credentials. The
default provider path is deterministic mock/fake provider behavior, and default
tests/evals must not call real providers or external enterprise systems.

Windows notes:

* Run commands from the repository root unless a section says to use
  `frontend/`.
* If `npm` is installed but not on `PATH`, use the full npm executable path:
  `C:\Program Files\nodejs\npm.cmd`.

## 3. Backend setup and run

From the repository root, start the FastAPI backend:

```bash
uv run uvicorn enterprise_ai_tool_gateway.api.http.app:app --reload
```

The API is versioned under `/api/v1`. Use these health checks:

```text
http://127.0.0.1:8000/api/v1/health
http://127.0.0.1:8000/api/v1/capabilities
```

The backend root may return 404:

```text
http://127.0.0.1:8000/
```

That is normal. The backend serves the API, not the frontend root page.

By default, the local app creates a SQLite database under `data/`. Local
database files are runtime artifacts and must not be committed.

## 4. Frontend setup and run

In a second terminal, install frontend dependencies if needed:

```bash
cd frontend
npm install
```

Start the Vite dev server on the documented local address:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open the main UI:

```text
http://127.0.0.1:5173/dashboard
```

The frontend API client uses `/api/v1` by default. The Vite dev server proxies
`/api` to `http://localhost:8000`, so the backend should be running on port
8000 before using the UI.

Windows npm fallback:

```text
C:\Program Files\nodejs\npm.cmd
```

Example:

```powershell
cd frontend
& "C:\Program Files\nodejs\npm.cmd" run dev -- --host 127.0.0.1 --port 5173
```

## 5. Backend validation

Run routine backend validation from the repository root:

```bash
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
```

The exact test count can change as the prototype evolves, so do not hardcode an
expected count in docs or task handoffs unless the repository establishes a
specific convention for that moment.

Default backend validation must remain deterministic and offline. It must not
require real provider credentials, network access or real enterprise systems.

## 6. Eval validation

Run the deterministic API acceptance evals:

```bash
uv run python scripts/run_eval.py
uv run python scripts/run_eval.py --format json
```

The eval runner exercises the public `/api/v1` API surface with deterministic
providers and isolated local SQLite state. It is acceptance validation for the
gateway lifecycle: controlled statuses, approval gating, readback endpoints,
audit events, reason codes and failed-validation handling.

The evals use the default mock/static provider path. They perform no real
provider calls, no external network calls and no real connector calls.

## 7. Frontend validation

Run frontend validation from `frontend/`:

```bash
cd frontend
npm run typecheck
npm run build
```

There is no full frontend E2E harness in the current prototype. Before
demo-facing frontend changes are accepted, run a manual browser smoke over the
main routes and workflows.

## 8. Manual smoke checklist

With the backend and frontend running, check the main routes:

* `/dashboard`
* `/workflows`
* `/runs`
* `/settings`

Then run the main workflow paths:

* Access submit with the documented known-good access values.
* Procurement approval path, including pending approval and approval
  resolution.
* Maintenance default/safe path with known-good low-severity values.

For a created run, inspect:

* `/runs/{run_id}`
* `/runs/{run_id}/approvals`
* `/runs/{run_id}/tool-calls`
* `/runs/{run_id}/audit`

Smoke expectations:

* no blank screen;
* API status is healthy;
* provider mode is `mock`;
* model selection is disabled;
* controlled statuses render safely, including `COMPLETED`,
  `WAITING_FOR_APPROVAL`, `NEEDS_USER_INPUT`, `NEEDS_MANUAL_REVIEW`,
  `REJECTED`, `FAILED_VALIDATION`, `FAILED_TOOL` and `FAILED_PROVIDER`;
* approval-required workflows do not show a completed draft before approval;
* run-scoped tool calls and audit records are visible.

## 9. Diff and review workflow

For review loops, use a staged-baseline workflow when it helps separate already
accepted changes from later fix-loop edits. Do not commit during this workflow
unless the task explicitly asks for a commit.

Before the fix-loop, stage the accepted baseline without committing:

```powershell
git status --short --untracked-files=all
git add <accepted-files>
git -c core.quotepath=false diff --cached --output=accepted-baseline.diff
```

After fix-loop edits, collect the unstaged delta:

```powershell
git -c core.quotepath=false diff --output=fix-loop-delta.diff
git diff --check
```

Review the delta. If the fix-loop changes are accepted, update the staged
baseline intentionally:

```powershell
git add <accepted-fix-files>
git -c core.quotepath=false diff --cached --output=accepted-baseline.diff
```

Prefer `git diff --output=...` over PowerShell `Out-File` for patch/diff files.
It avoids accidental encoding changes that make review artifacts harder to
apply or compare.

Keep review diffs focused. Do not mix unrelated cleanup, generated output,
local cache changes or unrelated documentation edits into the same review set.

## 10. Repo hygiene

Do not commit local dependency, build, cache, secret or review artifacts:

* `frontend/node_modules/`
* `frontend/dist/`
* `frontend/.vite/`
* `.env` or secret-bearing files
* local SQLite databases, logs and runtime data
* temporary task/report/plan/diff artifacts under `docs/codex/` or other
  ignored working directories

Keep generated reports and diffs out of final commits unless a task explicitly
requires a committed artifact. Before committing any change, inspect:

```bash
git status --short --untracked-files=all
git diff --check
```

## 11. Boundary rules for changes

Preserve these boundaries when changing the prototype:

* Frontend code must call the backend only through `/api/v1`.
* Frontend code must not import backend Python internals.
* API routes must remain thin adapters over application runtimes.
* Application runtimes own orchestration, workflow decisions and approval
  resolution behavior.
* The backend owns provider-output validation, tool execution, policy checks,
  approval gates, audit creation and persistence coordination.
* Provider output is untrusted until backend schema and runtime validation
  accept it.
* Tool execution must go through `ToolRegistry` / `ToolExecutor` or an explicit
  MCP/MCP-like boundary.
* Unknown, disallowed or unregistered tool proposals must fail validation.
* State-changing tools require policy checks.
* Risky or approval-required state-changing tools require approval before draft
  execution.
* Public API responses must use safe projection/redaction for tool payloads,
  approval free-text fields and audit payloads.
* Default tests and evals must not make real provider or external network
  calls.

## 12. Common troubleshooting

`npm` is not in `PATH`:

Use the full Windows executable path:

```text
C:\Program Files\nodejs\npm.cmd
```

Backend root `/` returns 404:

Use `/api/v1/health`, `/api/v1/capabilities` or the frontend dashboard. A 404
from `/` is normal.

Frontend cannot reach the API:

Make sure the backend is running on port 8000. The frontend calls `/api/v1`,
and Vite proxies `/api` to `http://localhost:8000`.

Vite port conflict:

Use the documented explicit port when possible:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

If another process already owns the port, stop that process or choose another
local port and open the URL Vite prints.

CRLF/LF Git warnings:

Check the diff before committing. Line-ending warnings are usually a local Git
configuration issue, but the final diff should stay readable and should not
include unrelated whole-file churn.

Maintenance returns `FAILED_TOOL` for arbitrary non-default input:

Treat it as a controlled backend failure state. Use the documented known-good
maintenance values for the default/safe smoke path, then inspect the run detail,
tool calls and audit trail.

FastAPI or Starlette `TestClient` warning:

If pytest emits a `TestClient` warning while tests still pass, record it in the
handoff as a dependency/tooling warning. Do not treat it as a real-provider or
connector failure, and do not mask failing tests.

## 13. Related documents

Related source-of-truth and companion documents:

* [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
* [ARCHITECTURE.md](ARCHITECTURE.md)
* [PROJECT_MAP.md](PROJECT_MAP.md)
* [API_AND_EVALS.md](API_AND_EVALS.md)
* [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md)
* [README.md](../README.md)

`README.md` is the public quickstart. If it is rewritten later, keep its
commands aligned with this guide and the current repository entrypoints.
