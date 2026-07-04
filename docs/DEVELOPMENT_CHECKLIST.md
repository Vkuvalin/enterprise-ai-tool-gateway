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

Stage 7 procurement and maintenance_lite tests must remain offline and
deterministic. They must not call real procurement, ERP, 1C, CMMS, EAM, TOIR,
vendor, asset, budget, work-order or provider systems. New demo template tests
should cover:

* completed path;
* approval path;
* missing input;
* manual review;
* rejected path;
* unknown tool proposal;
* audit and persistence records;
* draft output stored through `ToolCall.output_payload`.

## 3. Manual Smoke Boundary

Real provider and MCP smoke checks are manual/explicit only.

Allowed manual utilities include:

```bash
uv run python scripts/mcp_smoke.py
uv run python scripts/manual_gigachat_smoke.py --live --matrix lite,pro,max
```

Real provider smoke must be disabled by default, require both an explicit
environment opt-in flag and the per-run `--live` flag, reject placeholder
credentials, and print safe summaries only.

GigaChat manual smoke uses:

```env
ENABLE_REAL_PROVIDER_SMOKE=1
GIGACHAT_AUTHORIZATION_KEY=change_me
GIGACHAT_MODEL=GigaChat-2-Pro
GIGACHAT_TIMEOUT_SECONDS=30
GIGACHAT_MAX_RETRIES=1
GIGACHAT_VERIFY_SSL=true
```

Only `GIGACHAT_AUTHORIZATION_KEY` is supported for the GigaChat secret. Older
GigaChat secret aliases are not supported.

The GigaChat smoke matrix may check Lite, Pro and Max model aliases. Treat
matrix results as manual diagnostics, not deterministic acceptance tests.

The MCP smoke must stay local/fake only and must not call real enterprise
systems.

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
* Provider text must pass deterministic JSON extraction, `json.loads`,
  `LLMDecisionPayload` validation and runtime semantic validation.
* Do not use fuzzy JSON repair, provider-native function calling or real
  provider calls in default pytest.
* Tools execute only through the controlled tool boundary.
* ToolRegistry remains the canonical internal tool boundary; MCP is optional and
  external.
* State-changing tools require policy checks.
* Risky state-changing tools require approval.
* Audit events must not contain secrets.
* DB persistence stores already validated facts and must not own workflow or policy decisions.
* Stage 7 procurement and maintenance_lite controlled actions are synthetic
  draft-only actions and must not add domain DB tables or real connectors.

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
