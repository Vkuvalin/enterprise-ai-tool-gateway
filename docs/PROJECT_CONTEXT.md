# Project Context

## 1. Project

`enterprise-ai-tool-gateway`

## 2. Current status

MVP development after Stage 8.

Stage 4 — Core Gateway Foundation is implemented and accepted.
Stage 5 — Access Request Reference Workflow is implemented.
Stage 6 — GigaChat & MCP Hardening is implemented.
Stage 7 — Demo Template Expansion is implemented.
Stage 8 — Backend API, Evals & Acceptance Surface is implemented.

Implemented foundation packages:

```text
contracts/
workflow/
tools/
policy/
approval/
audit/
db/
llm/
mcp/
access/
procurement/
maintenance_lite/
demo_domain/
application/
api/http/
evals/
```

The access request reference workflow and provider/MCP hardening are
implemented. Thin synthetic procurement and maintenance_lite demo templates are
implemented to demonstrate the repeatable gateway pattern. A local/demo FastAPI
adapter and deterministic API-level acceptance evals are implemented for access,
procurement and maintenance_lite workflows. Web UI, production integrations,
auth, workers and migrations are not implemented.

## 3. Purpose

The project is a backend-first MVP for a controlled enterprise tool gateway for LLM-powered agents.

The goal is to demonstrate how an LLM agent can work with enterprise tools through a backend-controlled boundary:

```text
user request
→ structured LLM decision
→ backend validation
→ tool registry / MCP boundary
→ policy check
→ approval gate
→ controlled action or draft
→ audit trail
→ eval scenarios
```

The project is not intended to be a general chatbot.

## 4. Main thesis

An enterprise LLM agent should not receive uncontrolled direct access to internal systems.

The backend must own:

* tool availability;
* tool input/output validation;
* policy checks;
* approval requirements;
* execution boundaries;
* audit trail;
* safe error handling.

The LLM may propose a structured decision and tool calls, but the backend decides what can actually be executed.

## 5. MVP scope

Accepted MVP scope:

* FastAPI backend;
* async Python stack;
* deterministic mock provider;
* GigaChat as primary real provider;
* YandexGPT as stretch/spike provider;
* structured decision schema;
* tool registry;
* MCP-first tool boundary;
* MCP-like fallback only if real MCP blocks delivery;
* policy checks;
* approval gate;
* persisted audit trail;
* eval scenarios;
* API-first demo;
* Web UI after backend acceptance.

## 6. Demo surface

The demo surface is an `Enterprise Request Gateway`.

The gateway should support several lightweight request templates over the same foundation.

Accepted request templates:

| Request type          | Status                    | Purpose                |
| --------------------- | ------------------------- | ---------------------- |
| `ACCESS_REQUEST`      | required full             | reference workflow     |
| `PROCUREMENT_REQUEST` | required-lite implemented | second domain template |
| `MAINTENANCE_REQUEST` | required-lite implemented | third domain template  |
| `POLICY_INQUIRY`      | cross-cutting             | read-only policy mode  |
| `UNKNOWN`             | required                  | safe fallback          |

Stage 7 procurement and maintenance_lite support is synthetic and draft-only.
It uses deterministic local data, existing gateway persistence tables, existing
policy/approval/audit foundations and controlled draft actions stored through
`ToolCall.output_payload`. It does not add real procurement connectors,
maintenance / ТОИР connectors, ERP/1C/CMMS integrations, domain DB tables or
production workflow depth.

Stage 8 adds a local/demo backend API and deterministic acceptance eval surface
for the access, procurement and maintenance_lite workflows. The API is an
inbound adapter over application runtimes and persistence; it does not add
production auth, tenant isolation, RBAC, provider selection or real enterprise
connectors.

## 7. Important boundaries

The project must stay inside MVP №1 boundaries.

This project does not implement:

* full service desk;
* real IAM;
* real Jira / 1C / ERP / CRM integration;
* real 1C:TOIR integration;
* deep incident triage;
* deep maintenance workflow;
* deep data quality remediation;
* full procurement or tender response workflow;
* full RAG platform;
* production auth;
* production deployment;
* multi-tenant enterprise security;
* autonomous execution of risky actions without approval.

Future projects may interact with this project only through API / MCP-style boundaries.

Internal code sharing with future MVPs is not required.

## 8. Provider strategy

Primary provider:

* GigaChat.

Required provider for tests:

* deterministic mock provider.

Stretch / spike provider:

* YandexGPT.

Rules:

* no silent fallback from failed real provider to mock;
* real provider calls are manual or explicitly configured;
* default tests must not call real external providers;
* raw provider responses are internal by default;
* secrets must not be logged or stored in public artifacts.

## 9. MCP / tool boundary strategy

The project follows MCP-first strategy.

Preferred path:

* real MCP server exposing selected tools.

Fallback path:

* MCP-like FastAPI tool server, if real MCP blocks delivery.

Regardless of implementation path:

* tool schemas must be explicit;
* tool inputs must be validated;
* state-changing tools must pass policy checks;
* risky actions must require approval;
* all meaningful tool calls must be auditable.

## 10. UI strategy

Backend priority is 100%.

The project is demonstrable through the local/demo backend API first.

Web UI should be implemented only after backend acceptance.

If implemented, UI must show:

* request input;
* run status;
* structured decision summary;
* tool call timeline;
* approval panel;
* audit timeline;
* eval summary.

UI must not own business logic.

## 11. Development approach

Development proceeds through staged work.

Each Stage starts with Stage framing before detailed Step discussions are defined.

Current accepted top-level Stage Plan:

```text
Stage 0 — Project Orientation & Stage Plan
Stage 1 — Repo Bootstrap & Public/Private Boundary
Stage 2 — Source-of-Truth Docs
Stage 3 — Provider & MCP Technical Spike
Stage 4 — Core Gateway Foundation
Stage 5 — Access Request Reference Workflow
Stage 6 — GigaChat & MCP Hardening
Stage 7 — Demo Template Expansion
Stage 8 — Backend API, Evals & Acceptance Coverage
Stage 9 — Web UI Demo Surface
Stage 10 — Documentation, Packaging & Portfolio Case
Stage 11 — Final Review, Fix-loop & Public Release
```

This plan is a high-level map, not a fixed Step breakdown.

Each Stage must be refined through Stage-specific discussion, accepted decisions, a Stage Brief, implementation, review and fix-loop.

## 12. Current accepted technical direction

Current accepted technical direction:

* Python 3.14 first;
* downgrade only if required by dependency incompatibility;
* FastAPI;
* Pydantic v2;
* pydantic-settings;
* SQLAlchemy async;
* SQLite for MVP;
* httpx async;
* pytest;
* ruff;
* pyright;
* uv.

## 13. Documentation update rule

This document must reflect accepted current project facts.

If implementation changes project scope, capabilities, provider behavior, public boundaries, or accepted limitations, this document must be updated.

Do not treat temporary reports, notes, chat outputs, or implementation drafts as durable project context unless accepted into this file or another source-of-truth project document.
