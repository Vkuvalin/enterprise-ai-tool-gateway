from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from enterprise_ai_tool_gateway.api import create_app
from enterprise_ai_tool_gateway.audit import REDACTED_VALUE
from enterprise_ai_tool_gateway.contracts.enums import DomainTemplate, RequestType
from enterprise_ai_tool_gateway.evals.providers import (
    ACCESS_PROVIDER_KEY,
    ProviderOverrides,
    install_provider_dependency_overrides,
)
from enterprise_ai_tool_gateway.llm import StaticDecisionProvider


def test_access_procurement_and_maintenance_submit_endpoints_complete() -> None:
    with _client() as client:
        access = client.post("/api/v1/access-requests", json=_access_body())
        procurement = client.post("/api/v1/procurement-requests", json=_procurement_body())
        maintenance = client.post("/api/v1/maintenance-requests", json=_maintenance_body())

    assert access.status_code == 200
    assert access.json()["run"]["status"] == "COMPLETED"
    assert _draft_created(access.json())

    assert procurement.status_code == 200
    assert procurement.json()["run"]["status"] == "COMPLETED"
    assert _draft_created(procurement.json())

    assert maintenance.status_code == 200
    assert maintenance.json()["run"]["status"] == "COMPLETED"
    assert _draft_created(maintenance.json())


def test_tool_call_payloads_are_redacted_in_workflow_and_run_readbacks() -> None:
    sensitive_issue = "Routine inspection needed. token=abc123456"
    with _client() as client:
        submitted = client.post(
            "/api/v1/maintenance-requests",
            json=_maintenance_body(issue_description=sensitive_issue),
        )
        assert submitted.status_code == 200
        submitted_body = submitted.json()
        run_id = submitted_body["run"]["id"]

        run_detail = client.get(f"/api/v1/runs/{run_id}")
        tool_calls = client.get(f"/api/v1/runs/{run_id}/tool-calls")

    assert run_detail.status_code == 200
    assert tool_calls.status_code == 200

    for body in [submitted_body, run_detail.json()]:
        draft_call = _tool_call(body["tool_calls"], "create_work_order_draft")
        _assert_redacted_maintenance_draft_call(draft_call)
        assert sensitive_issue not in str(body)

    draft_call = _tool_call(tool_calls.json(), "create_work_order_draft")
    _assert_redacted_maintenance_draft_call(draft_call)
    assert sensitive_issue not in str(tool_calls.json())


def test_business_outcomes_return_http_200() -> None:
    with _client() as client:
        rejected = client.post(
            "/api/v1/access-requests",
            json=_access_body(employee_id="emp-intern-001", access_level="ADMIN"),
        )
        manual = client.post(
            "/api/v1/maintenance-requests",
            json=_maintenance_body(safety_concern=True),
        )

    assert rejected.status_code == 200
    assert rejected.json()["run"]["status"] == "REJECTED"
    assert not _draft_created(rejected.json())

    assert manual.status_code == 200
    assert manual.json()["run"]["status"] == "NEEDS_MANUAL_REVIEW"
    assert not _draft_created(manual.json())


def test_failed_validation_returns_controlled_business_response() -> None:
    provider = StaticDecisionProvider(
        request_type=RequestType.ACCESS_REQUEST,
        domain_template=DomainTemplate.ACCESS,
        proposed_tool_name="delete_access_grant",
        reason_code="TEST_UNKNOWN_TOOL",
        requires_approval=True,
    )
    with _client(provider_overrides={ACCESS_PROVIDER_KEY: provider}) as client:
        response = client.post("/api/v1/access-requests", json=_access_body())

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["status"] == "FAILED_VALIDATION"
    assert body["tool_calls"] == []
    assert body["final_summary"]


def test_malformed_submit_body_returns_422() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/procurement-requests",
            json={**_procurement_body(), "quantity": 0},
        )

    assert response.status_code == 422


@pytest.mark.parametrize("observed_severity", ["low", "unknown"])
def test_maintenance_submit_rejects_non_canonical_observed_severity(
    observed_severity: str,
) -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/maintenance-requests",
            json=_maintenance_body(observed_severity=observed_severity),
        )

    assert response.status_code == 422


def test_submit_body_rejects_provider_model_selection_fields() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/access-requests",
            json={
                **_access_body(),
                "provider": "gigachat",
                "model": "GigaChat-2-Pro",
                "gpt_model": "gpt-test",
            },
        )

    assert response.status_code == 422


@contextmanager
def _client(
    *,
    provider_overrides: ProviderOverrides | None = None,
) -> Iterator[TestClient]:
    with TemporaryDirectory(prefix="gateway-api-test-") as temp_dir:
        database_url = f"sqlite+aiosqlite:///{(Path(temp_dir) / 'api.sqlite3').as_posix()}"
        app = create_app(database_url=database_url)
        if provider_overrides:
            install_provider_dependency_overrides(app, provider_overrides)
        with TestClient(app) as client:
            yield client


def _access_body(
    *,
    employee_id: str = "emp-001",
    access_level: str = "READ",
) -> dict[str, object]:
    return {
        "user_id": "user-1",
        "request_text": "Need access to CRM.",
        "employee_id": employee_id,
        "system_id": "crm",
        "access_level": access_level,
        "duration_days": 30,
        "justification": "Need access for routine work.",
        "approval_mode": "HIGH_RISK_ONLY",
    }


def _procurement_body() -> dict[str, object]:
    return {
        "user_id": "user-1",
        "request_text": "Need to buy equipment.",
        "requester_id": "req-001",
        "item_id": "item-laptop",
        "quantity": 1,
        "estimated_total": 900.0,
        "currency": "USD",
        "cost_center": "cc-ops",
        "justification": "Need equipment.",
        "preferred_vendor_id": "vendor-approved-001",
        "approval_mode": "HIGH_RISK_ONLY",
    }


def _maintenance_body(
    *,
    safety_concern: bool = False,
    issue_description: str = "Routine inspection needed.",
    observed_severity: str = "LOW",
) -> dict[str, object]:
    return {
        "user_id": "user-1",
        "request_text": "Maintenance request.",
        "requester_id": "maint-req-001",
        "asset_id": "asset-pump-001",
        "issue_description": issue_description,
        "location": "Plant A",
        "observed_severity": observed_severity,
        "safety_concern": safety_concern,
        "approval_mode": "HIGH_RISK_ONLY",
    }


def _draft_created(body: dict[str, object]) -> bool:
    tool_calls = body["tool_calls"]
    assert isinstance(tool_calls, list)
    return any(
        isinstance(tool_call, dict)
        and tool_call.get("status") == "SUCCEEDED"
        and isinstance(tool_call.get("output_payload"), dict)
        and tool_call["output_payload"].get("status") == "draft"
        for tool_call in tool_calls
    )


def _tool_call(tool_calls: object, tool_name: str) -> dict[str, object]:
    assert isinstance(tool_calls, list)
    for tool_call in tool_calls:
        if isinstance(tool_call, dict) and tool_call.get("tool_name") == tool_name:
            return tool_call
    raise AssertionError(f"Tool call not found: {tool_name}")


def _assert_redacted_maintenance_draft_call(tool_call: dict[str, object]) -> None:
    input_payload = tool_call["input_payload"]
    output_payload = tool_call["output_payload"]
    assert isinstance(input_payload, dict)
    assert isinstance(output_payload, dict)

    assert input_payload["issue_description"] == REDACTED_VALUE
    assert input_payload["asset_id"] == "asset-pump-001"
    assert input_payload["severity"] == "LOW"
    assert output_payload["issue_summary"] == REDACTED_VALUE
    assert output_payload["status"] == "draft"
    assert output_payload["asset_id"] == "asset-pump-001"
