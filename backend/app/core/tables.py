"""Tables and reservation rules per outlet (T-057) — screen O8.

Owner-only checks happen in the API layer. A deleted table is deactivated, not removed:
past orders, bills, and reservations keep pointing at it. Creating a table with the name
of a deactivated one brings that row back with the new capacity and area.
"""

from __future__ import annotations

import secrets
from datetime import time
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row

from app.core import crypto
from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError

HOLD_MINUTES = 15  # FR9.10: fixed, shown read-only on O8

_TABLE_COLUMNS = "id, name, capacity, area, is_bookable"

SETTINGS_FIELDS = (
    "is_enabled",
    "bookable_from",
    "bookable_until",
    "default_duration_minutes",
    "booking_window_days",
    "max_party_size",
    "reminder_offset_minutes",
    "cancellation_cutoff_minutes",
)


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValidationFailedError("table name is required", {"field": "name"})
    return cleaned


def _clean_area(area: str | None) -> str | None:
    if area is None:
        return None
    return " ".join(area.split()) or None


async def list_tables(conn: AsyncConnection, outlet_id: UUID) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        f"select {_TABLE_COLUMNS} from app.tables"  # noqa: S608 - constant column list
        " where outlet_id = %s and is_active order by name",
        (outlet_id,),
    )
    return await cur.fetchall()


async def get_table(conn: AsyncConnection, table_id: UUID) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        f"select {_TABLE_COLUMNS}, outlet_id from app.tables"  # noqa: S608 - constant column list
        " where id = %s and is_active",
        (table_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("table")
    return row


async def create_table(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    *,
    name: str,
    capacity: int,
    area: str | None,
    is_bookable: bool,
) -> dict[str, Any]:
    name = _clean_name(name)
    area = _clean_area(area)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, is_active from app.tables where outlet_id = %s and lower(name) = lower(%s)",
        (outlet_id, name),
    )
    existing = await cur.fetchone()
    if existing and existing["is_active"]:
        raise ConflictError("table_name_taken", "a table with this name already exists")
    if existing:
        await cur.execute(
            "update app.tables set name = %s, capacity = %s, area = %s, is_bookable = %s,"  # noqa: S608 - constant column list
            f" is_active = true where id = %s returning {_TABLE_COLUMNS}",
            (name, capacity, area, is_bookable, existing["id"]),
        )
    else:
        token = secrets.token_hex(16)  # the table QR token (128 bits)
        try:
            async with conn.transaction():
                await cur.execute(
                    "insert into app.tables (tenant_id, outlet_id, name, capacity, area,"  # noqa: S608 - constant column list
                    " is_bookable, qr_token, qr_token_hash) values (%s, %s, %s, %s, %s, %s, %s, %s)"
                    f" returning {_TABLE_COLUMNS}",
                    (
                        ctx.tenant_id,
                        outlet_id,
                        name,
                        capacity,
                        area,
                        is_bookable,
                        # Stored encrypted; looked up by its SHA-256 (app.core.crypto).
                        crypto.encrypt(token, "tables.qr_token"),
                        crypto.sha256_hex(token),
                    ),
                )
        except errors.UniqueViolation:
            raise ConflictError(
                "table_name_taken", "a table with this name already exists"
            ) from None
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("table")
    await record_audit(
        conn,
        ctx,
        action="table.created",
        entity_type="table",
        entity_id=row["id"],
        outlet_id=outlet_id,
        data={"name": name, "capacity": capacity},
    )
    return row


async def update_table(
    conn: AsyncConnection, ctx: ActorContext, table_id: UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    table = await get_table(conn, table_id)
    if "name" in changes:
        changes["name"] = _clean_name(changes["name"])
    if "area" in changes:
        changes["area"] = _clean_area(changes["area"])
    if "capacity" in changes and changes["capacity"] < table["capacity"]:
        # Upcoming bookings were placed for their party size; a smaller table must still fit.
        cur = await conn.execute(
            "select max(party_size) from app.reservations where table_id = %s"
            " and status in ('booked', 'seated') and ends_at > now()",
            (table_id,),
        )
        largest = (await cur.fetchone())[0]  # type: ignore[index]
        if largest is not None and largest > changes["capacity"]:
            raise ConflictError(
                "table_has_reservations",
                "an upcoming reservation on this table is larger than the new capacity",
                {"party_size": largest},
            )
    if not changes:
        return {k: table[k] for k in ("id", "name", "capacity", "area", "is_bookable")}
    sets = ", ".join(f"{k} = %s" for k in changes)
    cur = conn.cursor(row_factory=dict_row)
    try:
        async with conn.transaction():
            await cur.execute(
                f"update app.tables set {sets} where id = %s returning {_TABLE_COLUMNS}",  # noqa: S608 - keys from the API model
                (*changes.values(), table_id),
            )
    except errors.UniqueViolation:
        raise ConflictError("table_name_taken", "a table with this name already exists") from None
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("table")
    await record_audit(
        conn,
        ctx,
        action="table.updated",
        entity_type="table",
        entity_id=table_id,
        outlet_id=table["outlet_id"],
        data={k: str(v) if v is not None else None for k, v in changes.items()},
    )
    return row


async def delete_table(conn: AsyncConnection, ctx: ActorContext, table_id: UUID) -> None:
    """Deactivate. Refused while the table has an open bill or an upcoming booking."""
    table = await get_table(conn, table_id)
    cur = await conn.execute(
        "select exists (select 1 from app.bills where table_id = %s and status = 'open'),"
        " exists (select 1 from app.reservations where table_id = %s"
        "         and status in ('booked', 'seated') and ends_at > now())",
        (table_id, table_id),
    )
    has_bill, has_booking = await cur.fetchone()  # type: ignore[misc]
    if has_bill:
        raise ConflictError("table_in_use", "this table has an open bill")
    if has_booking:
        raise ConflictError("table_in_use", "this table has an upcoming reservation")
    await conn.execute("update app.tables set is_active = false where id = %s", (table_id,))
    await record_audit(
        conn,
        ctx,
        action="table.deleted",
        entity_type="table",
        entity_id=table_id,
        outlet_id=table["outlet_id"],
        data={"name": table["name"]},
    )


async def get_settings(conn: AsyncConnection, outlet_id: UUID) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        f"select {', '.join(SETTINGS_FIELDS)} from app.reservation_settings where outlet_id = %s",  # noqa: S608 - constant field list
        (outlet_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("outlet")
    return {**row, "hold_minutes": HOLD_MINUTES}


async def put_settings(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, values: dict[str, Any]
) -> dict[str, Any]:
    start: time = values["bookable_from"]
    end: time = values["bookable_until"]
    if end <= start:
        raise ValidationFailedError(
            "the last booking time must be after the first", {"field": "bookable_until"}
        )
    sets = ", ".join(f"{k} = %s" for k in SETTINGS_FIELDS)
    cur = await conn.execute(
        f"update app.reservation_settings set {sets} where outlet_id = %s",  # noqa: S608 - constant field list
        (*(values[k] for k in SETTINGS_FIELDS), outlet_id),
    )
    if cur.rowcount == 0:
        raise NotFoundError("outlet")
    await record_audit(
        conn,
        ctx,
        action="reservation_settings.updated",
        entity_type="outlet",
        entity_id=outlet_id,
        outlet_id=outlet_id,
        data={k: str(values[k]) for k in SETTINGS_FIELDS},
    )
    return await get_settings(conn, outlet_id)
