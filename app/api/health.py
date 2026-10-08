"""Liveness check for load balancers and container orchestrators."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.files import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", summary="Check that the service is running")
def health() -> HealthResponse:
    return HealthResponse(status="ok")
