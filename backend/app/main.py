"""FastAPI application factory for the API process.

Run locally:  uv run uvicorn app.main:create_app --factory --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.config import Settings, get_settings
from app.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, service="api", app_env=settings.app_env)

    app = FastAPI(
        title="SME POS API",
        version="0.1.0",
        docs_url="/docs" if settings.app_env in {"local", "demo"} else None,
        redoc_url=None,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)

    logger.info(
        "api configured",
        extra={"timezone": settings.default_timezone, "db_configured": bool(settings.database_url)},
    )
    return app
