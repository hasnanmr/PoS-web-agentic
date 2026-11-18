"""Append-only audit trail for administrative actions (T-008).

Domain history (order, reservation, attendance events) has its own tables; this
writer covers settings changes, staff management, dead-letter replay/discard, and
similar actions in `app.audit_events`. It must run inside `app.db.transaction`
so RLS sees the same tenant as the change being audited.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.core.actor import ActorContext

_INSERT = """
insert into app.audit_events
  (tenant_id, outlet_id, actor_type, actor_id, action, entity_type, entity_id, reason, data)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
returning id
"""


async def record_audit(
    conn: AsyncConnection,
    ctx: ActorContext,
    *,
    action: str,
    entity_type: str,
    entity_id: str | UUID | None = None,
    outlet_id: UUID | None = None,
    data: dict[str, Any] | None = None,
) -> int:
    """Insert one audit event and return its id. `ctx.reason` is stored when present."""
    payload = {"correlation_id": ctx.correlation_id, **(data or {})}
    cur = await conn.execute(
        _INSERT,
        (
            ctx.tenant_id,
            outlet_id,
            ctx.actor_type.value,
            ctx.actor_id,
            action,
            entity_type,
            str(entity_id) if entity_id is not None else None,
            ctx.reason,
            Jsonb(payload),
        ),
    )
    row = await cur.fetchone()
    assert row is not None  # noqa: S101 - insert ... returning always yields a row
    return int(row[0])
