"""Common API schema primitives."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base settings for API-facing DTOs."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiModel):
    status: str


class ErrorResponse(ApiModel):
    code: str
    message: str
