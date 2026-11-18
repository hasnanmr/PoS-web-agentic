"""FastAPI application factory for the API process.

Run locally:  uv run uvicorn app.main:create_app --factory --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.api import health
from app.api.errors import install_error_handlers
from app.api.v1 import me
from app.api.v1.ops import bills as ops_bills
from app.api.v1.ops import orders as ops_orders
from app.api.v1.ops import stock as ops_stock
from app.api.v1.owner import catalog, onboarding, outlets, staff
from app.auth.principal import PgUserDirectory, UserDirectory
from app.auth.supabase_admin import AuthAdmin, SupabaseAdmin
from app.auth.tokens import JwksCache, TokenVerifier, http_jwks_fetcher
from app.config import Settings, get_settings
from app.logging import configure_logging

logger = logging.getLogger(__name__)


def build_token_verifier(settings: Settings) -> TokenVerifier | None:
    if settings.supabase_jwks_url is None or settings.supabase_jwt_issuer is None:
        return None
    jwks = JwksCache(
        http_jwks_fetcher(str(settings.supabase_jwks_url)),
        ttl_seconds=settings.jwks_cache_seconds,
    )
    return TokenVerifier(
        jwks,
        issuer=settings.supabase_jwt_issuer,
        audience=settings.supabase_jwt_audience,
        algorithms=settings.jwt_algorithms,
    )


def build_auth_admin(settings: Settings) -> AuthAdmin | None:
    if settings.supabase_url is None or settings.supabase_service_role_key is None:
        return None
    return SupabaseAdmin(
        str(settings.supabase_url), settings.supabase_service_role_key.get_secret_value()
    )


def create_app(
    settings: Settings | None = None,
    *,
    token_verifier: TokenVerifier | None = None,
    user_directory: UserDirectory | None = None,
    auth_admin: AuthAdmin | None = None,
) -> FastAPI:
    """Build the app. Tests may inject a verifier and a user directory."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, service="api", app_env=settings.app_env)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = None
        if settings.database_url is not None:
            pool = db.create_pool(
                str(settings.database_url),
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_max_size,
            )
            await pool.open(wait=False)
            app.state.db_pool = pool
            if app.state.user_directory is None:
                app.state.user_directory = PgUserDirectory(pool)
        try:
            yield
        finally:
            if pool is not None:
                await pool.close()

    app = FastAPI(
        title="SME POS API",
        version="0.1.0",
        docs_url="/docs" if settings.app_env in {"local", "demo"} else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db_pool = None
    app.state.token_verifier = token_verifier or build_token_verifier(settings)
    app.state.user_directory = user_directory
    app.state.auth_admin = auth_admin or build_auth_admin(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(onboarding.router)
    app.include_router(outlets.router)
    app.include_router(staff.router)
    app.include_router(catalog.router)
    app.include_router(ops_stock.router)
    app.include_router(ops_orders.router)
    app.include_router(ops_bills.router)

    logger.info(
        "api configured",
        extra={
            "timezone": settings.default_timezone,
            "db_configured": bool(settings.database_url),
            "auth_configured": app.state.token_verifier is not None,
        },
    )
    return app
