"""Deterministic API-level eval runner."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

from enterprise_ai_tool_gateway.api.http.app import create_app
from enterprise_ai_tool_gateway.evals.cases import EvalCase, acceptance_cases
from enterprise_ai_tool_gateway.evals.providers import install_provider_dependency_overrides
from enterprise_ai_tool_gateway.evals.results import EvalCaseResult, EvalSuiteResult

SAFE_SUMMARY_FORBIDDEN_TERMS = ("authorization", "bearer", "secret", "token")
ACTION_DRAFT_TOOL_NAMES = {
    "create_access_request_draft",
    "create_purchase_request_draft",
    "create_work_order_draft",
}


def run_suite(suite: str = "acceptance") -> EvalSuiteResult:
    if suite != "acceptance":
        raise ValueError("Only the deterministic acceptance suite is supported.")
    return run_cases(acceptance_cases(), suite=suite)


def run_cases(cases: Sequence[EvalCase], *, suite: str = "acceptance") -> EvalSuiteResult:
    with TemporaryDirectory(prefix="gateway-api-evals-") as temp_dir:
        base_path = Path(temp_dir)
        results = tuple(_run_case(case, base_path / f"{case.case_id}.sqlite3") for case in cases)
    return EvalSuiteResult(suite=suite, cases=results)


def format_text_report(result: EvalSuiteResult) -> str:
    lines = [
        f"Suite: {result.suite}",
        f"Total: {result.total}  Passed: {result.passed}  Failed: {result.failed}",
        "",
        "Case                                      Result  Initial              Final",
        "----                                      ------  -------              -----",
    ]
    for case in result.cases:
        status = "PASS" if case.passed else "FAIL"
        lines.append(
            f"{case.case_id:<41} {status:<6} "
            f"{case.initial_status or '-':<20} {case.final_status or '-'}"
        )
        for failure in case.failures:
            lines.append(f"  - {failure}")
    return "\n".join(lines)


def _run_case(case: EvalCase, database_path: Path) -> EvalCaseResult:
    failures: list[str] = []
    initial_status: str | None = None
    final_status: str | None = None
    initial_http_status: int | None = None

    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    app = create_app(database_url=database_url)
    install_provider_dependency_overrides(app, case.provider_overrides)
    with TestClient(app) as client:
        response = client.post(case.submit_path, json=case.request_body)
        initial_http_status = response.status_code
        if response.status_code != case.expected_http_status:
            failures.append(
                f"expected HTTP {case.expected_http_status}, got {response.status_code}"
            )
            return _result(case, failures, initial_http_status, initial_status, final_status)

        payload = response.json()
        initial_status = _run_status(payload)
        _assert_initial_response(case, payload, failures)

        final_payload = payload
        if case.approval_decision is not None:
            final_payload = _resolve_approval(case, client, payload, failures)

        final_status = _run_status(final_payload)
        run_id = _run_id(final_payload) or _run_id(payload)
        if run_id is None:
            failures.append("response did not include run.id")
            return _result(case, failures, initial_http_status, initial_status, final_status)

        detail = _read_run_detail(client, run_id, failures)
        if detail is not None:
            final_status = _run_status(detail)
            _assert_final_detail(case, detail, failures)
            _assert_related_endpoints(client, run_id, detail, failures)

    return _result(case, failures, initial_http_status, initial_status, final_status)


def _resolve_approval(
    case: EvalCase,
    client: TestClient,
    payload: dict[str, Any],
    failures: list[str],
) -> dict[str, Any]:
    approval = payload.get("approval")
    run_id = _run_id(payload)
    if not isinstance(approval, dict) or run_id is None:
        failures.append("approval case did not return approval/run_id")
        return payload

    resolve_body = {
        "run_id": run_id,
        "status": case.approval_decision,
        "decided_by": "eval-approver",
        "decision_comment": "Eval decision.",
    }
    response = client.post(
        f"/api/v1/approvals/{approval['id']}/resolve",
        json=resolve_body,
    )
    if response.status_code != 200:
        failures.append(f"approval resolve expected HTTP 200, got {response.status_code}")
        return payload
    resolved_payload = response.json()
    expected_status = case.expected_status_after_approval
    if expected_status is not None and _run_status(resolved_payload) != expected_status:
        failures.append(
            f"expected final status {expected_status}, got {_run_status(resolved_payload)}"
        )

    if case.check_second_resolve_conflict:
        second = client.post(f"/api/v1/approvals/{approval['id']}/resolve", json=resolve_body)
        if second.status_code != 409:
            failures.append(f"second approval resolve expected HTTP 409, got {second.status_code}")
    return resolved_payload


def _read_run_detail(
    client: TestClient,
    run_id: str,
    failures: list[str],
) -> dict[str, Any] | None:
    response = client.get(f"/api/v1/runs/{run_id}")
    if response.status_code != 200:
        failures.append(f"run detail expected HTTP 200, got {response.status_code}")
        return None
    return response.json()


def _assert_related_endpoints(
    client: TestClient,
    run_id: str,
    detail: dict[str, Any],
    failures: list[str],
) -> None:
    expected = {
        "tool-calls": len(detail.get("tool_calls", [])),
        "approvals": 1 if detail.get("approval") is not None else 0,
        "audit-events": len(detail.get("audit_events", [])),
    }
    for suffix, expected_count in expected.items():
        response = client.get(f"/api/v1/runs/{run_id}/{suffix}")
        if response.status_code != 200:
            failures.append(f"related endpoint {suffix} expected HTTP 200, got {response.status_code}")
            continue
        body = response.json()
        if not isinstance(body, list):
            failures.append(f"related endpoint {suffix} did not return a list")
            continue
        if suffix == "approvals" and len(body) < expected_count:
            failures.append("approvals endpoint returned fewer records than run detail")
        elif suffix != "approvals" and len(body) != expected_count:
            failures.append(
                f"{suffix} endpoint count mismatch: expected {expected_count}, got {len(body)}"
            )


def _assert_initial_response(
    case: EvalCase,
    payload: dict[str, Any],
    failures: list[str],
) -> None:
    status = _run_status(payload)
    if status != case.expected_status:
        failures.append(f"expected initial status {case.expected_status}, got {status}")
    if payload.get("requires_approval") is not case.expected_requires_approval:
        failures.append(
            "requires_approval mismatch: "
            f"expected {case.expected_requires_approval}, got {payload.get('requires_approval')}"
        )
    approval = payload.get("approval")
    if case.expected_requires_approval:
        if not isinstance(approval, dict):
            failures.append("expected pending approval in initial response")
        elif approval.get("status") != "PENDING":
            failures.append(f"expected approval PENDING, got {approval.get('status')}")
        if _draft_created(payload):
            failures.append("approval case created draft output before approval")
        _assert_action_not_executed_before_approval(payload, failures)
    elif approval is not None:
        failures.append("did not expect approval in initial response")
    _assert_final_summary(payload, failures)


def _assert_final_detail(
    case: EvalCase,
    detail: dict[str, Any],
    failures: list[str],
) -> None:
    expected_status = case.expected_status_after_approval or case.expected_status
    status = _run_status(detail)
    if status != expected_status:
        failures.append(f"expected final detail status {expected_status}, got {status}")

    if _draft_created(detail) is not case.expected_draft_created:
        failures.append(
            "draft_created mismatch: "
            f"expected {case.expected_draft_created}, got {_draft_created(detail)}"
        )

    audit_events = detail.get("audit_events", [])
    event_types = {
        str(event.get("event_type"))
        for event in audit_events
        if isinstance(event, dict) and event.get("event_type") is not None
    }
    missing_events = set(case.expected_audit_events) - event_types
    if missing_events:
        failures.append(f"missing audit events: {sorted(missing_events)}")

    if case.expected_reason_codes_any:
        reason_codes = _collect_reason_codes(detail)
        if not set(case.expected_reason_codes_any) & reason_codes:
            failures.append(
                "missing expected reason code; expected any of "
                f"{list(case.expected_reason_codes_any)}, got {sorted(reason_codes)}"
            )

    if case.expected_status == "FAILED_VALIDATION":
        tool_calls = detail.get("tool_calls", [])
        if tool_calls:
            failures.append("FAILED_VALIDATION case unexpectedly persisted tool calls")
        if "RUN_FAILED" not in event_types:
            failures.append("FAILED_VALIDATION case did not include RUN_FAILED audit event")

    _assert_tool_call_statuses(detail, failures)
    _assert_final_summary(detail, failures)


def _assert_tool_call_statuses(detail: dict[str, Any], failures: list[str]) -> None:
    allowed = {
        "PROPOSED",
        "VALIDATED",
        "EXECUTING",
        "SUCCEEDED",
        "FAILED",
        "REJECTED",
        "WAITING_FOR_APPROVAL",
    }
    for tool_call in detail.get("tool_calls", []):
        if not isinstance(tool_call, dict):
            failures.append("tool call record is not an object")
            continue
        status = tool_call.get("status")
        if status not in allowed:
            failures.append(f"unexpected tool call status {status}")


def _assert_action_not_executed_before_approval(
    payload: dict[str, Any],
    failures: list[str],
) -> None:
    for tool_call in payload.get("tool_calls", []):
        if not isinstance(tool_call, dict):
            continue
        if tool_call.get("tool_name") not in ACTION_DRAFT_TOOL_NAMES:
            continue
        if tool_call.get("status") == "SUCCEEDED":
            failures.append("approval action tool succeeded before approval")
        output_payload = tool_call.get("output_payload")
        if isinstance(output_payload, dict) and output_payload.get("status") == "draft":
            failures.append("approval action tool produced draft output before approval")


def _assert_final_summary(payload: dict[str, Any], failures: list[str]) -> None:
    summary = payload.get("final_summary")
    if summary is None and isinstance(payload.get("run"), dict):
        summary = payload["run"].get("final_summary")
    if not isinstance(summary, str) or not summary.strip():
        failures.append("final_summary is missing or empty")
        return
    normalized = summary.lower()
    leaked_terms = [term for term in SAFE_SUMMARY_FORBIDDEN_TERMS if term in normalized]
    if leaked_terms:
        failures.append(f"final_summary contains unsafe terms: {leaked_terms}")


def _draft_created(payload: dict[str, Any]) -> bool:
    for tool_call in payload.get("tool_calls", []):
        if not isinstance(tool_call, dict):
            continue
        output_payload = tool_call.get("output_payload")
        if (
            tool_call.get("status") == "SUCCEEDED"
            and isinstance(output_payload, dict)
            and output_payload.get("status") == "draft"
        ):
            return True
    return False


def _collect_reason_codes(payload: dict[str, Any]) -> set[str]:
    reason_codes: set[str] = set()
    for event in payload.get("audit_events", []):
        if not isinstance(event, dict):
            continue
        event_payload = event.get("payload")
        if isinstance(event_payload, dict):
            reason_codes.update(_reason_codes_from_payload(event_payload))
    for tool_call in payload.get("tool_calls", []):
        if not isinstance(tool_call, dict):
            continue
        output_payload = tool_call.get("output_payload")
        if isinstance(output_payload, dict):
            reason_codes.update(_reason_codes_from_payload(output_payload))
    return reason_codes


def _reason_codes_from_payload(payload: dict[str, Any]) -> set[str]:
    value = payload.get("reason_codes")
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def _run_status(payload: dict[str, Any]) -> str | None:
    run = payload.get("run")
    if isinstance(run, dict):
        status = run.get("status")
        return str(status) if status is not None else None
    return None


def _run_id(payload: dict[str, Any]) -> str | None:
    run = payload.get("run")
    if isinstance(run, dict):
        run_id = run.get("id")
        return str(run_id) if run_id is not None else None
    return None


def _result(
    case: EvalCase,
    failures: list[str],
    initial_http_status: int | None,
    initial_status: str | None,
    final_status: str | None,
) -> EvalCaseResult:
    return EvalCaseResult(
        case_id=case.case_id,
        workflow=case.workflow,
        passed=not failures,
        failures=tuple(failures),
        initial_http_status=initial_http_status,
        initial_status=initial_status,
        final_status=final_status,
    )
