# Руководство по разработке

## 1. Назначение

Это руководство объясняет, как разрабатывать, валидировать и безопасно изменять замороженный локальный прототип. Это практический checklist для запуска backend, запуска frontend, выполнения детерминированных evals, сбора review diffs и сохранения границ проекта, которые делают gateway безопасным для инспекции.

Прототип является local/demo software. Он демонстрирует backend-controlled выполнение инструментов, предложенных LLM, для синтетических workflows access, procurement и maintenance. Это не руководство по production deployment.

## 2. Prerequisites

Необходимые локальные tools:

* Python, совместимый с требованием проекта в `pyproject.toml`. Текущее требование проекта — Python `>=3.14`.
* `uv` для управления Python dependencies и выполнения команд.
* Node.js и npm для React/Vite frontend.
* Локальная checkout-копия этого repository.

Default validation и demo runs не требуют real provider credentials. Default provider path — это deterministic mock/fake provider behavior, а default tests/evals не должны вызывать real providers или external enterprise systems.

Windows notes:

* Запускайте команды из корня repository, если раздел явно не требует использовать `frontend/`.
* Для самого быстрого local demo start запустите `run_demo.cmd` из корня repository. Он запускает backend и frontend, пишет logs в `.runtime/logs/` и открывает `http://127.0.0.1:5173/dashboard`.
* Если `npm` установлен, но отсутствует в `PATH`, используйте полный путь к npm executable:
  `C:\Program Files\nodejs\npm.cmd`.

### Windows demo runner

`run_demo.cmd` — это локальный convenience wrapper вокруг
`scripts/demo/run_demo.ps1`. Он запускает FastAPI backend на
`127.0.0.1:8000` и Vite frontend на `127.0.0.1:5173` только если эти services ещё не healthy/reachable.

Runtime files являются локальными artifacts в `.runtime/`:

```text
.runtime/demo-backend.pid
.runtime/demo-frontend.pid
.runtime/logs/backend.log
.runtime/logs/frontend.log
```

Нажмите `Q` в controlling PowerShell window, чтобы остановить только процессы, запущенные этим runner window. Чтобы остановить предыдущий runner-owned demo, выполните:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/demo/stop_demo.ps1
```

Stop script читает только runner PID files и не завершает unrelated процессы Python, Node.js, npm, uvicorn или Vite.

## 3. Backend setup and run

Из корня repository запустите FastAPI backend:

```bash
uv run uvicorn enterprise_ai_tool_gateway.api.http.app:app --reload
```

API версионирован под `/api/v1`. Используйте эти health checks:

```text
http://127.0.0.1:8000/api/v1/health
http://127.0.0.1:8000/api/v1/capabilities
```

Backend root может возвращать 404:

```text
http://127.0.0.1:8000/
```

Это нормально. Backend обслуживает API, а не frontend root page.

По умолчанию local app создаёт SQLite database в `data/`. Local database files являются runtime artifacts и не должны коммититься.

## 4. Frontend setup and run

Во втором терминале при необходимости установите frontend dependencies:

```bash
cd frontend
npm install
```

Запустите Vite dev server на документированном local address:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Откройте основной UI:

```text
http://127.0.0.1:5173/dashboard
```

Frontend API client по умолчанию использует `/api/v1`. Vite dev server проксирует `/api` на `http://localhost:8000`, поэтому backend должен быть запущен на порту 8000 перед использованием UI.

Windows npm fallback:

```text
C:\Program Files\nodejs\npm.cmd
```

Пример:

```powershell
cd frontend
& "C:\Program Files\nodejs\npm.cmd" run dev -- --host 127.0.0.1 --port 5173
```

## 5. Backend validation

Запустите routine backend validation из корня repository:

```bash
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
```

Точное количество tests может меняться по мере развития прототипа, поэтому не hardcode expected count в docs или task handoffs, если repository не устанавливает конкретную convention для текущего момента.

Default backend validation должна оставаться deterministic и offline. Она не должна требовать real provider credentials, network access или real enterprise systems.

## 6. Eval validation

Запустите deterministic API acceptance evals:

```bash
uv run python scripts/run_eval.py
uv run python scripts/run_eval.py --format json
```

Eval runner проверяет public API surface `/api/v1` с deterministic providers и isolated local SQLite state. Это acceptance validation для gateway lifecycle: controlled statuses, approval gating, readback endpoints, audit events, reason codes и failed-validation handling.

Evals используют default mock/static provider path. Они не выполняют real provider calls, external network calls и real connector calls.

## 7. Frontend validation

Запустите frontend validation из `frontend/`:

```bash
cd frontend
npm run typecheck
npm run build
```

В текущем прототипе нет full frontend E2E harness. Перед принятием demo-facing frontend changes выполните manual browser smoke по основным routes и workflows.

## 8. Manual smoke checklist

При запущенных backend и frontend проверьте основные routes:

* `/dashboard`
* `/workflows`
* `/runs`
* `/settings`

Затем пройдите основные workflow paths:

* Access submit с документированными known-good access values.
* Procurement approval path, включая pending approval и approval resolution.
* Maintenance default/safe path с known-good low-severity values.

Для созданного run проверьте:

* `/runs/{run_id}`
* `/runs/{run_id}/approvals`
* `/runs/{run_id}/tool-calls`
* `/runs/{run_id}/audit`

Smoke expectations:

* нет blank screen;
* API status healthy;
* provider mode — `mock`;
* model selection disabled;
* controlled statuses безопасно отображаются, включая `COMPLETED`,
  `WAITING_FOR_APPROVAL`, `NEEDS_USER_INPUT`, `NEEDS_MANUAL_REVIEW`,
  `REJECTED`, `FAILED_VALIDATION`, `FAILED_TOOL` и `FAILED_PROVIDER`;
* approval-required workflows не показывают completed draft до approval;
* run-scoped tool calls и audit records видимы.

## 9. Diff and review workflow

Для review loops используйте staged-baseline workflow, когда это помогает отделить уже принятые changes от последующих fix-loop edits. Не делайте commit во время этого workflow, если task явно не просит commit.

Перед fix-loop добавьте accepted baseline в staged без commit:

```powershell
git status --short --untracked-files=all
git add <accepted-files>
git -c core.quotepath=false diff --cached --output=accepted-baseline.diff
```

После fix-loop edits соберите unstaged delta:

```powershell
git -c core.quotepath=false diff --output=fix-loop-delta.diff
git diff --check
```

Проверьте delta. Если fix-loop changes приняты, намеренно обновите staged baseline:

```powershell
git add <accepted-fix-files>
git -c core.quotepath=false diff --cached --output=accepted-baseline.diff
```

Предпочитайте `git diff --output=...` вместо PowerShell `Out-File` для patch/diff files. Это позволяет избежать случайных encoding changes, из-за которых review artifacts сложнее apply или compare.

Держите review diffs сфокусированными. Не смешивайте unrelated cleanup, generated output, local cache changes или unrelated documentation edits в одном review set.

## 10. Repo hygiene

Не коммитьте local dependency, build, cache, secret или review artifacts:

* `frontend/node_modules/`
* `frontend/dist/`
* `frontend/.vite/`
* `.env` или secret-bearing files
* local SQLite databases, logs и runtime data
* temporary task/report/plan/diff artifacts в `docs/codex/` или других ignored working directories

Держите generated reports и diffs вне final commits, если task явно не требует committed artifact. Перед commit любых изменений проверьте:

```bash
git status --short --untracked-files=all
git diff --check
```

## 11. Boundary rules for changes

Сохраняйте эти boundaries при изменении прототипа:

* Frontend code должен обращаться к backend только через `/api/v1`.
* Frontend code не должен импортировать backend Python internals.
* API routes должны оставаться thin adapters поверх application runtimes.
* Application runtimes владеют orchestration, workflow decisions и approval resolution behavior.
* Backend владеет provider-output validation, tool execution, policy checks,
  approval gates, audit creation и persistence coordination.
* Provider output считается недоверенным, пока backend schema и runtime validation не примут его.
* Tool execution должно проходить через `ToolRegistry` / `ToolExecutor` или explicit MCP/MCP-like boundary.
* Unknown, disallowed или unregistered tool proposals должны завершаться validation failure.
* State-changing tools требуют policy checks.
* Risky или approval-required state-changing tools требуют approval перед draft execution.
* Public API responses должны использовать safe projection/redaction для tool payloads,
  approval free-text fields и audit payloads.
* Default tests и evals не должны выполнять real provider или external network calls.

## 12. Common troubleshooting

`npm` отсутствует в `PATH`:

Используйте полный путь к Windows executable:

```text
C:\Program Files\nodejs\npm.cmd
```

Backend root `/` возвращает 404:

Используйте `/api/v1/health`, `/api/v1/capabilities` или frontend dashboard. 404 от `/` — это нормально.

Frontend не может достучаться до API:

Убедитесь, что backend запущен на порту 8000. Frontend вызывает `/api/v1`, а Vite проксирует `/api` на `http://localhost:8000`.

Vite port conflict:

По возможности используйте документированный explicit port:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Если другой process уже занимает port, остановите этот process или выберите другой local port и откройте URL, который напечатает Vite.

CRLF/LF Git warnings:

Проверьте diff перед commit. Line-ending warnings обычно связаны с local Git configuration, но final diff должен оставаться readable и не должен включать unrelated whole-file churn.

Maintenance возвращает `FAILED_TOOL` для arbitrary non-default input:

Считайте это controlled backend failure state. Используйте documented known-good maintenance values для default/safe smoke path, затем проверьте run detail, tool calls и audit trail.

FastAPI или Starlette `TestClient` warning:

Если pytest выводит `TestClient` warning, но tests всё ещё проходят, зафиксируйте это в handoff как dependency/tooling warning. Не считайте это real-provider или connector failure и не маскируйте failing tests.

## 13. Related documents

Related source-of-truth and companion documents:

* [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
* [ARCHITECTURE.md](ARCHITECTURE.md)
* [PROJECT_MAP.md](PROJECT_MAP.md)
* [API_AND_EVALS.md](API_AND_EVALS.md)
* [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md)
* [README.md](../README.md)

`README.md` — это public quickstart. Если он будет переписан позже, держите его commands согласованными с этим guide и текущими repository entrypoints.
