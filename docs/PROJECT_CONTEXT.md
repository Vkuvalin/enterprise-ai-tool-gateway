# Контекст проекта

## 1. Тезис проекта

Enterprise AI Tool Gateway — это локальный/demo-прототип контролируемого выполнения инструментов LLM для синтетических enterprise-workflows.

Ключевой тезис простой:

```text
LLM proposes.
Backend validates.
Tools execute only through controlled boundaries.
Approval gates risky actions.
Audit records meaningful lifecycle events.
Frontend displays the controlled workflow through /api/v1.
```

Проект не является чат-ботом и не является production SaaS-продуктом. Он демонстрирует, как backend-owned contracts, policy checks, approval gates, tool boundaries и audit records могут управлять действиями, предложенными LLM.

## 2. Что демонстрирует этот прототип

Прототип демонстрирует инженерный паттерн для управляемого использования LLM-инструментов:

* контролируемое выполнение инструментов LLM через runtime-логику, принадлежащую backend;
* строгую валидацию структурированных решений provider перед выполнением инструментов;
* зарегистрированное выполнение инструментов через `ToolRegistry` и `ToolExecutor`;
* policy checks перед state-changing draft actions;
* approval control для рискованных действий до их выполнения;
* видимость tool calls, approvals и audit events в рамках конкретного run;
* разделение между FastAPI backend `/api/v1` и React/Vite frontend;
* детерминированное offline acceptance-тестирование поверх API surface.

Основной жизненный цикл:

```text
request
-> backend run creation
-> provider decision
-> backend validation
-> read tools
-> policy check
-> approval if required
-> controlled draft action or controlled stop
-> audit events
-> final run outcome
```

## 3. Текущее замороженное состояние прототипа

Реализованные слои:

* Backend: Python-пакет в `src/enterprise_ai_tool_gateway/`.
* API: FastAPI adapter, версионированный под `/api/v1`.
* Workflows: три синтетических enterprise-workflows:
  `ACCESS_REQUEST`, `PROCUREMENT_REQUEST` и `MAINTENANCE_REQUEST`.
* Frontend: независимый React + TypeScript + Vite client в `frontend/`.
* Evals: детерминированный acceptance runner с набором из 21 кейса.
* Persistence: локальное SQLite-хранилище через async SQLAlchemy.
* Provider mode: по умолчанию используется детерминированный mock/fake provider path.

Реализованные backend-области включают contracts, workflow transitions, provider ports, tool registry/executor, policy decisions, approval primitives, audit redaction/events, persistence, application runtimes, FastAPI routes и evals.

Реализованные frontend-области включают dashboard, страницы отправки workflow, представления agent run, approvals в рамках run, tool calls, audit trail, settings, API status и локальный known-run index.

## 4. Реализованные workflows

### ACCESS_REQUEST

Назначение: продемонстрировать запрос на управление доступом через контролируемый gateway.

Что демонстрирует:

* read checks для employee, system, access-policy и existing-ticket;
* backend-валидацию provider decision и разрешённых access tools;
* policy decisions перед созданием access request draft;
* approval для высокорискованных изменений доступа, например admin access;
* безопасное отклонение или manual review, когда synthetic policy/data checks не проходят.

Возможные контролируемые outcomes:

* завершённый synthetic access request draft;
* ожидание approval, затем завершение или отклонение после approval resolution;
* needs user input для отсутствующих обязательных полей;
* needs manual review для непроверяемых данных или рисков duplicate/open-ticket;
* rejected by policy;
* failed validation для невалидного provider output или неизвестных tool proposals.

Это не реальная IAM-интеграция.

### PROCUREMENT_REQUEST

Назначение: продемонстрировать контроль расходов, поставщиков и бюджета через тот же gateway-паттерн.

Что демонстрирует:

* synthetic checks для requester, vendor, catalog item, budget/policy и duplicate-request;
* backend-валидацию procurement request type, domain template и tool names;
* policy control перед созданием purchase request draft;
* approval для high-value или approval-required draft actions;
* manual review или rejection для blocked vendors, restricted items, budget issues, duplicates или отсутствующих synthetic data.

Возможные контролируемые outcomes:

* завершённый synthetic purchase request draft;
* ожидание approval, затем завершение или отклонение после approval resolution;
* needs user input для отсутствующих обязательных полей;
* needs manual review при неопределённости synthetic data/policy;
* rejected by policy;
* failed validation для невалидного provider output или неизвестных tool proposals.

Это не реальный procurement, ERP, vendor или tender workflow.

### MAINTENANCE_REQUEST

Назначение: продемонстрировать контроль asset/severity/safety через облегчённый maintenance workflow.

Что демонстрирует:

* synthetic checks для requester, asset, severity classification, duplicate-ticket и maintenance-policy;
* canonical `MaintenanceSeverity` handling с uppercase enum values;
* backend-валидацию maintenance request type, domain template и tool names;
* policy control перед созданием work order draft;
* approval для high-severity work order drafts;
* manual review или rejection для safety concerns, critical/manual-review cases или forbidden maintenance instructions.

Возможные контролируемые outcomes:

* завершённый synthetic work order draft;
* ожидание approval, затем завершение или отклонение после approval resolution;
* needs user input для отсутствующих обязательных полей;
* needs manual review для safety или неопределённости synthetic data/policy;
* rejected by policy;
* failed validation для невалидного provider output или неизвестных tool proposals.

Это не реальная интеграция с CMMS, EAM или maintenance/TOIR.

## 5. Статус Backend/API

Backend предоставляет локальный/demo FastAPI API под `/api/v1`.

Реализованные группы endpoint:

* `GET /api/v1/health`;
* `GET /api/v1/capabilities`;
* `POST /api/v1/access-requests`;
* `POST /api/v1/procurement-requests`;
* `POST /api/v1/maintenance-requests`;
* `POST /api/v1/approvals/{approval_id}/resolve`;
* `GET /api/v1/runs/{run_id}`;
* `GET /api/v1/runs/{run_id}/tool-calls`;
* `GET /api/v1/runs/{run_id}/approvals`;
* `GET /api/v1/runs/{run_id}/audit-events`.

Business outcomes моделируются как controlled run statuses, а не как generic HTTP failures. Например, outcomes rejected, manual-review, user-input и failed-validation могут возвращать HTTP 200 со статусом run, который объясняет controlled stop. HTTP errors всё ещё используются для malformed request bodies, unknown run или approval IDs, invalid approval decisions и state conflicts.

Public API responses используют redacted projection для tool payloads и approval free-text fields. Backend runtime objects могут содержать больше внутренних деталей, чем раскрывают public response DTOs.

## 6. Статус Frontend

Frontend — это независимый React/Vite client в `frontend/`. Он взаимодействует с backend только через `/api/v1` HTTP API client в `frontend/src/api/`.

UI лучше всего понимать как локальную Gateway Operations Console. Она включает:

* Dashboard;
* Workflows;
* workflow submit pages для access, procurement и maintenance;
* Agent Runs;
* run detail;
* Approvals;
* run-scoped Tool Calls;
* run-scoped Audit Trail;
* Settings и API status.

Frontend хранит browser-local known-run index, в котором сохраняются run IDs для текущей demo session. Он не реализует global backend search, global audit search, production approval queue, разделение ролей requester/admin или выполнение business logic.

Это не production requester portal, operator portal, admin portal или monitoring product.

## 7. Статус Provider/model

Default demo и test path используют детерминированные mock/fake providers. Endpoint API capabilities сообщает `provider_mode` как `mock`.

Real-provider smoke не является default demo path и должен оставаться явным и ручным. Silent fallback с failed real provider на mock отсутствует.

API capabilities показывают model selection как disabled:

```text
model_selection.enabled = false
active_profile = "mock"
available_profiles = ["mock"]
```

OpenRouter, Yandex, provider marketplace, provider fallback routing, streaming, quota/billing и frontend model selector не реализованы.

## 8. Статус Data, audit и safety

Прототип использует локальное SQLite-хранилище для gateway records:

* agent runs;
* validated LLM decisions;
* tool calls;
* approvals;
* audit events.

Tool calls, approvals и audit events привязаны к run и доступны через public API read endpoints. Audit events фиксируют значимые lifecycle events, такие как run creation, provider selection, decision validation, tool execution, policy checks, approval requests/decisions, manual review, rejection, completion и failure.

Safety-related behavior в замороженном прототипе включает:

* public API redaction для tool payloads и approval text;
* controlled public projection для run, tool, approval и audit records;
* approval safety floor, чтобы `AUTO_APPROVE` не обходил high-risk, critical-risk или default-approval state-changing controls;
* строгую domain-template validation перед dispatching workflow actions;
* canonical maintenance severity validation через `MaintenanceSeverity`;
* workflow submit bodies не принимают provider/model selection fields;
* public API responses не должны содержать secrets.

## 9. Что намеренно не реализовано

Прототип намеренно не реализует:

* production authentication;
* RBAC;
* tenants;
* real enterprise connectors;
* реальные интеграции IAM, ERP, 1C, Jira, CRM, CMMS или EAM;
* provider/model selection;
* global run search или history;
* global audit search;
* deployment или hosting;
* payment;
* desktop app;
* workflow builder;
* policy editor;
* organization administration;
* production background workers;
* production observability;
* production security hardening.

## 10. Будущие направления

Потенциальный future backlog, не являющийся committed scope:

* реальные интеграции через API или MCP-style boundaries;
* provider profiles и explicit provider selection;
* authentication, RBAC и tenant isolation;
* deployment packaging и hosted environments;
* более развитые admin/operator UI surfaces;
* workflow-builder concepts;
* monitoring, analytics и operational reporting.

Любое будущее расширение должно сохранять control model: backend validation, explicit tool boundaries, policy checks, approval gates и auditability.

## 11. Связанные документы

Существующие companion documents:

* [PROJECT_MAP.md](PROJECT_MAP.md) - architecture map, package ownership,
  runtime ownership и entrypoints.

* [README.md](../README.md) - public quickstart и validation commands.

* [ARCHITECTURE.md](ARCHITECTURE.md) - architecture, lifecycle, boundaries,
  failure model и limitations.

* [API_AND_EVALS.md](API_AND_EVALS.md) - public API surface, controlled
  outcomes и deterministic eval suite.

* [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) - local demo walkthrough для
  backend, frontend и eval runner.

* [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) - setup, validation и safe
  development workflow.
