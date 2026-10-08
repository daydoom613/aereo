"""Every error leaves the API as RFC 9457 Problem Details."""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.errors import AppError

PROBLEM_MEDIA_TYPE = "application/problem+json"
# Python 3.12 still uses the pre-RFC 9110 phrases for these two.
_CURRENT_PHRASES = {413: "Content Too Large", 422: "Unprocessable Content"}


def status_title(status: int) -> str:
    return _CURRENT_PHRASES.get(status) or HTTPStatus(status).phrase


def problem_response(
    status: int,
    detail: str,
    instance: str,
    headers: Mapping[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    body = {
        # "about:blank" means the problem has no meaning beyond its HTTP status, in which
        # case the RFC says the title is the status phrase.
        "type": "about:blank",
        "title": status_title(status),
        "status": status,
        "detail": detail,
        "instance": instance,
        **extensions,
    }
    return JSONResponse(body, status_code=status, headers=headers, media_type=PROBLEM_MEDIA_TYPE)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def on_app_error(request: Request, error: AppError) -> JSONResponse:
        return problem_response(error.status_code, error.detail, request.url.path)

    @app.exception_handler(HTTPException)
    async def on_http_error(request: Request, error: HTTPException) -> JSONResponse:
        # Raised by the framework itself: unknown path, wrong method, oversized body.
        return problem_response(
            error.status_code, str(error.detail), request.url.path, headers=error.headers
        )

    @app.exception_handler(RequestValidationError)
    async def on_invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        invalid = [
            {"field": ".".join(str(part) for part in issue["loc"]), "message": issue["msg"]}
            for issue in error.errors()
        ]
        return problem_response(400, "The request is not valid.", request.url.path, errors=invalid)
