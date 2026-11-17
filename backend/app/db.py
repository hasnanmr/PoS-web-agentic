"""Minimal async Postgres helpers (psycopg 3). No ORM; queries are plain SQL.

Schema migrations live in `supabase/migrations/` as plain SQL files.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg

CONNECT_TIMEOUT_SECONDS = 3


@asynccontextmanager
async def connect(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    """Open a short-lived async connection. Pooling comes later with real queries."""
    conn = await psycopg.AsyncConnection.connect(
        database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS, autocommit=True
    )
    try:
        yield conn
    finally:
        await conn.close()


async def ping(database_url: str) -> None:
    """Raise if the database cannot be reached or cannot run `select 1`."""
    async with connect(database_url) as conn:
        await conn.execute("select 1")
