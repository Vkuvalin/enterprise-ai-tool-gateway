"""FastAPI app factory for the local/demo Stage 8 API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI

from enterprise_ai_tool_gateway.api.http.errors import register_exception_handlers
from enterprise_ai_tool_gateway.api.http.routes import (
    access,
    approvals,
    capabilities,
    health,
    maintenance,
    procurement,
    runs,
)
from enterprise_ai_tool_gateway.db import (
    create_async_engine_from_url,
    create_async_session_factory,
    create_database_schema,
)

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/stage8_api.sqlite3"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    database_url = str(app.state.database_url)
    _ensure_sqlite_parent(database_url)
    engine = create_async_engine_from_url(database_url)
    await create_database_schema(engine)
    app.state.engine = engine
    app.state.session_factory = create_async_session_factory(engine)
    try:
        yield
    finally:
        await engine.dispose()


def create_app(
    *,
    database_url: str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Enterprise AI Tool Gateway API",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.state.database_url = database_url or DEFAULT_DATABASE_URL
    register_exception_handlers(app)

    api_router = APIRouter(prefix="/api/v1")
    api_router.include_router(health.router)
    api_router.include_router(capabilities.router)
    api_router.include_router(access.router)
    api_router.include_router(procurement.router)
    api_router.include_router(maintenance.router)
    api_router.include_router(approvals.router)
    api_router.include_router(runs.router)
    app.include_router(api_router)
    return app


def _ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return
    path_text = database_url.removeprefix(prefix)
    if path_text == ":memory:":
        return
    path = Path(path_text)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)


app = create_app()
