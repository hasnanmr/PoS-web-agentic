"""Automatic table occupancy (FR9.11, PRD v0.22, T-149) — screens S6 / M4, O2, C10.

A table is **occupied** while it has, with activity after its last release:

- an open dine-in order on it (table QR `web_table` or `counter`), from the moment the order
  is created (`pending_payment` included) until it is `completed` or `cancelled`; or
- an open bill, from when it is opened until it is closed or voided (its latest activity is
  the newest of its opening and its orders, so a new order on the bill counts again).

Activity older than 12 hours is ignored, so a table nobody closed does not stay occupied.
Staff or the owner can override with "Kosongkan meja" (`release`): orders and bills whose
latest activity is not after `tables.occupancy_released_at` stop counting.

Occupancy is derived, not a reservation row: it has no end time, stays outside the
`no_overlap` constraint, and never cancels or moves a booking. While a table is occupied it
is skipped for bookings that start on the outlet-local current day (`starts_today`); other
days are unaffected. The same rule feeds the O2 crowd card (`OCCUPIED_SQL`).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError

WINDOW_HOURS = 12  # activity older than this no longer occupies a table

# The earliest activity that still counts for table `t`: inside the window and after the
# last release. Shared by every query below and by the O2 crowd card.
_FLOOR = (
    f"greatest(now() - interval '{WINDOW_HOURS} hours',"
    " coalesce(t.occupancy_released_at, '-infinity'::timestamptz))"
)
_OPEN_ORDER = (
    "o.table_id = t.id and o.type = 'dine_in'"
    " and o.status not in ('completed', 'cancelled')"
    f" and o.created_at > {_FLOOR}"
)
_BILL_ACTIVITY = (
    "greatest(b.opened_at, coalesce((select max(bo.created_at) from app.orders bo"
    " where bo.bill_id = b.id), b.opened_at))"
)
_OPEN_BILL = f"b.table_id = t.id and b.status = 'open' and {_BILL_ACTIVITY} > {_FLOOR}"

# A boolean SQL condition on a table aliased `t` (no parameters).
OCCUPIED_SQL = (
    f"(exists (select 1 from app.orders o where {_OPEN_ORDER})"  # noqa: S608 - constants only
    f" or exists (select 1 from app.bills b where {_OPEN_BILL}))"
)


def starts_today(starts_at: datetime, tz: str, now: datetime) -> bool:
    """True when a booking starting at `starts_at` falls on the outlet-local current day."""
    zone = ZoneInfo(tz)
    return starts_at.astimezone(zone).date() == now.astimezone(zone).date()


async def occupied_table_ids(conn: AsyncConnection, outlet_id: UUID) -> set[UUID]:
    """Active tables of the outlet that are occupied now."""
    cur = await conn.execute(
        f"select t.id from app.tables t where t.outlet_id = %s and t.is_active and {OCCUPIED_SQL}",  # noqa: S608 - constant SQL fragments only
        (outlet_id,),
    )
    return {r[0] for r in await cur.fetchall()}


async def is_occupied(conn: AsyncConnection, table_id: UUID) -> bool:
    cur = await conn.execute(
        f"select {OCCUPIED_SQL} from app.tables t where t.id = %s",  # noqa: S608 - constant SQL fragments only
        (table_id,),
    )
    row = await cur.fetchone()
    return bool(row and row[0])


async def details(conn: AsyncConnection, outlet_id: UUID) -> dict[UUID, dict[str, Any]]:
    """S6 `occupancy` per occupied table: since when, the open bill, and its open orders."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        f"""
        select t.id as table_id,
          (select b.id from app.bills b where {_OPEN_BILL} limit 1) as bill_id,
          (select b.opened_at from app.bills b where {_OPEN_BILL} limit 1) as bill_opened_at,
          (select min(o.created_at) from app.orders o where {_OPEN_ORDER}) as first_order_at,
          (select count(*) from app.orders o where {_OPEN_ORDER})::int as open_orders
        from app.tables t
        where t.outlet_id = %s and t.is_active and {OCCUPIED_SQL}
        """,  # noqa: S608 - constant SQL fragments only
        (outlet_id,),
    )
    out: dict[UUID, dict[str, Any]] = {}
    for r in await cur.fetchall():
        since = min(x for x in (r["bill_opened_at"], r["first_order_at"]) if x is not None)
        out[r["table_id"]] = {
            "since": since,
            "bill_id": r["bill_id"],
            "open_orders": r["open_orders"],
            "allowed_actions": ["release"],
        }
    return out


async def release(
    conn: AsyncConnection, ctx: ActorContext, table_id: UUID, reason: str | None = None
) -> None:
    """S6 "Kosongkan meja": the table is free again until a new order or bill uses it. Orders,
    bills, and payments are not changed. The release is audit-logged with the actor."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, outlet_id, name from app.tables where id = %s and is_active for update",
        (table_id,),
    )
    table = await cur.fetchone()
    if table is None:
        raise NotFoundError("table")
    occupying = (await details(conn, table["outlet_id"])).get(table_id)
    if occupying is None:
        raise ConflictError("not_occupied", "this table is not occupied")
    await cur.execute(
        "select o.id from app.orders o join app.tables t on t.id = o.table_id"  # noqa: S608 - constants only
        f" where t.id = %s and {_OPEN_ORDER} order by o.created_at",
        (table_id,),
    )
    order_ids = [str(r["id"]) for r in await cur.fetchall()]
    await conn.execute(
        "update app.tables set occupancy_released_at = now(), occupancy_released_by = %s"
        " where id = %s",
        (ctx.user_id, table_id),
    )
    cleaned = (reason or "").strip() or None
    await record_audit(
        conn,
        replace(ctx, reason=cleaned),
        action="table.occupancy_released",
        entity_type="table",
        entity_id=table_id,
        outlet_id=table["outlet_id"],
        data={
            "name": table["name"],
            "bill_id": str(occupying["bill_id"]) if occupying["bill_id"] else None,
            "order_ids": order_ids,
        },
    )
