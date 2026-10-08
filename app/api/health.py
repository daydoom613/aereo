"""Liveness check for load balancers and container orchestrators."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Check that the service is running")
def health() -> dict[str, str]:
    return {"status": "ok"}
