from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from inspect import signature
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from enterprise_ai_tool_gateway.api import create_app


def test_health_endpoint_returns_ok() -> None:
    with _client() as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_capabilities_endpoint_exposes_stage_8_demo_surface() -> None:
    with _client() as client:
        response = client.get("/api/v1/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["workflows"] == [
        "ACCESS_REQUEST",
        "PROCUREMENT_REQUEST",
        "MAINTENANCE_REQUEST",
    ]
    assert body["approval_modes"] == [
        "AUTO_APPROVE",
        "HIGH_RISK_ONLY",
        "ALWAYS_REQUIRE",
    ]
    assert body["provider_mode"] == "mock"
    assert body["model_selection"] == {
        "enabled": False,
        "active_profile": "mock",
        "available_profiles": ["mock"],
        "note": "Model/provider selection is deferred.",
    }
    assert "GIGACHAT" not in str(body).upper()
    assert "OPENROUTER" not in str(body).upper()


def test_app_factory_does_not_expose_provider_override_hook() -> None:
    assert "provider_overrides" not in signature(create_app).parameters


@contextmanager
def _client() -> Iterator[TestClient]:
    with TemporaryDirectory(prefix="gateway-api-test-") as temp_dir:
        database_url = f"sqlite+aiosqlite:///{(Path(temp_dir) / 'api.sqlite3').as_posix()}"
        with TestClient(create_app(database_url=database_url)) as client:
            yield client
