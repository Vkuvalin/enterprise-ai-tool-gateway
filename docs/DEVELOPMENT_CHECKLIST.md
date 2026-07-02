# Development Checklist

This checklist defines routine development hygiene for `enterprise-ai-tool-gateway`.

It is not the provider policy, architecture map, or task workflow. Provider-specific rules live in `docs/LLM_PROVIDER_POLICY.md`; package ownership and entrypoints live in `docs/PROJECT_MAP.md`; accepted project scope lives in `docs/PROJECT_CONTEXT.md`.

## 1. Routine Validation

Run the default validation before handing off code changes:

```bash
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
```

Before commit, also inspect:

```bash
git status --short --untracked-files=all
```

Docs-only changes do not normally require pytest unless they modify commands, paths, or behavior claims that need verification.

## 2. Test Boundary

Default tests must be deterministic and offline.

Default tests must not require:

* real provider credentials;
* network access;
* GigaChat or Yandex availability;
* real MCP network services;
* real enterprise systems.

Use deterministic mocks, fake transports, local in-memory storage, or local smoke utilities where appropriate.

## 3. Manual Smoke Boundary

Real provider and MCP smoke checks are manual/explicit only.

Allowed manual utilities include:

```bash
uv run python scripts/mcp_smoke.py
uv run python scripts/manual_gigachat_smoke.py
```

Real provider smoke must be disabled by default, require an explicit opt-in flag, reject placeholder credentials, and print safe summaries only.

## 4. Stage 4 Foundation Awareness

Stage 4 core foundation packages are implemented:

```text
contracts/
workflow/
tools/
policy/
approval/
audit/
db/
```

Do not bypass these boundaries when adding later stages:

* LLM output is untrusted until backend validation accepts it.
* Tools execute only through the controlled tool boundary.
* State-changing tools require policy checks.
* Risky state-changing tools require approval.
* Audit events must not contain secrets.
* DB persistence stores already validated facts and must not own workflow or policy decisions.

## 5. Source-of-Truth Docs

Durable project facts belong in source-of-truth docs:

* `docs/PROJECT_CONTEXT.md` for accepted scope, status, non-goals and boundaries;
* `docs/PROJECT_MAP.md` for package map, dependency direction and entrypoints;
* `docs/LLM_PROVIDER_POLICY.md` for provider/model/tool-calling policy;
* `docs/DEVELOPMENT_CHECKLIST.md` for development and validation hygiene.

`docs/codex/` task envelopes, plans, stage briefs and reports are local workflow artifacts. They can inform implementation while active, but they are not durable source of truth.

## 6. Local Artifacts

Do not commit temporary review or patch artifacts.

Local `*.diff` and `*.patch` files are ignored and should remain local unless a task explicitly asks for a committed patch artifact.

Delete completed Codex workflow artifacts when their durable facts have been accepted into source-of-truth docs or code and they are no longer useful for future work.

## 7. Secret Hygiene

Never commit or expose:

* real API keys, bearer tokens, authorization headers or cookies;
* `.env` files with real credentials;
* raw provider logs containing secrets;
* screenshots or docs that reveal private credentials;
* unredacted audit payloads with credential-like fields.

Use placeholders only in public examples and ensure real-provider paths fail early on missing or placeholder credentials.
