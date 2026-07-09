# Политика LLM Provider

## 1. Назначение

Этот документ определяет текущую политику provider, model, structured-output, tool-calling и safety для `enterprise-ai-tool-gateway`.

Это source-of-truth документ проекта для provider-related development decisions.

Это не API reference и не provider comparison report.

Текущий статус: Stage 6 provider и MCP boundary hardening реализованы для MVP use. Реализация остаётся практичной и ограниченной, а не production provider platform.

Stage 6 усиливает optional/manual использование GigaChat, deterministic structured-output validation, safe provider errors и локальную fake MCP external boundary, при этом default tests остаются deterministic и offline.

---

## 2. Provider Strategy

Принятая provider strategy:

| Provider      | Status                | Purpose                                                               |
| ------------- | --------------------- | --------------------------------------------------------------------- |
| Mock provider | required              | Deterministic local tests, evals и development baseline.              |
| GigaChat      | primary real provider | Основной real provider для MVP.                                       |
| YandexGPT     | stretch / spike       | Вторичный provider, если интеграция возможна без нарушения MVP scope. |

MVP acceptance требует:

* deterministic mock provider;
* GigaChat adapter или чётко ограниченный GigaChat integration path;
* manual real-provider smoke path;
* отсутствия real provider calls в default tests.

YandexGPT не требуется для MVP acceptance, если позже явно не будет переведён из stretch в required scope.

---

## 3. Provider Selection Rationale

Проект ориентирован на российский enterprise context.

MVP должен продемонстрировать практическую способность работать напрямую как минимум с одним отечественным LLM provider.

GigaChat выбран как primary real provider для первой MVP-реализации.

YandexGPT остаётся planned spike/stretch provider, чтобы проверить, насколько легко architecture может поддержать вторую отечественную model.

Проект не должен превращаться в multi-provider benchmark на MVP phase.

---

## 4. Provider Abstraction

Runtime должен использовать provider abstraction.

Планируемый provider port:

```text
LLMProviderPort
→ generate_structured_decision(request)
→ LLMDecisionPayload-compatible response
```

Provider adapters должны скрывать provider-specific details от workflow orchestration.

Workflow code не должен напрямую зависеть от:

* provider SDK internals;
* provider-specific HTTP payload shape;
* provider-specific auth mechanics;
* provider-specific raw response format.

Workflow layer должен получать normalized response, который проходит validation через `LLMDecisionPayload`. Provider-specific HTTP response parsing остаётся внутри provider adapter.

---

## 5. Required Providers

## 5.1. Mock Provider

Mock provider обязателен.

Назначение:

* deterministic tests;
* deterministic evals;
* local development без external API calls;
* reproducible behavior во время workflow development.

Rules:

* mock provider может быть default local provider;
* mock provider не должен silent replace failed real provider;
* mock provider outputs должны представлять expected structured decisions;
* mock provider должен поддерживать success и failure scenarios.

Mock provider не является доказательством real model behavior.

---

## 5.2. GigaChat Provider

GigaChat — primary real provider.

Назначение:

* продемонстрировать прямую domestic LLM integration;
* протестировать structured decision generation;
* протестировать provider error handling;
* протестировать manual smoke flow;
* валидировать provider adapter design.

Rules:

* GigaChat calls должны быть явно configured;
* missing или placeholder credentials должны fail early;
* provider errors должны map to safe application errors;
* raw provider responses не должны становиться обычным user-facing output;
* secrets не должны логироваться;
* default tests не должны вызывать GigaChat.

Stage 3 verified direct `httpx` GigaChat path как preferred implementation candidate.

Manual GigaChat PERS smoke подтвердил auth, token acquisition, model listing и simple chat completion.

Strict `response_format=json_schema` structured output не был accepted в текущем personal-account path. Provider может возвращать JSON-like text, который всё равно требует backend parsing и strict schema validation.

MVP не должен зависеть от provider-enforced schema compliance для GigaChat PERS. Backend validation остаётся обязательной.

Реализованные детали Stage 6:

* token acquisition использует OAuth endpoint, configured через `GIGACHAT_AUTH_URL`;
* chat completions используют configurable `GIGACHAT_BASE_URL` и `/chat/completions`;
* `GIGACHAT_AUTHORIZATION_KEY` — единственный поддерживаемый GigaChat secret env;
* предыдущий API-key alias не поддерживается и считается missing config;
* access tokens кэшируются только в provider instance и refresh, когда expiry information этого требует;
* каждый real HTTP call использует explicit timeout и bounded retries;
* retries ограничены transient transport, rate-limit и 5xx failures;
* provider HTTP, transport, response и schema failures map to safe provider errors with redacted context;
* structured decisions парсятся из model text через deterministic extraction,
  `json.loads`, `LLMDecisionPayload` validation и runtime validation;
* provider-native function calling не используется в Stage 6.

OpenAI SDK не был добавлен во время spike, потому что direct HTTP path достаточен для request-shape validation и избегает unnecessary dependency.

---

## 5.3. YandexGPT Provider

YandexGPT находится в stretch / spike scope.

Назначение:

* проверить, поддерживает ли provider abstraction второго domestic provider;
* сравнить implementation friction на high level;
* опционально выполнить небольшой manual smoke, если это feasible.

Rules:

* YandexGPT не должен задерживать MVP completion, если явно не переведён в required scope;
* YandexGPT adapter может оставаться stubbed или deferred, если GigaChat path достаточен для MVP;
* любое Yandex-specific behavior должно быть documented после verification.

Stage 3 оставил YandexGPT как deferred adapter stub. Provider boundary может содержать Yandex settings object и fail early при missing или placeholder credentials, но real YandexGPT adapter или smoke script не требуется для MVP progress, если provider явно не переведён из stretch scope.

---

## 6. Provider Configuration

Текущие environment variables:

```env
LLM_PROVIDER=mock

GIGACHAT_AUTHORIZATION_KEY=change_me
GIGACHAT_MODEL=GigaChat-2-Pro
GIGACHAT_BASE_URL=https://gigachat.devices.sberbank.ru/api/v1
GIGACHAT_AUTH_URL=https://ngw.devices.sberbank.ru:9443/api/v2/oauth
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_TIMEOUT_SECONDS=30
GIGACHAT_MAX_RETRIES=1
GIGACHAT_VERIFY_SSL=true

YANDEX_API_KEY=change_me
YANDEX_FOLDER_ID=change_me
YANDEX_MODEL=change_me

ENABLE_REAL_PROVIDER_SMOKE=0
```

Rules:

* `.env.example` может содержать только placeholders;
* real `.env` не должен коммититься;
* `GIGACHAT_AUTHORIZATION_KEY` — единственное поддерживаемое имя для Basic
  Authorization key, используемого OAuth request;
* старые GigaChat secret aliases не поддерживаются;
* placeholder values, такие как `change_me`, должны отклоняться для real provider calls;
* provider-specific secrets не должны попадать в logs, audit events, screenshots или public docs.

---

## 7. Structured Output Policy

Runtime должен считать LLM output недоверенным, пока он не validated.

Предпочтительный model output — structured decision, compatible with project schema.

Planned decision schema включает:

```text
request_type
domain_template
confidence
risk_level
requires_approval
missing_fields
proposed_tool_calls
user_facing_summary
reason_codes
```

Rules:

* raw model text считается недоверенным;
* structured decision parsing использует deterministic JSON object extraction,
  `json.loads`, `LLMDecisionPayload.model_validate(...)`, затем runtime semantic
  validation;
* accepted provider text shapes: single JSON object, one fenced JSON object или one balanced top-level JSON object surrounded by text;
* zero JSON objects, multiple JSON objects, invalid JSON и non-object JSON
  roots fail safely;
* fuzzy repair запрещён: no JSON5, YAML, comment stripping, trailing comma
  repair, enum autocorrection, tool-name fuzzy matching, automatic reprompting
  or multiple-candidate selection;
* unknown enum values должны fail validation;
* unknown tool names должны fail validation;
* malformed arguments должны fail validation;
* invalid structured output не должен execute tools;
* fallback parsing не должен bypass validation.

Если provider не поддерживает strict structured output напрямую, adapter может parse provider text into structured payload только при сохранении strict validation.

---

## 8. Tool / Function Calling Policy

LLM может предлагать tool calls.

LLM не должен выполнять tools напрямую.

Backend владеет:

* available tool registry;
* tool input schemas;
* tool output schemas;
* tool permission metadata;
* tool validation;
* tool execution;
* policy checks;
* approval gates;
* audit trail.

Provider-native function/tool calling находится вне Stage 6 scope. Model-suggested tool calls представлены только как validated structured payload proposals.

Rules:

* model-suggested tool calls являются proposals;
* backend решает, valid ли tool call;
* backend решает, требует ли tool call approval;
* backend выполняет tools только через controlled ToolRegistry boundary;
* MCP — optional external tool boundary, а не canonical internal ToolRegistry;
* state-changing tools не должны запускаться до policy и approval checks.

---

## 9. MCP / Tool Boundary Relation

MCP или MCP-like tool server — это integration boundary.

MCP сам по себе не является safety model.

Safety остаётся backend-owned через:

* schema validation;
* tool registry;
* policy checks;
* approval gates;
* audit trail;
* safe error handling.

Текущее позиционирование:

```text
LLM structured decision
→ backend validation
→ ToolRegistry
→ optional MCP / external boundary
→ tool execution
→ audit
```

ToolRegistry остаётся canonical internal tool boundary. MCP является optional и external. Stage 5 access runtime не переписан на MCP.

Stage 6 включает локальную deterministic fake MCP boundary для `get_demo_system_status`. Она валидирует typed input/output, normalizes safe MCP errors и покрыта offline tests. Она не подключается к real IAM, HR, CRM, ERP, CMDB или другим enterprise systems.

---

## 10. Real Provider Smoke Policy

Manual real-provider smoke tests разрешены.

Они должны быть explicit.

Required properties:

* disabled by default;
* требуют одновременно environment flag и per-run `--live` flag;
* требуют real non-placeholder credentials;
* выводят только safe summaries;
* избегают раскрытия raw provider payloads, если они не являются явно safe;
* never run as part of default pytest.

Suggested flag:

```env
ENABLE_REAL_PROVIDER_SMOKE=1
```

Текущие manual smoke entrypoints:

```text
uv run python scripts/manual_gigachat_smoke.py --live --matrix lite,pro,max
uv run python scripts/mcp_smoke.py
```

`scripts/manual_gigachat_smoke.py` skipped, если одновременно не установлены
`ENABLE_REAL_PROVIDER_SMOKE=1` в project-root `.env` и `--live` не передан для этого run. Он загружает project-root `.env` values, отклоняет placeholder credentials, включает `truststore` для local Windows/root-certificate compatibility и печатает только safe normalized diagnostics.

GigaChat matrix проверяет Lite, Pro и Max model aliases и печатает:

```text
local_extract | ok/fail
model | auth | chat | structured_decision | schema_valid | stable_enums | stable_tools | usable_for_demo | reason
```

MCP smoke script является только local/fake и проверяет:

```text
local_boundary | fastmcp_tool | tool_discovery | tool_call | schema_validation | safe_error_mapping
```

Manual smoke должен проверять:

* provider auth works;
* simple structured decision call works;
* provider errors are safely mapped;
* no secrets are printed;
* result can be validated by project schema.

---

## 11. Eval Policy

Default evals должны использовать deterministic mock provider.

Eval scenarios должны тестировать workflow behavior, а не только provider text quality.

Planned metrics:

```text
schema_valid_rate
request_type_accuracy
missing_fields_accuracy
tool_selection_accuracy
approval_detection_accuracy
forbidden_action_block_rate
final_status_accuracy
```

Real provider evals могут быть добавлены позже как manual или opt-in runs.

Real provider evals не должны считаться deterministic tests.

---

## 12. Error Handling Policy

Provider errors должны map to safe application errors.

Error categories могут включать:

```text
PROVIDER_AUTH_ERROR
PROVIDER_TIMEOUT
PROVIDER_RATE_LIMIT
PROVIDER_INVALID_RESPONSE
PROVIDER_UNAVAILABLE
LLM_OUTPUT_VALIDATION_ERROR
```

Stage 6 provider errors включают:

```text
ProviderConfigurationError
ProviderAuthenticationError
ProviderTransportError
ProviderRateLimitError
ProviderResponseError
ProviderSchemaValidationError
ProviderModelUnavailableError
```

Provider errors раскрывают только safe context:

```text
safe_message
reason_code
provider_name
model_name
```

Rules:

* user-facing errors должны быть safe;
* raw provider exceptions не должны leak to normal users;
* stack traces не должны exposed through API;
* internal error details могут записываться только после redaction;
* failed provider call не должен silently switch to mock.

---

## 13. Audit and Logging Policy

Audit должен фиксировать meaningful provider-related events:

* provider selected;
* model name, if safe;
* schema version;
* decision validation status;
* provider error category;
* latency metadata, if available;
* final workflow status.

Audit не должен фиксировать:

* API keys;
* bearer tokens;
* authorization headers;
* raw secrets;
* full sensitive provider payloads by default;
* unredacted internal stack traces.

Raw provider response, если он вообще persisted, должен быть internal-only и safe by design.

---

## 14. No Silent Fallback Rule

Проект не должен silently hide provider failures.

Forbidden:

```text
GigaChat fails → silently use mock → return success
```

Allowed:

```text
GigaChat fails → return safe provider error
GigaChat not configured → fail early for real provider mode
mock mode explicitly configured → use mock
```

Fallback между real providers может быть рассмотрен на более позднем stage, но это не входит в MVP scope.

---

## 15. Default Test Boundary

Default tests должны быть offline и deterministic.

Default tests не должны требовать:

* GigaChat credentials;
* Yandex credentials;
* network access;
* real provider availability;
* real enterprise integrations.

Provider adapters должны тестироваться через fake transports или mocked HTTP clients, если не запускается explicit manual smoke.

---

## 16. Public Documentation Boundary

Public documentation может описывать:

* accepted provider strategy;
* mock/GigaChat/Yandex roles;
* structured-output policy;
* tool-calling policy;
* safety boundaries;
* manual smoke boundary.

Public documentation не должна включать:

* real credentials;
* private tokens;
* raw provider logs with sensitive data;
* paid account details;
* local secrets;
* private operational notes.

---

## 17. Update Rule

Этот документ должен обновляться, когда:

* provider strategy changes;
* GigaChat implementation details are verified;
* Yandex moves from stretch to required scope;
* structured output strategy changes;
* tool/function calling strategy changes;
* real-provider smoke commands change;
* default tests start or stop using any provider-related behavior;
* provider error handling changes.

Не описывайте unverified provider behavior как implemented fact.
