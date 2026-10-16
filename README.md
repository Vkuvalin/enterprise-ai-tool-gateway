# Enterprise AI Tool Gateway

## 1. Что это

Enterprise AI Tool Gateway — это локальный/demo-прототип контролируемого выполнения инструментов LLM для синтетических enterprise workflows: модель предлагает structured decisions, backend валидирует их, tools выполняются только через controlled backend boundaries, approval ограничивает risky actions, audit фиксирует lifecycle evidence, а web UI отображает controlled lifecycle через `/api/v1`.

Это не chatbot, не автономное прямое использование tools со стороны LLM и не production SaaS platform.

## Демонстрация

Видео работы расширения и примеры его интерфейса.

[Смотреть видео](https://github.com/user-attachments/assets/d8f6e8f7-d521-42de-986b-02f59fa2bdbc)

### Images

<img width="3831" height="2048" alt="Dashboard" src="https://github.com/user-attachments/assets/780fb52a-6d07-410c-9b6a-e8f4d09686ec" />

<img width="3831" height="2051" alt="Run Detail" src="https://github.com/user-attachments/assets/b107e7a7-ffbc-4e26-95fb-d444b85a62a2" />

<img width="3832" height="2038" alt="Settings" src="https://github.com/user-attachments/assets/0e1da123-e549-4bb9-b8e6-8cfcc24c2375" />

<img width="3836" height="2047" alt="Workflow submit" src="https://github.com/user-attachments/assets/bab384b7-f723-4c09-b19c-45efa40d5c54" />

<img width="3835" height="2046" alt="Manual review" src="[https://github.com/user-attachments/assets/2349e6b5-0ac2-40c7-9b06-1e4f6912b244](https://github.com/user-attachments/assets/2349e6b5-0ac2-40c7-9b06-1e4f6912b244)" />



## 2. Что это демонстрирует

* Controlled gateway lifecycle от workflow submission до final run status.
* Синтетические enterprise workflows для access, procurement и maintenance.
* FastAPI backend с версионированными endpoints `/api/v1`.
* React/Vite frontend как локальная RU/EN web console поверх API; fresh local session по умолчанию использует русский язык.
* Deterministic eval suite для backend/API acceptance behavior.
* Public redaction/projection boundary для run, tool, approval и audit data.

## 3. Архитектура в общих чертах

```mermaid
flowchart LR
    Frontend["Frontend<br/>React/Vite"]
    API["FastAPI<br/>/api/v1"]
    Runtime["Application runtimes"]
    Validation["Provider decision<br/>validation"]
    Controls["Policy / tools<br/>approval / audit"]
    DB[("SQLite")]
    Readback["API readback"]
    Display["Frontend display"]

    Frontend --> API --> Runtime --> Validation --> Controls --> DB
    DB --> Readback --> Display
```

Backend владеет workflow decisions. Frontend отправляет demo requests, resolves approvals через API и отображает backend-controlled readback.

## 4. Текущие возможности

Реализованные capabilities:

* `ACCESS_REQUEST`;
* `PROCUREMENT_REQUEST`;
* `MAINTENANCE_REQUEST`;
* approval flow для risky state-changing draft actions;
* run detail и run-scoped readback;
* registered tool calls с safe public projection;
* audit trail для lifecycle events;
* deterministic eval runner;
* local web console.

## 5. Quickstart

После clean checkout сначала установите frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

Затем используйте быстрый demo runner для Windows:

```text
run_demo.cmd
```

Runner запускает backend и frontend, проверяет их готовность и открывает dashboard. Логи обоих сервисов видны в одном PowerShell-окне и сохраняются в `.runtime/logs/<instance-id>/`. Нажмите `Ctrl+C` для штатной остановки; закрытие окна также завершает все процессы, запущенные этим Runner. `Q` остаётся дополнительным способом остановки. Уже готовые services переиспользуются без передачи ownership. Для explicit cleanup старых проверенных instances используйте `scripts/demo/stop_demo.ps1`. Runner не устанавливает npm dependencies автоматически.

Запустить backend из корня repository:

```bash
uv run uvicorn enterprise_ai_tool_gateway.api.http.app:app --reload
```

Запустить frontend во втором терминале:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Открыть:

```text
http://127.0.0.1:5173/dashboard
http://127.0.0.1:8000/api/v1/health
http://127.0.0.1:8000/api/v1/capabilities
```

Backend root `/` может возвращать 404. Это нормально: backend обслуживает версионированный API, а frontend обслуживается через Vite.

## 6. Validation

Backend validation:

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run python scripts/run_eval.py
uv run python scripts/run_eval.py --format json
```

Frontend validation:

```bash
cd frontend
npm run typecheck
npm run build
```

Default validation использует deterministic mock/static provider paths. Real provider credentials не требуются.

## 7. Demo walkthrough

Используйте [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md) для guided local demo. Он покрывает Access happy path, Procurement approval path, Maintenance default/safe path, Run Detail, Tool Calls, Audit Trail и eval runner.

## 8. Карта документации

* [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) - current prototype scope,
  implemented workflows, safety status и intentional non-goals.
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - system architecture, request
  lifecycle, tool boundary, approval boundary, audit/redaction model и
  limitations.
* [docs/PROJECT_MAP.md](docs/PROJECT_MAP.md) - repository structure, package
  ownership, entrypoints и boundary rules.
* [docs/API_AND_EVALS.md](docs/API_AND_EVALS.md) - public API surface,
  controlled outcomes, redaction behavior и deterministic eval suite.
* [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md) - step-by-step local
  demo scenarios для backend и frontend.
* [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) - local setup,
  validation commands, smoke checks и safe development workflow.

## 9. Известные ограничения

* Только local/demo.
* Mock provider path по умолчанию.
* Synthetic workflow data.
* Нет authentication, RBAC или tenants.
* Нет real enterprise connectors.
* Нет provider/model selection.
* Нет deployment, hosting или payment support.
* Нет production security hardening.
* Frontend использует browser-local known-run index, а не global backend listing.

## 10. Статус

Этот repository представляет текущий frozen local/demo prototype. Реализация feature-complete для documented demo scope, а future ideas должны рассматриваться как backlog, а не implemented capabilities.

Используйте public docs в `docs/` как текущий source of truth.
