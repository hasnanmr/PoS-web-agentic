"""Outlets, opening hours, and cash drawers (T-011, T-039 drawer config) — screen O3.

All functions run inside `app.db.transaction` with the caller's context, so RLS
limits them to the caller's tenant. Owner-only checks happen in the API layer
(and again in the RLS `with check` for outlet writes).
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row

from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError

TIMEZONES = ("Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura")

# Fields the owner may change from O3 "Simpan perubahan" (one PATCH).
EDITABLE_FIELDS = (
    "name",
    "address",
    "timezone",
    "whatsapp_phone",
    "pb1_enabled",
    "pb1_rate_bps",
    "payment_mode",
    "delivery_fee",
    "unpaid_timeout_minutes",
    "attendance_grace_minutes",
)

_OUTLET_COLUMNS = """
id, name, address, timezone, whatsapp_phone, whatsapp_status, catalog_synced_at,
order_prefix, payment_mode::text as payment_mode, pb1_enabled, pb1_rate_bps, delivery_fee,
unpaid_timeout_minutes, attendance_grace_minutes, is_active
"""


@dataclass(frozen=True, slots=True)
class OpeningHours:
    weekday: int  # ISO 1 = Monday … 7 = Sunday
    opens_at: time
    closes_at: time


async def list_outlets(conn: AsyncConnection) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, name, timezone, order_prefix, is_active from app.outlets order by created_at"
    )
    return await cur.fetchall()


async def get_outlet(conn: AsyncConnection, outlet_id: UUID) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(f"select {_OUTLET_COLUMNS} from app.outlets where id = %s", (outlet_id,))  # noqa: S608 - constant column list
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("outlet")
    await cur.execute(
        "select weekday, opens_at, closes_at from app.outlet_opening_hours"
        " where outlet_id = %s order by weekday",
        (outlet_id,),
    )
    row["opening_hours"] = await cur.fetchall()
    return row


async def _next_order_prefix(conn: AsyncConnection) -> str:
    cur = await conn.execute("select order_prefix from app.outlets")
    used = {r[0] for r in await cur.fetchall()}
    for letter in string.ascii_uppercase:
        if letter not in used:
            return letter
    for a in string.ascii_uppercase:
        for b in string.ascii_uppercase:
            if a + b not in used:
                return a + b
    raise ConflictError("order_prefix_exhausted", "no order prefix left for this business")


def _integrity_to_domain(exc: errors.IntegrityError) -> Exception:
    constraint = getattr(exc.diag, "constraint_name", None) or ""
    if "whatsapp_phone" in constraint:
        return ConflictError("whatsapp_phone_taken", "WhatsApp number is used by another outlet")
    if "pb1_rate_required" in constraint:
        return ValidationFailedError(
            "PB1 rate is required when PB1 is on", {"field": "pb1_rate_bps"}
        )
    if isinstance(exc, errors.CheckViolation):
        return ValidationFailedError("invalid outlet value", {"constraint": constraint})
    return ConflictError(
        "conflict", "outlet conflicts with existing data", {"constraint": constraint}
    )


async def create_outlet(
    conn: AsyncConnection,
    ctx: ActorContext,
    *,
    name: str,
    timezone: str = "Asia/Jakarta",
    address: str | None = None,
    whatsapp_phone: str | None = None,
) -> UUID:
    """New outlet; the DB trigger adds the default drawer and reservation settings."""
    prefix = await _next_order_prefix(conn)
    # The id is generated here: INSERT ... RETURNING would need the new row to pass the
    # SELECT policy (can_access_outlet), which cannot see it inside the same statement.
    outlet_id = uuid4()
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into app.outlets (id, tenant_id, name, timezone, address, whatsapp_phone,"
                " order_prefix) values (%s, %s, %s, %s, %s, %s, %s)",
                (outlet_id, ctx.tenant_id, name.strip(), timezone, address, whatsapp_phone, prefix),
            )
    except errors.IntegrityError as exc:
        raise _integrity_to_domain(exc) from None
    # Same opening hours as the wireframe default (Sen-Min 08:00-22:00) until edited.
    await conn.execute(
        "insert into app.outlet_opening_hours (outlet_id, tenant_id, weekday, opens_at, closes_at)"
        " select %s, %s, d, '08:00', '22:00' from generate_series(1, 7) d",
        (outlet_id, ctx.tenant_id),
    )
    # New outlets sell the same menu at the oldest active outlet's prices (and availability)
    # until the owner edits them.
    await conn.execute(
        """
        insert into app.outlet_prices
          (tenant_id, outlet_id, product_id, addon_option_id, price, is_available)
        select tenant_id, %s, product_id, addon_option_id, price, is_available
        from app.outlet_prices
        where outlet_id = (select id from app.outlets where id <> %s and is_active
                           order by created_at, id limit 1)
        """,
        (outlet_id, outlet_id),
    )
    await record_audit(
        conn,
        ctx,
        action="outlet.created",
        entity_type="outlet",
        entity_id=outlet_id,
        outlet_id=outlet_id,
        data={"name": name.strip()},
    )
    return outlet_id


async def update_outlet(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, changes: dict[str, Any]
) -> None:
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValidationFailedError("fields cannot be changed", {"fields": sorted(unknown)})
    if not changes:
        return
    before = await get_outlet(conn, outlet_id)
    if any(f in changes and changes[f] != before.get(f) for f in ("pb1_enabled", "pb1_rate_bps")):
        # A bill's PB1 is computed when it closes; changing the rate while a bill is open
        # would make the bill disagree with the orders already taken on it.
        cur = await conn.execute(
            "select exists (select 1 from app.bills where outlet_id = %s and status = 'open')",
            (outlet_id,),
        )
        if (await cur.fetchone())[0]:  # type: ignore[index]
            raise ConflictError(
                "bills_open", "close or void the open bills before changing PB1", {"field": "pb1"}
            )
    assignments = ", ".join(f"{field} = %s" for field in changes)
    try:
        async with conn.transaction():
            cur = await conn.execute(
                f"update app.outlets set {assignments} where id = %s",  # noqa: S608 - whitelisted names
                (*changes.values(), outlet_id),
            )
    except errors.IntegrityError as exc:
        raise _integrity_to_domain(exc) from None
    if cur.rowcount == 0:
        raise NotFoundError("outlet")
    diff = {
        k: {"from": _jsonable(before.get(k)), "to": _jsonable(v)}
        for k, v in changes.items()
        if before.get(k) != v
    }
    if diff:
        await record_audit(
            conn,
            ctx,
            action="outlet.updated",
            entity_type="outlet",
            entity_id=outlet_id,
            outlet_id=outlet_id,
            data={"changes": diff},
        )


async def set_opening_hours(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, hours: list[OpeningHours]
) -> None:
    weekdays = [h.weekday for h in hours]
    if len(set(weekdays)) != len(weekdays):
        raise ValidationFailedError("each weekday may appear once", {"field": "weekday"})
    await get_outlet(conn, outlet_id)  # 404 when not visible
    await conn.execute("delete from app.outlet_opening_hours where outlet_id = %s", (outlet_id,))
    for h in hours:
        await conn.execute(
            "insert into app.outlet_opening_hours (outlet_id, tenant_id, weekday, opens_at,"
            " closes_at) values (%s, %s, %s, %s, %s)",
            (outlet_id, ctx.tenant_id, h.weekday, h.opens_at, h.closes_at),
        )
    await record_audit(
        conn,
        ctx,
        action="outlet.opening_hours_set",
        entity_type="outlet",
        entity_id=outlet_id,
        outlet_id=outlet_id,
        data={"hours": [[h.weekday, str(h.opens_at), str(h.closes_at)] for h in hours]},
    )


# Cash drawers -------------------------------------------------------------------------


async def list_drawers(conn: AsyncConnection, outlet_id: UUID) -> list[dict[str, Any]]:
    await get_outlet(conn, outlet_id)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select d.id, d.name, d.created_at,
               exists (select 1 from app.cashier_shifts s
                       where s.drawer_id = d.id and s.closed_at is null) as has_open_shift
        from app.cash_drawers d
        where d.outlet_id = %s and d.is_active
        order by d.created_at, d.name
        """,
        (outlet_id,),
    )
    return await cur.fetchall()


async def create_drawer(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, name: str
) -> UUID:
    await get_outlet(conn, outlet_id)
    try:
        async with conn.transaction():
            cur = await conn.execute(
                "insert into app.cash_drawers (tenant_id, outlet_id, name) values (%s, %s, %s)"
                " returning id",
                (ctx.tenant_id, outlet_id, name.strip()),
            )
            row = await cur.fetchone()
    except errors.UniqueViolation:
        raise ConflictError("drawer_name_taken", "a drawer with this name exists") from None
    assert row is not None  # noqa: S101
    await record_audit(
        conn,
        ctx,
        action="drawer.created",
        entity_type="cash_drawer",
        entity_id=row[0],
        outlet_id=outlet_id,
        data={"name": name.strip()},
    )
    return row[0]


async def _drawer_outlet(conn: AsyncConnection, drawer_id: UUID) -> UUID:
    cur = await conn.execute(
        "select outlet_id from app.cash_drawers where id = %s and is_active", (drawer_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("drawer")
    return row[0]


async def rename_drawer(
    conn: AsyncConnection, ctx: ActorContext, drawer_id: UUID, name: str
) -> None:
    outlet_id = await _drawer_outlet(conn, drawer_id)
    try:
        async with conn.transaction():
            await conn.execute(
                "update app.cash_drawers set name = %s where id = %s", (name.strip(), drawer_id)
            )
    except errors.UniqueViolation:
        raise ConflictError("drawer_name_taken", "a drawer with this name exists") from None
    await record_audit(
        conn,
        ctx,
        action="drawer.renamed",
        entity_type="cash_drawer",
        entity_id=drawer_id,
        outlet_id=outlet_id,
        data={"name": name.strip()},
    )


async def delete_drawer(conn: AsyncConnection, ctx: ActorContext, drawer_id: UUID) -> None:
    """Deactivate a drawer (shift history keeps pointing at it). Refused while a shift is open
    or when it is the outlet's last drawer."""
    outlet_id = await _drawer_outlet(conn, drawer_id)
    cur = await conn.execute(
        "select exists (select 1 from app.cashier_shifts where drawer_id = %s"
        " and closed_at is null)",
        (drawer_id,),
    )
    if (await cur.fetchone())[0]:  # type: ignore[index]
        raise ConflictError("shift_open", "close the open shift before deleting this drawer")
    cur = await conn.execute(
        "select count(*) from app.cash_drawers where outlet_id = %s and is_active", (outlet_id,)
    )
    if (await cur.fetchone())[0] <= 1:  # type: ignore[index]
        raise ConflictError("last_drawer", "an outlet needs at least one drawer")
    await conn.execute(
        "update app.cash_drawers set is_active = false, name = left(name, 40) || ' (dihapus '"
        " || to_char(now(), 'YYMMDDHH24MISS') || ')' where id = %s",
        (drawer_id,),
    )
    await record_audit(
        conn,
        ctx,
        action="drawer.deleted",
        entity_type="cash_drawer",
        entity_id=drawer_id,
        outlet_id=outlet_id,
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


async def require_outlet(conn: AsyncConnection, outlet_id: UUID) -> dict[str, Any]:
    """404 unless the caller may access this outlet (RLS: owner, assigned staff, workers)."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, name, timezone, order_prefix, payment_mode::text as payment_mode,"
        " pb1_enabled, pb1_rate_bps, delivery_fee from app.outlets where id = %s and is_active",
        (outlet_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("outlet")
    return row
