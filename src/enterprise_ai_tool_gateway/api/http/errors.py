"""Safe HTTP error helpers for the API adapter."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


def http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def not_found(resource: str) -> HTTPException:
    return http_error(404, "not_found", f"{resource} was not found.")


def conflict(message: str) -> HTTPException:
    return http_error(409, "state_conflict", message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def _unexpected_error_handler(
        _request: Request,
        _exc: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "internal_error",
                    "message": "Unexpected internal API error.",
                }
            },
        )
