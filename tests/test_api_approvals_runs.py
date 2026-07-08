from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi.testclient import TestClient

from enterprise_ai_tool_gateway.api import create_app
from enterprise_ai_tool_gateway.api.http.dependencies import get_gateway_repository
from enterprise_ai_tool_gateway.audit import REDACTED_VALUE


def test_approval_resolve_and_run_read_endpoints() -> None:
    with _client() as client:
        submitted = client.post("/api/v1/access-requests", json=_admin_access_body())
        assert submitted.status_code == 200
        submitted_body = submitted.json()
        approval = submitted_body["approval"]
        run_id = submitted_body["run"]["id"]

        assert submitted_body["run"]["status"] == "WAITING_FOR_APPROVAL"
        assert not _draft_created(submitted_body)

        resolved = client.post(
            f"/api/v1/approvals/{approval['id']}/resolve",
            json={
                "run_id": run_id,
                "status": "APPROVED",
                "decided_by": "manager-001",
                "decision_comment": "Approved for demo.",
            },
        )
        run_detail = client.get(f"/api/v1/runs/{run_id}")
        tool_calls = client.get(f"/api/v1/runs/{run_id}/tool-calls")
        approvals = client.get(f"/api/v1/runs/{run_id}/approvals")
        audit_events = client.get(f"/api/v1/runs/{run_id}/audit-events")

    assert resolved.status_code == 200
    resolved_body = resolved.json()
    assert resolved_body["run"]["status"] == "COMPLETED"
    assert resolved_body["approval"]["id"] == approval["id"]
    assert resolved_body["approval"]["run_id"] == run_id
    assert resolved_body["approval"]["status"] == "APPROVED"
    assert resolved_body["approval"]["decided_by"] == "manager-001"
    assert resolved_body["approval"]["decision_comment"] == "Approved for demo."

    assert run_detail.status_code == 200
    run_detail_body = run_detail.json()
    assert run_detail_body["run"]["status"] == "COMPLETED"
    assert run_detail_body["approval"]["status"] == "APPROVED"
    assert run_detail_body["approval"]["decision_comment"] == "Approved for demo."
    assert run_detail_body["tool_calls"]
    assert run_detail_body["audit_events"]

    assert tool_calls.status_code == 200
    assert isinstance(tool_calls.json(), list)
    assert approvals.status_code == 200
    approvals_body = approvals.json()
    assert approvals_body[0]["status"] == "APPROVED"
    assert approvals_body[0]["decision_comment"] == "Approved for demo."
    assert audit_events.status_code == 200
    assert any(event["event_type"] == "RUN_COMPLETED" for event in audit_events.json())


def test_approval_decision_comment_is_redacted_in_public_readbacks() -> None:
    sensitive_comment = "Authorization: Bearer approvalsecret123456"
    with _client() as client:
        submitted = client.post("/api/v1/access-requests", json=_admin_access_body())
        assert submitted.status_code == 200
        submitted_body = submitted.json()
        approval = submitted_body["approval"]
        run_id = submitted_body["run"]["id"]

        resolved = client.post(
            f"/api/v1/approvals/{approval['id']}/resolve",
            json={
                "run_id": run_id,
                "status": "APPROVED",
                "decided_by": "manager-001",
                "decision_comment": sensitive_comment,
            },
        )
        run_detail = client.get(f"/api/v1/runs/{run_id}")
        approvals = client.get(f"/api/v1/runs/{run_id}/approvals")

    assert resolved.status_code == 200
    resolved_body = resolved.json()
    assert resolved_body["approval"]["id"] == approval["id"]
    assert resolved_body["approval"]["run_id"] == run_id
    assert resolved_body["approval"]["status"] == "APPROVED"
    assert resolved_body["approval"]["decided_by"] == "manager-001"
    assert resolved_body["approval"]["decision_comment"] == REDACTED_VALUE

    assert run_detail.status_code == 200
    run_detail_approval = run_detail.json()["approval"]
    assert run_detail_approval["id"] == approval["id"]
    assert run_detail_approval["run_id"] == run_id
    assert run_detail_approval["status"] == "APPROVED"
    assert run_detail_approval["decision_comment"] == REDACTED_VALUE

    assert approvals.status_code == 200
    approval_readback = approvals.json()[0]
    assert approval_readback["id"] == approval["id"]
    assert approval_readback["run_id"] == run_id
    assert approval_readback["status"] == "APPROVED"
    assert approval_readback["decision_comment"] == REDACTED_VALUE

    assert sensitive_comment not in str(resolved_body)
    assert sensitive_comment not in str(run_detail.json())
    assert sensitive_comment not in str(approvals.json())


def test_cancelled_approval_rejects_run_without_draft_and_second_resolve_conflicts() -> None:
    with _client() as client:
        submitted = client.post("/api/v1/access-requests", json=_admin_access_body())
        assert submitted.status_code == 200
        submitted_body = submitted.json()
        approval = submitted_body["approval"]
        run_id = submitted_body["run"]["id"]

        assert submitted_body["run"]["status"] == "WAITING_FOR_APPROVAL"
        assert approval["status"] == "PENDING"
        assert not _draft_created(submitted_body)

        resolved = client.post(
            f"/api/v1/approvals/{approval['id']}/resolve",
            json=_resolve_body(run_id, "CANCELLED"),
        )
        run_detail = client.get(f"/api/v1/runs/{run_id}")
        second_resolve = client.post(
            f"/api/v1/approvals/{approval['id']}/resolve",
            json=_resolve_body(run_id, "APPROVED"),
        )

    assert resolved.status_code == 200
    assert resolved.json()["run"]["status"] == "REJECTED"
    assert resolved.json()["approval"]["status"] == "CANCELLED"
    assert not _draft_created(resolved.json())

    assert run_detail.status_code == 200
    assert run_detail.json()["run"]["status"] == "REJECTED"
    assert run_detail.json()["approval"]["status"] == "CANCELLED"
    assert not _draft_created(run_detail.json())

    assert second_resolve.status_code == 409


def test_approval_edge_cases_return_expected_http_errors() -> None:
    with _client() as client:
        submitted = client.post("/api/v1/access-requests", json=_admin_access_body())
        body = submitted.json()
        approval_id = body["approval"]["id"]
        run_id = body["run"]["id"]

        unknown_approval = client.post(
            f"/api/v1/approvals/{uuid4()}/resolve",
            json=_resolve_body(run_id, "APPROVED"),
        )
        mismatched_run = client.post(
            f"/api/v1/approvals/{approval_id}/resolve",
            json=_resolve_body(str(uuid4()), "APPROVED"),
        )
        pending_decision = client.post(
            f"/api/v1/approvals/{approval_id}/resolve",
            json=_resolve_body(run_id, "PENDING"),
        )
        resolved = client.post(
            f"/api/v1/approvals/{approval_id}/resolve",
            json=_resolve_body(run_id, "REJECTED"),
        )
        second_resolve = client.post(
            f"/api/v1/approvals/{approval_id}/resolve",
            json=_resolve_body(run_id, "APPROVED"),
        )

    assert unknown_approval.status_code == 404
    assert mismatched_run.status_code == 409
    assert pending_decision.status_code == 422
    assert resolved.status_code == 200
    assert resolved.json()["run"]["status"] == "REJECTED"
    assert second_resolve.status_code == 409


def test_unknown_run_read_endpoints_return_404() -> None:
    unknown_run_id = str(uuid4())
    with _client() as client:
        detail = client.get(f"/api/v1/runs/{unknown_run_id}")
        tool_calls = client.get(f"/api/v1/runs/{unknown_run_id}/tool-calls")
        approvals = client.get(f"/api/v1/runs/{unknown_run_id}/approvals")
        audit_events = client.get(f"/api/v1/runs/{unknown_run_id}/audit-events")

    assert detail.status_code == 404
    assert tool_calls.status_code == 404
    assert approvals.status_code == 404
    assert audit_events.status_code == 404


def test_unexpected_internal_errors_return_safe_generic_response() -> None:
    with TemporaryDirectory(prefix="gateway-api-test-") as temp_dir:
        database_url = f"sqlite+aiosqlite:///{(Path(temp_dir) / 'api.sqlite3').as_posix()}"
        app = create_app(database_url=database_url)

        def _raise_internal_error() -> object:
            raise RuntimeError("secret token should not leak")

        app.dependency_overrides[get_gateway_repository] = _raise_internal_error
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(f"/api/v1/runs/{uuid4()}")

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "internal_error",
            "message": "Unexpected internal API error.",
        }
    }
    assert "secret token" not in str(response.json()).lower()


@contextmanager
def _client() -> Iterator[TestClient]:
    with TemporaryDirectory(prefix="gateway-api-test-") as temp_dir:
        database_url = f"sqlite+aiosqlite:///{(Path(temp_dir) / 'api.sqlite3').as_posix()}"
        with TestClient(create_app(database_url=database_url)) as client:
            yield client


def _admin_access_body() -> dict[str, object]:
    return {
        "user_id": "user-1",
        "request_text": "Need access to CRM.",
        "employee_id": "emp-001",
        "system_id": "crm",
        "access_level": "ADMIN",
        "duration_days": 30,
        "justification": "Need admin access for a migration.",
        "approval_mode": "HIGH_RISK_ONLY",
    }


def _resolve_body(run_id: str, status: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "status": status,
        "decided_by": "manager-001",
        "decision_comment": "Decision for API test.",
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
