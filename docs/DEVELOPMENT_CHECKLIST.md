# Чеклист разработки

Этот checklist определяет routine development hygiene для `enterprise-ai-tool-gateway`.

Это не provider policy, architecture map или task workflow. Provider-specific rules находятся в `docs/LLM_PROVIDER_POLICY.md`; package ownership и entrypoints находятся в `docs/PROJECT_MAP.md`; accepted project scope находится в `docs/PROJECT_CONTEXT.md`.

## 1. Routine Validation

Запускайте default validation перед передачей code changes:

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

Перед commit также проверьте:

```bash
git status --short --untracked-files=all
```

Docs-only changes обычно не требуют pytest, если они не изменяют commands, paths или behavior claims, которые нужно верифицировать.

## 2. Test Boundary

Default tests должны быть deterministic и offline.

Default tests не должны требовать:

* real provider credentials;
* network access;
* доступности GigaChat или Yandex;
* real MCP network services;
* real enterprise systems.

Используйте deterministic mocks, fake transports, local in-memory storage или local smoke utilities там, где это уместно.

Stage 7 procurement и maintenance_lite tests должны оставаться offline и deterministic. Они не должны вызывать реальные procurement, ERP, 1C, CMMS, EAM, TOIR, vendor, asset, budget, work-order или provider systems. Новые demo template tests должны покрывать:

* completed path;
* approval path;
* missing input;
* manual review;
* rejected path;
* unknown tool proposal;
* audit и persistence records;
* draft output, сохранённый через `ToolCall.output_payload`.

Stage 8 API и eval tests должны оставаться offline и deterministic. API tests должны использовать только local test clients, temporary SQLite storage и deterministic mock/fake providers. Eval runner должен проверять endpoints `/api/v1`, а не application runtimes напрямую, и `scripts/run_eval.py` должен проходить до того, как Stage 8 acceptance считается завершённым.

Stage 9 frontend validation должна оставаться local/demo и не должна напрямую вызывать real provider или enterprise network paths. Frontend взаимодействует только с FastAPI `/api/v1` через `frontend/src/api/`, а browser localStorage может хранить только run IDs.

## 3. Manual Smoke Boundary

Real provider и MCP smoke checks являются только manual/explicit.

Разрешённые manual utilities включают:

```bash
uv run python scripts/mcp_smoke.py
uv run python scripts/manual_gigachat_smoke.py --live --matrix lite,pro,max
```

Real provider smoke должен быть disabled by default, требовать одновременно explicit environment opt-in flag и per-run `--live` flag, отклонять placeholder credentials и выводить только safe summaries.

GigaChat manual smoke использует:

```env
ENABLE_REAL_PROVIDER_SMOKE=1
GIGACHAT_AUTHORIZATION_KEY=change_me
GIGACHAT_MODEL=GigaChat-2-Pro
GIGACHAT_TIMEOUT_SECONDS=30
GIGACHAT_MAX_RETRIES=1
GIGACHAT_VERIFY_SSL=true
```

Для GigaChat secret поддерживается только `GIGACHAT_AUTHORIZATION_KEY`. Старые GigaChat secret aliases не поддерживаются.

GigaChat smoke matrix может проверять Lite, Pro и Max model aliases. Рассматривайте matrix results как manual diagnostics, а не как deterministic acceptance tests.

MCP smoke должен оставаться только local/fake и не должен вызывать real enterprise systems.

## 4. Stage 4 Foundation Awareness

Stage 4 core foundation packages реализованы:

```text
contracts/
workflow/
tools/
policy/
approval/
audit/
db/
```

Не обходите эти boundaries при добавлении последующих stages:

* LLM output считается недоверенным, пока backend validation не примет его.
* Provider text должен пройти deterministic JSON extraction, `json.loads`,
  `LLMDecisionPayload` validation и runtime semantic validation.
* Не используйте fuzzy JSON repair, provider-native function calling или real provider calls в default pytest.
* Tools выполняются только через controlled tool boundary.
* ToolRegistry остаётся canonical internal tool boundary; MCP является optional и external.
* State-changing tools требуют policy checks.
* Risky state-changing tools требуют approval.
* Audit events не должны содержать secrets.
* DB persistence сохраняет уже validated facts и не должен владеть workflow или policy decisions.
* Stage 7 procurement и maintenance_lite controlled actions являются synthetic draft-only actions и не должны добавлять domain DB tables или real connectors.
* Stage 8 API routes являются только inbound adapters. Application runtimes владеют workflow orchestration; routes не должны владеть policy, approval, tool execution, workflow transition или audit logic.
* Stage 8 evals являются deterministic acceptance checks, а не model benchmarks, prompt optimization, provider comparison или production observability.
* Stage 9 frontend — это независимый React/Vite client в `frontend/`.
  `frontend/src/api/` владеет HTTP calls к `/api/v1`; случайные UI components не должны вызывать `fetch` напрямую или импортировать backend internals. UI copy не должна заявлять unsupported production/admin features, такие как auth, RBAC, tenants, provider management, policy editing, global audit search или global approval queues.

## 5. Source-of-Truth Docs

Durable project facts должны находиться в source-of-truth docs:

* `docs/PROJECT_CONTEXT.md` — для accepted scope, status, non-goals и boundaries;
* `docs/PROJECT_MAP.md` — для package map, dependency direction и entrypoints;
* `docs/LLM_PROVIDER_POLICY.md` — для provider/model/tool-calling policy;
* `docs/DEVELOPMENT_CHECKLIST.md` — для development и validation hygiene.

`docs/codex/` task envelopes, plans, stage briefs и reports являются local workflow artifacts. Они могут помогать implementation, пока активны, но не являются durable source of truth.

## 6. Local Artifacts

Не коммитьте temporary review или patch artifacts.

Local `*.diff` и `*.patch` files игнорируются и должны оставаться локальными, если task явно не просит committed patch artifact.

Удаляйте completed Codex workflow artifacts, когда их durable facts уже приняты в source-of-truth docs или code и они больше не полезны для future work.

## 7. Secret Hygiene

Никогда не коммитьте и не раскрывайте:

* real API keys, bearer tokens, authorization headers или cookies;
* `.env` files с real credentials;
* raw provider logs, содержащие secrets;
* screenshots или docs, раскрывающие private credentials;
* unredacted audit payloads с credential-like fields.

Используйте только placeholders в public examples и обеспечивайте fail early для real-provider paths при missing или placeholder credentials.
