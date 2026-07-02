"""Database schema bootstrap helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

import enterprise_ai_tool_gateway.db.models as _models  # noqa: F401
from enterprise_ai_tool_gateway.db.base import Base


async def create_database_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
