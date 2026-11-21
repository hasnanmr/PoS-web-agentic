"""Idempotency-Key handling for writes that must not run twice (T-029).

Usage inside one transaction:

    fp = idempotency.fingerprint(outlet_id, body)
    cached = await idempotency.lookup(conn, ctx, scope, key, fp)
    if cached is not None:
        return cached          # a replay: same key, same body, same user
    ... do the work ...
    await idempotency.store(conn, ctx, scope, key, fp, response)

Keys are stored as their SHA-256 (`stored_key`), never as sent.
A key is bound to the request that first used it (a hash of the body plus the user).
Reusing it with another body or by another user is `idempotency_key_reused` (409), never a
silent replay of an unrelated response. A concurrent duplicate waits on the primary key
and then fails with a unique violation; the API maps that to `conflict` so the client
retries and gets the stored response. Keys older than 24 hours are removed by `purge`
(run per tenant by the scheduler).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.core.actor import ActorContext
from app.core.errors import ConflictError, ValidationFailedError

RETENTION_HOURS = 24


def check_key(key: str | None) -> str | None:
    if key is None:
        return None
    key = key.strip()
    if not 8 <= len(key) <= 200:
        raise ValidationFailedError("Idempotency-Key must be 8 to 200 characters")
    return key


def stored_key(key: str) -> str:
    """The key as stored: its SHA-256, never the key the client sent (glossary §10)."""
    return hashlib.sha256(key.encode()).hexdigest()


def fingerprint(*parts: Any) -> str:
    """Stable hash of the request: JSON-serializable parts (ids, body) in a fixed order."""
    text = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


async def lookup(
    conn: AsyncConnection, ctx: ActorContext, scope: str, key: str | None, request_hash: str
) -> dict[str, Any] | None:
    if key is None:
        return None
    cur = await conn.execute(
        "select response, request_hash, actor_id from app.idempotency_keys"
        " where tenant_id = %s and scope = %s and key = %s",
        (ctx.tenant_id, scope, stored_key(key)),
    )
    row = await cur.fetchone()
    if row is None:
        return None
    response, stored_hash, stored_actor = row
    if (stored_hash is not None and stored_hash != request_hash) or (
        stored_actor is not None and stored_actor != ctx.actor_id
    ):
        raise ConflictError(
            "idempotency_key_reused",
            "this Idempotency-Key was already used for a different request",
        )
    return response


async def store(
    conn: AsyncConnection,
    ctx: ActorContext,
    scope: str,
    key: str | None,
    request_hash: str,
    response: dict[str, Any],
) -> None:
    if key is None:
        return
    await conn.execute(
        "insert into app.idempotency_keys (tenant_id, scope, key, response, request_hash,"
        " actor_id) values (%s, %s, %s, %s, %s, %s)",
        (ctx.tenant_id, scope, stored_key(key), Jsonb(response), request_hash, ctx.actor_id),
    )


async def purge(conn: AsyncConnection) -> int:
    """Delete this tenant's keys past the retention window; returns how many."""
    cur = await conn.execute(
        "delete from app.idempotency_keys where created_at < now() - make_interval(hours => %s)",
        (RETENTION_HOURS,),
    )
    return cur.rowcount
