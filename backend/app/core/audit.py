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
"""
# No RETURNING: staff may append audit events but only the owner may read them (RLS),
# and RETURNING needs read access to the new row.


async def record_audit(
    conn: AsyncConnection,
    ctx: ActorContext,
    *,
    action: str,
    entity_type: str,
    entity_id: str | UUID | None = None,
    outlet_id: UUID | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Insert one audit event. `ctx.reason` is stored when present."""
    payload = {"correlation_id": ctx.correlation_id, **(data or {})}
    await conn.execute(
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
