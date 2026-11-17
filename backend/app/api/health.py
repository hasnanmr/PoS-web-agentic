"""Liveness and readiness probes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, Response, status

from app import db
from app.config import Settings

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    """Liveness: the process is up and serving requests. Never touches dependencies."""
    settings: Settings = request.app.state.settings
    return {"status": "ok", "env": settings.app_env}


@router.get("/readyz")
async def readyz(request: Request, response: Response) -> dict[str, Any]:
    """Readiness: dependencies needed to serve traffic are reachable."""
    settings: Settings = request.app.state.settings
    checks: dict[str, str] = {}

    if settings.database_url is None:
        checks["database"] = "not_configured"
    else:
        try:
            await db.ping(str(settings.database_url))
            checks["database"] = "ok"
        except Exception as exc:  # any driver/network error means "not ready"
            logger.warning("readiness check failed", extra={"check": "database", "error": str(exc)})
            checks["database"] = "error"

    ready = all(value in {"ok", "not_configured"} for value in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ready else "unavailable", "checks": checks}
