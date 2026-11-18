"""Idempotency-Key handling for writes that must not run twice (T-029).

Usage inside one transaction:

    cached = await idempotency.lookup(conn, ctx, scope, key)
    if cached is not None:
        return cached
    ... do the work ...
    await idempotency.store(conn, ctx, scope, key, response)

A concurrent duplicate waits on the primary key and then fails with a unique violation;
the API maps that to `conflict` so the client retries and gets the stored response.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.core.actor import ActorContext
from app.core.errors import ValidationFailedError


def check_key(key: str | None) -> str | None:
    if key is None:
        return None
    key = key.strip()
    if not 8 <= len(key) <= 200:
        raise ValidationFailedError("Idempotency-Key must be 8 to 200 characters")
    return key


async def lookup(
    conn: AsyncConnection, ctx: ActorContext, scope: str, key: str | None
) -> dict[str, Any] | None:
    if key is None:
        return None
    cur = await conn.execute(
        "select response from app.idempotency_keys where tenant_id = %s and scope = %s"
        " and key = %s",
        (ctx.tenant_id, scope, key),
    )
    row = await cur.fetchone()
    return row[0] if row else None


async def store(
    conn: AsyncConnection, ctx: ActorContext, scope: str, key: str | None, response: dict[str, Any]
) -> None:
    if key is None:
        return
    await conn.execute(
        "insert into app.idempotency_keys (tenant_id, scope, key, response)"
        " values (%s, %s, %s, %s)",
        (ctx.tenant_id, scope, key, Jsonb(response)),
    )
