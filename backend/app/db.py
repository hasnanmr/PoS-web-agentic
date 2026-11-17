"""Postgres access (psycopg 3, plain SQL, no ORM) — T-113 session pattern.

- The API and workers connect as role `app_backend` through the Supabase
  transaction pooler (port 6543). Transaction mode does not support prepared
  statements, so the pool disables them (`prepare_threshold=None`).
- Every unit of work runs in ONE transaction that first sets transaction-local
  settings from the `ActorContext` (`set_config(..., true)`), so RLS sees the
  caller's tenant, user, and actor, and nothing leaks to the next request on a
  pooled connection (Appendix B.4).
- Schema migrations live in `supabase/migrations/` and run with a direct/session
  connection, not through this module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from psycopg_pool import AsyncConnectionPool

from app.core.actor import ActorContext

CONNECT_TIMEOUT_SECONDS = 3

_SET_CONTEXT = """
select set_config('app.tenant_id', %s, true),
       set_config('app.user_id', %s, true),
       set_config('app.actor', %s, true),
       set_config('app.device_outlet_id', %s, true),
       set_config('app.correlation_id', %s, true)
"""


def _configure(conn: psycopg.AsyncConnection) -> None:
    conn.prepare_threshold = None  # transaction pooler: no server-side prepared statements


async def _configure_async(conn: psycopg.AsyncConnection) -> None:
    _configure(conn)


def create_pool(database_url: str, *, min_size: int = 1, max_size: int = 5) -> AsyncConnectionPool:
    """Create (but do not open) the shared pool. Open it in the app lifespan."""
    return AsyncConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        open=False,
        configure=_configure_async,
        kwargs={"connect_timeout": CONNECT_TIMEOUT_SECONDS, "autocommit": False},
    )


async def set_context(conn: psycopg.AsyncConnection, ctx: ActorContext) -> None:
    """Set the transaction-local request context. Call inside an open transaction."""
    s = ctx.session_settings()
    await conn.execute(
        _SET_CONTEXT,
        (
            s["app.tenant_id"],
            s["app.user_id"],
            s["app.actor"],
            s["app.device_outlet_id"],
            s["app.correlation_id"],
        ),
    )


@asynccontextmanager
async def transaction(
    pool: AsyncConnectionPool, ctx: ActorContext
) -> AsyncIterator[psycopg.AsyncConnection]:
    """One unit of work: borrow a connection, open a transaction, set the context.

    Commits on success, rolls back on any exception.
    """
    async with pool.connection() as conn, conn.transaction():
        await set_context(conn, ctx)
        yield conn


@asynccontextmanager
async def connect(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    """Open a short-lived autocommit connection (health checks, CLI)."""
    conn = await psycopg.AsyncConnection.connect(
        database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS, autocommit=True
    )
    _configure(conn)
    try:
        yield conn
    finally:
        await conn.close()


async def ping(database_url: str) -> None:
    """Raise if the database cannot be reached or cannot run `select 1`."""
    async with connect(database_url) as conn:
        await conn.execute("select 1")
