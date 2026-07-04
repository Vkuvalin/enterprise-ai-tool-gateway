# LLM Provider Policy

## 1. Purpose

This document defines the current provider, model, structured-output, tool-calling and safety policy for `enterprise-ai-tool-gateway`.

It is a project source-of-truth document for provider-related development decisions.

This is not an API reference and not a provider comparison report.

Current status: Stage 6 provider and MCP boundary hardening is implemented for
MVP use. The implementation remains practical and bounded, not a production
provider platform.

Stage 6 hardens optional/manual GigaChat use, deterministic structured-output
validation, safe provider errors, and a local fake MCP external boundary while
keeping default tests deterministic and offline.

---

## 2. Provider Strategy

Accepted provider strategy:

| Provider      | Status                | Purpose                                                                   |
| ------------- | --------------------- | ------------------------------------------------------------------------- |
| Mock provider | required              | Deterministic local tests, evals and development baseline.                |
| GigaChat      | primary real provider | Main real provider for MVP.                                               |
| YandexGPT     | stretch / spike       | Secondary provider if integration is feasible without breaking MVP scope. |

MVP acceptance requires:

* deterministic mock provider;
* GigaChat adapter or clearly bounded GigaChat integration path;
* manual real-provider smoke path;
* no real provider calls in default tests.

YandexGPT is not required for MVP acceptance unless explicitly promoted from stretch to required scope later.

---

## 3. Provider Selection Rationale

The project targets the Russian enterprise context.

The MVP should demonstrate practical ability to work with at least one domestic LLM provider directly.

GigaChat is selected as the primary real provider for the first MVP implementation.

YandexGPT remains a planned spike/stretch provider to check how easily the architecture can support a second domestic model.

The project should avoid becoming a multi-provider benchmark in the MVP phase.

---

## 4. Provider Abstraction

The runtime must use a provider abstraction.

Planned provider port:

```text id="xv837n"
LLMProviderPort
→ generate_structured_decision(request)
→ LLMDecisionPayload-compatible response
```

Provider adapters should hide provider-specific details from workflow orchestration.

Workflow code must not depend directly on:

* provider SDK internals;
* provider-specific HTTP payload shape;
* provider-specific auth mechanics;
* provider-specific raw response format.

The workflow layer should receive a normalized response that validates through
`LLMDecisionPayload`. Provider-specific HTTP response parsing stays inside the
provider adapter.

---

## 5. Required Providers

## 5.1. Mock Provider

The mock provider is required.

Purpose:

* deterministic tests;
* deterministic evals;
* local development without external API calls;
* reproducible behavior during workflow development.

Rules:

* mock provider may be the default local provider;
* mock provider must not silently replace a failed real provider;
* mock provider outputs should represent expected structured decisions;
* mock provider should support success and failure scenarios.

The mock provider is not a proof of real model behavior.

---

## 5.2. GigaChat Provider

GigaChat is the primary real provider.

Purpose:

* demonstrate direct domestic LLM integration;
* test structured decision generation;
* test provider error handling;
* test manual smoke flow;
* validate provider adapter design.

Rules:

* GigaChat calls must be explicitly configured;
* missing or placeholder credentials must fail early;
* provider errors must be mapped to safe application errors;
* raw provider responses must not become normal user-facing output;
* secrets must not be logged;
* default tests must not call GigaChat.

Stage 3 verified a direct `httpx` GigaChat path as the preferred implementation
candidate.

Manual GigaChat PERS smoke confirmed auth, token acquisition, model listing and simple chat completion.

Strict `response_format=json_schema` structured output was not accepted in the current personal-account path. The provider may return JSON-like text that still requires backend parsing and strict schema validation.

The MVP must not depend on provider-enforced schema compliance for GigaChat PERS. Backend validation remains mandatory.

Implemented Stage 6 details:

* token acquisition uses the OAuth endpoint configured by `GIGACHAT_AUTH_URL`;
* chat completions use a configurable `GIGACHAT_BASE_URL` and `/chat/completions`;
* `GIGACHAT_AUTHORIZATION_KEY` is the only supported GigaChat secret env;
* the previous API-key alias is not supported and is treated as missing config;
* access tokens are cached only in the provider instance and are refreshed when
  expiry information requires it;
* every real HTTP call uses explicit timeout and bounded retries;
* retries are limited to transient transport, rate-limit and 5xx failures;
* provider HTTP, transport, response and schema failures map to safe provider
  errors with redacted context;
* structured decisions are parsed from model text by deterministic extraction,
  `json.loads`, `LLMDecisionPayload` validation and runtime validation;
* provider-native function calling is not used in Stage 6.

The OpenAI SDK was not added during the spike because the direct HTTP path is
sufficient for request-shape validation and avoids an unnecessary dependency.

---

## 5.3. YandexGPT Provider

YandexGPT is stretch / spike scope.

Purpose:

* validate whether the provider abstraction supports a second domestic provider;
* compare implementation friction at a high level;
* optionally run a small manual smoke if feasible.

Rules:

* YandexGPT must not delay MVP completion unless explicitly promoted to required scope;
* YandexGPT adapter can remain stubbed or deferred if GigaChat path is enough for MVP;
* any Yandex-specific behavior must be documented after verification.

Stage 3 left YandexGPT as a deferred adapter stub. The provider boundary can host
a Yandex settings object and fail early on missing or placeholder credentials,
but no real YandexGPT adapter or smoke script is required for MVP progress unless
the provider is explicitly promoted from stretch scope.

---

## 6. Provider Configuration

Current environment variables:

```env id="ipf9yf"
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

* `.env.example` may contain placeholders only;
* real `.env` must not be committed;
* `GIGACHAT_AUTHORIZATION_KEY` is the only supported name for the Basic
  Authorization key used by the OAuth request;
* older GigaChat secret aliases are not supported;
* placeholder values such as `change_me` must be rejected for real provider calls;
* provider-specific secrets must not appear in logs, audit events, screenshots or public docs.

---

## 7. Structured Output Policy

The runtime must treat LLM output as untrusted until validated.

The preferred model output is a structured decision compatible with the project schema.

Planned decision schema includes:

```text id="xlt2ra"
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

* raw model text is untrusted;
* structured decision parsing uses deterministic JSON object extraction,
  `json.loads`, `LLMDecisionPayload.model_validate(...)`, then runtime semantic
  validation;
* accepted provider text shapes are a single JSON object, one fenced JSON object,
  or one balanced top-level JSON object surrounded by text;
* zero JSON objects, multiple JSON objects, invalid JSON and non-object JSON
  roots fail safely;
* no fuzzy repair is allowed: no JSON5, YAML, comment stripping, trailing comma
  repair, enum autocorrection, tool-name fuzzy matching, automatic reprompting
  or multiple-candidate selection;
* unknown enum values must fail validation;
* unknown tool names must fail validation;
* malformed arguments must fail validation;
* invalid structured output must not execute tools;
* fallback parsing must not bypass validation.

If a provider does not support strict structured output directly, the adapter may parse provider text into a structured payload only if validation remains strict.

---

## 8. Tool / Function Calling Policy

The LLM may propose tool calls.

The LLM must not execute tools directly.

Backend owns:

* available tool registry;
* tool input schemas;
* tool output schemas;
* tool permission metadata;
* tool validation;
* tool execution;
* policy checks;
* approval gates;
* audit trail.

Provider-native function/tool calling is out of Stage 6 scope. Model-suggested
tool calls are represented only as validated structured payload proposals.

Rules:

* model-suggested tool calls are proposals;
* backend decides whether a tool call is valid;
* backend decides whether a tool call requires approval;
* backend executes tools only through the controlled ToolRegistry boundary;
* MCP is an optional external tool boundary, not the canonical internal
  ToolRegistry;
* state-changing tools must not run before policy and approval checks.

---

## 9. MCP / Tool Boundary Relation

MCP or MCP-like tool server is an integration boundary.

MCP is not the safety model by itself.

Safety remains backend-owned through:

* schema validation;
* tool registry;
* policy checks;
* approval gates;
* audit trail;
* safe error handling.

Current positioning:

```text id="evxwna"
LLM structured decision
→ backend validation
→ ToolRegistry
→ optional MCP / external boundary
→ tool execution
→ audit
```

ToolRegistry remains the canonical internal tool boundary. MCP is optional and
external. Stage 5 access runtime is not rewritten to MCP.

Stage 6 includes a local deterministic fake MCP boundary for
`get_demo_system_status`. It validates typed input/output, normalizes safe MCP
errors and is covered by offline tests. It does not connect to real IAM, HR,
CRM, ERP, CMDB or other enterprise systems.

---

## 10. Real Provider Smoke Policy

Manual real-provider smoke tests are allowed.

They must be explicit.

Required properties:

* disabled by default;
* require both the environment flag and the per-run `--live` flag;
* require real non-placeholder credentials;
* print safe summaries only;
* avoid exposing raw provider payloads unless explicitly safe;
* never run as part of default pytest.

Suggested flag:

```env id="t74wp1"
ENABLE_REAL_PROVIDER_SMOKE=1
```

Current manual smoke entrypoints:

```text
uv run python scripts/manual_gigachat_smoke.py --live --matrix lite,pro,max
uv run python scripts/mcp_smoke.py
```

`scripts/manual_gigachat_smoke.py` is skipped unless both
`ENABLE_REAL_PROVIDER_SMOKE=1` is set in the project-root `.env` and `--live` is
passed for that run. It loads project-root `.env` values, rejects placeholder
credentials, enables `truststore` for local Windows/root-certificate
compatibility, and prints only safe normalized diagnostics.

The GigaChat matrix checks Lite, Pro and Max model aliases and prints:

```text
local_extract | ok/fail
model | auth | chat | structured_decision | schema_valid | stable_enums | stable_tools | usable_for_demo | reason
```

The MCP smoke script is local/fake only and checks:

```text
local_boundary | fastmcp_tool | tool_discovery | tool_call | schema_validation | safe_error_mapping
```

Manual smoke should verify:

* provider auth works;
* simple structured decision call works;
* provider errors are safely mapped;
* no secrets are printed;
* result can be validated by project schema.

---

## 11. Eval Policy

Default evals should use the deterministic mock provider.

Eval scenarios should test workflow behavior, not only provider text quality.

Planned metrics:

```text id="u0ot3q"
schema_valid_rate
request_type_accuracy
missing_fields_accuracy
tool_selection_accuracy
approval_detection_accuracy
forbidden_action_block_rate
final_status_accuracy
```

Real provider evals may be added later as manual or opt-in runs.

Real provider evals must not be treated as deterministic tests.

---

## 12. Error Handling Policy

Provider errors must be mapped to safe application errors.

Error categories may include:

```text id="4ru5v2"
PROVIDER_AUTH_ERROR
PROVIDER_TIMEOUT
PROVIDER_RATE_LIMIT
PROVIDER_INVALID_RESPONSE
PROVIDER_UNAVAILABLE
LLM_OUTPUT_VALIDATION_ERROR
```

Stage 6 provider errors include:

```text
ProviderConfigurationError
ProviderAuthenticationError
ProviderTransportError
ProviderRateLimitError
ProviderResponseError
ProviderSchemaValidationError
ProviderModelUnavailableError
```

Provider errors expose safe context only:

```text
safe_message
reason_code
provider_name
model_name
```

Rules:

* user-facing errors must be safe;
* raw provider exceptions must not leak to normal users;
* stack traces must not be exposed through API;
* internal error details may be recorded only after redaction;
* failed provider call must not silently switch to mock.

---

## 13. Audit and Logging Policy

Audit should record meaningful provider-related events:

* provider selected;
* model name, if safe;
* schema version;
* decision validation status;
* provider error category;
* latency metadata, if available;
* final workflow status.

Audit must not record:

* API keys;
* bearer tokens;
* authorization headers;
* raw secrets;
* full sensitive provider payloads by default;
* unredacted internal stack traces.

Raw provider response, if persisted at all, must be internal-only and safe by design.

---

## 14. No Silent Fallback Rule

The project must not silently hide provider failures.

Forbidden:

```text id="l8ok5n"
GigaChat fails → silently use mock → return success
```

Allowed:

```text id="z9amxr"
GigaChat fails → return safe provider error
GigaChat not configured → fail early for real provider mode
mock mode explicitly configured → use mock
```

A fallback between real providers may be considered in a later stage, but it is not MVP scope.

---

## 15. Default Test Boundary

Default tests must be offline and deterministic.

Default tests must not require:

* GigaChat credentials;
* Yandex credentials;
* network access;
* real provider availability;
* real enterprise integrations.

Provider adapters should be tested with fake transports or mocked HTTP clients unless running explicit manual smoke.

---

## 16. Public Documentation Boundary

Public documentation may describe:

* accepted provider strategy;
* mock/GigaChat/Yandex roles;
* structured-output policy;
* tool-calling policy;
* safety boundaries;
* manual smoke boundary.

Public documentation must not include:

* real credentials;
* private tokens;
* raw provider logs with sensitive data;
* paid account details;
* local secrets;
* private operational notes.

---

## 17. Update Rule

This document must be updated when:

* provider strategy changes;
* GigaChat implementation details are verified;
* Yandex moves from stretch to required scope;
* structured output strategy changes;
* tool/function calling strategy changes;
* real-provider smoke commands change;
* default tests start or stop using any provider-related behavior;
* provider error handling changes.

Do not describe unverified provider behavior as implemented fact.
