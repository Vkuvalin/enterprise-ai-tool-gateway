from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import UUID

import httpx
import pytest

from enterprise_ai_tool_gateway.api import create_app
from enterprise_ai_tool_gateway.application import (
    AccessWorkflowRuntime,
    MaintenanceLiteWorkflowRuntime,
    ProcurementWorkflowRuntime,
)
from enterprise_ai_tool_gateway.contracts.enums import ApprovalStatus
from enterprise_ai_tool_gateway.contracts.schemas import ApprovalRead
from enterprise_ai_tool_gateway.db import GatewayRepository


_workflow_case = pytest.mark.parametrize(
    ("submit_path", "submit_body", "action_tool_name"),
    [
        pytest.param(
            "/api/v1/access-requests",
            {
                "user_id": "user-1",
                "request_text": "Need admin access to CRM.",
                "employee_id": "emp-001",
                "system_id": "crm",
                "access_level": "ADMIN",
                "duration_days": 30,
                "justification": "Need admin access for a migration.",
                "approval_mode": "HIGH_RISK_ONLY",
            },
            "create_access_request_draft",
            id="access",
        ),
        pytest.param(
            "/api/v1/procurement-requests",
            {
                "user_id": "user-1",
                "request_text": "Need to buy a service.",
                "requester_id": "req-001",
                "item_id": "item-service",
                "quantity": 1,
                "estimated_total": 1500.0,
                "currency": "USD",
                "cost_center": "cc-ops",
                "justification": "Need the service.",
                "preferred_vendor_id": "vendor-approved-001",
                "approval_mode": "HIGH_RISK_ONLY",
            },
            "create_purchase_request_draft",
            id="procurement",
        ),
        pytest.param(
            "/api/v1/maintenance-requests",
            {
                "user_id": "user-1",
                "request_text": "Maintenance request.",
                "requester_id": "maint-req-001",
                "asset_id": "asset-pump-001",
                "issue_description": "Line stopped after failure.",
                "location": "Plant A",
                "safety_concern": False,
                "approval_mode": "HIGH_RISK_ONLY",
            },
            "create_work_order_draft",
            id="maintenance",
        ),
    ],
)


@_workflow_case
@pytest.mark.parametrize(
    "decisions",
    [
        pytest.param(("APPROVED", "REJECTED"), id="approve-vs-reject"),
        pytest.param(("APPROVED", "APPROVED"), id="approve-vs-approve"),
    ],
)
@pytest.mark.asyncio
async def test_concurrent_approval_resolution_has_one_terminal_owner(
    monkeypatch: pytest.MonkeyPatch,
    submit_path: str,
    submit_body: dict[str, object],
    action_tool_name: str,
    decisions: tuple[str, str],
) -> None:
    with TemporaryDirectory(prefix="gateway-approval-race-") as temp_dir:
        database_url = f"sqlite+aiosqlite:///{(Path(temp_dir) / 'api.sqlite3').as_posix()}"
        app = create_app(database_url=database_url)

        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                submitted = await client.post(submit_path, json=submit_body)
                assert submitted.status_code == 200
                submitted_body = submitted.json()
                assert submitted_body["run"]["status"] == "WAITING_FOR_APPROVAL"
                approval_id = submitted_body["approval"]["id"]
                run_id = submitted_body["run"]["id"]

                gate = _AsyncBarrier(parties=2)
                session_ids: set[int] = set()
                original_update = GatewayRepository.update_approval_decision

                async def gated_update(
                    repo: GatewayRepository,
                    target_approval_id: UUID,
                    *,
                    status: ApprovalStatus,
                    decided_by: str,
                    decision_comment: str | None = None,
                ) -> ApprovalRead:
                    session_ids.add(id(repo._session))
                    await asyncio.wait_for(gate.wait(), timeout=5)
                    return await original_update(
                        repo,
                        target_approval_id,
                        status=status,
                        decided_by=decided_by,
                        decision_comment=decision_comment,
                    )

                monkeypatch.setattr(
                    GatewayRepository,
                    "update_approval_decision",
                    gated_update,
                )

                responses = await asyncio.gather(
                    *(
                        client.post(
                            f"/api/v1/approvals/{approval_id}/resolve",
                            json={
                                "run_id": run_id,
                                "status": decision,
                                "decided_by": f"manager-{index}",
                                "decision_comment": f"Concurrent decision {index}.",
                            },
                        )
                        for index, decision in enumerate(decisions, start=1)
                    )
                )

                assert len(session_ids) == 2
                assert sorted(response.status_code for response in responses) == [200, 409]
                winner_index = next(
                    index for index, response in enumerate(responses) if response.status_code == 200
                )
                winning_decision = decisions[winner_index]
                winner = responses[winner_index]
                loser = next(response for response in responses if response.status_code == 409)
                assert loser.json()["detail"]["code"] == "state_conflict"
                assert winner.json()["approval"]["status"] == winning_decision

                run_detail = await client.get(f"/api/v1/runs/{run_id}")
                assert run_detail.status_code == 200
                detail = run_detail.json()

    expected_run_status = "COMPLETED" if winning_decision == "APPROVED" else "REJECTED"
    expected_tool_status = "SUCCEEDED" if winning_decision == "APPROVED" else "REJECTED"
    assert detail["approval"]["status"] == winning_decision
    assert detail["approval"]["decided_by"] == f"manager-{winner_index + 1}"
    assert detail["approval"]["decision_comment"] == (
        f"Concurrent decision {winner_index + 1}."
    )
    assert detail["run"]["status"] == expected_run_status

    action_calls = [
        tool_call
        for tool_call in detail["tool_calls"]
        if tool_call["tool_name"] == action_tool_name
    ]
    assert len(action_calls) == 1
    assert action_calls[0]["status"] == expected_tool_status
    assert _draft_count(action_calls) == (1 if winning_decision == "APPROVED" else 0)

    audit_events = detail["audit_events"]
    _assert_terminal_audit_consistency(
        detail,
        winning_decision=winning_decision,
        decided_by=f"manager-{winner_index + 1}",
    )
    action_execution_events = [
        event
        for event in audit_events
        if event["event_type"] == "TOOL_EXECUTED"
        and event["payload"].get("tool_name") == action_tool_name
    ]
    assert len(action_execution_events) == (1 if winning_decision == "APPROVED" else 0)


@_workflow_case
@pytest.mark.asyncio
async def test_stale_runtime_revalidation_returns_conflict_after_winner_commit(
    monkeypatch: pytest.MonkeyPatch,
    submit_path: str,
    submit_body: dict[str, object],
    action_tool_name: str,
) -> None:
    with TemporaryDirectory(prefix="gateway-approval-revalidation-race-") as temp_dir:
        database_url = f"sqlite+aiosqlite:///{(Path(temp_dir) / 'api.sqlite3').as_posix()}"
        app = create_app(database_url=database_url)

        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                submitted = await client.post(submit_path, json=submit_body)
                assert submitted.status_code == 200
                submitted_body = submitted.json()
                assert submitted_body["run"]["status"] == "WAITING_FOR_APPROVAL"
                approval_id = submitted_body["approval"]["id"]
                run_id = submitted_body["run"]["id"]

                loser_at_runtime = asyncio.Event()
                winner_committed = asyncio.Event()
                session_ids: set[int] = set()
                runtime_type, method_name = _runtime_resolution_target(submit_path)
                original_resolve = getattr(runtime_type, method_name)

                async def gated_resolve(runtime: Any, request: Any) -> Any:
                    session_ids.add(id(runtime._session))
                    if request.decided_by == "manager-loser":
                        loser_at_runtime.set()
                        await asyncio.wait_for(winner_committed.wait(), timeout=5)
                        return await original_resolve(runtime, request)

                    await asyncio.wait_for(loser_at_runtime.wait(), timeout=5)
                    result = await original_resolve(runtime, request)
                    winner_committed.set()
                    return result

                monkeypatch.setattr(runtime_type, method_name, gated_resolve)

                loser_request = asyncio.create_task(
                    client.post(
                        f"/api/v1/approvals/{approval_id}/resolve",
                        json={
                            "run_id": run_id,
                            "status": "REJECTED",
                            "decided_by": "manager-loser",
                            "decision_comment": "Stale losing decision.",
                        },
                    )
                )
                await asyncio.wait_for(loser_at_runtime.wait(), timeout=5)
                winner = await client.post(
                    f"/api/v1/approvals/{approval_id}/resolve",
                    json={
                        "run_id": run_id,
                        "status": "APPROVED",
                        "decided_by": "manager-winner",
                        "decision_comment": "Winning decision.",
                    },
                )
                loser = await asyncio.wait_for(loser_request, timeout=5)

                assert len(session_ids) == 2
                assert winner.status_code == 200
                assert loser.status_code == 409
                assert loser.json()["detail"]["code"] == "state_conflict"

                run_detail = await client.get(f"/api/v1/runs/{run_id}")
                assert run_detail.status_code == 200
                detail = run_detail.json()

    assert detail["approval"]["status"] == "APPROVED"
    assert detail["approval"]["decided_by"] == "manager-winner"
    assert detail["approval"]["decision_comment"] == "Winning decision."
    assert detail["run"]["status"] == "COMPLETED"

    action_calls = [
        tool_call
        for tool_call in detail["tool_calls"]
        if tool_call["tool_name"] == action_tool_name
    ]
    assert len(action_calls) == 1
    assert action_calls[0]["status"] == "SUCCEEDED"
    assert _draft_count(action_calls) == 1
    _assert_terminal_audit_consistency(
        detail,
        winning_decision="APPROVED",
        decided_by="manager-winner",
    )


class _AsyncBarrier:
    def __init__(self, *, parties: int) -> None:
        self._parties = parties
        self._arrived = 0
        self._condition = asyncio.Condition()

    async def wait(self) -> None:
        async with self._condition:
            self._arrived += 1
            if self._arrived == self._parties:
                self._condition.notify_all()
                return
            await self._condition.wait_for(lambda: self._arrived == self._parties)


def _runtime_resolution_target(submit_path: str) -> tuple[type[Any], str]:
    if submit_path == "/api/v1/access-requests":
        return AccessWorkflowRuntime, "resolve_access_approval"
    if submit_path == "/api/v1/procurement-requests":
        return ProcurementWorkflowRuntime, "resolve_procurement_approval"
    if submit_path == "/api/v1/maintenance-requests":
        return MaintenanceLiteWorkflowRuntime, "resolve_maintenance_approval"
    raise AssertionError(f"Unsupported workflow path: {submit_path}")


def _assert_terminal_audit_consistency(
    detail: dict[str, Any],
    *,
    winning_decision: str,
    decided_by: str,
) -> None:
    audit_events = detail["audit_events"]
    approval_decided_events = [
        event for event in audit_events if event["event_type"] == "APPROVAL_DECIDED"
    ]
    assert len(approval_decided_events) == 1
    assert approval_decided_events[0]["payload"]["status"] == winning_decision
    assert approval_decided_events[0]["payload"]["decided_by"] == decided_by

    event_types = [event["event_type"] for event in audit_events]
    expected_terminal_event = (
        "RUN_COMPLETED" if winning_decision == "APPROVED" else "RUN_REJECTED"
    )
    for event_type in ("RUN_COMPLETED", "RUN_REJECTED", "RUN_FAILED"):
        expected_count = 1 if event_type == expected_terminal_event else 0
        assert event_types.count(event_type) == expected_count


def _draft_count(tool_calls: list[dict[str, object]]) -> int:
    return sum(
        1
        for tool_call in tool_calls
        if isinstance(output_payload := tool_call.get("output_payload"), dict)
        and output_payload.get("status") == "draft"
    )
