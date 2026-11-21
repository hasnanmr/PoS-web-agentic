"""Reservations and table occupancy (T-058, T-059, T-062, T-063, T-064) — screens S6 / M4.

One service for every channel: staff bookings (phone, in person) and walk-ins now, the
WhatsApp flow (T-060) and the agent (T-088) later.

- Availability and times use the outlet's time zone (glossary §3, AC9.9).
- A booking gets the smallest free bookable table that fits the party (FR9.2).
- Overlaps are refused by the database exclusion constraint `no_overlap` on active
  (`booked`, `seated`) rows, so concurrent requests cannot double-book (FR9.3, US-024).
  Auto-assignment tries the candidates in order and moves on when the constraint fires.
- A walk-in is a `seated` reservation with source `walk_in`; it blocks overlapping
  bookings like any other active row (FR9.7).
- Hold: a booking not seated 15 minutes after its start becomes `no_show` and frees the
  table (FR9.10). A `no_show_release` job is written for the scheduler (T-104); until the
  poller runs, `release_no_shows` also runs before every read or write of an outlet's
  reservations, so an expired hold never blocks a new booking and the board is current.
- A table in use (open dine-in order or open bill, `app.core.occupancy`, FR9.11) is skipped
  for bookings that start today (outlet-local); bookings on other days are unaffected and
  existing bookings are never moved, only flagged on the board (`table_occupied`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core import crypto, occupancy
from app.core.actor import ActorContext
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.localtime import local_day_bounds
from app.core.proofs import mask_phone
from app.core.tables import HOLD_MINUTES, get_settings

HOLD = timedelta(minutes=HOLD_MINUTES)
SLOT_STEP = timedelta(minutes=30)  # granularity of the times offered to customers (T-060)
PAST_GRACE = timedelta(minutes=5)  # a booking a few minutes "ago" is a clock skew, not an error

ACTIVE = ("booked", "seated")


# Time rules -------------------------------------------------------------------------------
async def _outlet_tz(conn: AsyncConnection, outlet_id: UUID) -> str:
    cur = await conn.execute("select timezone from app.outlets where id = %s", (outlet_id,))
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("outlet")
    return row[0]


def check_booking_time(
    starts_at: datetime, settings: dict[str, Any], tz: str, now: datetime
) -> None:
    """Outlet rules for a new or rescheduled booking: not in the past, inside the booking
    window, and starting within the bookable hours (all in outlet-local time)."""
    if starts_at < now - PAST_GRACE:
        raise ValidationFailedError("the booking time has passed", {"field": "starts_at"})
    local = starts_at.astimezone(ZoneInfo(tz))
    today = now.astimezone(ZoneInfo(tz)).date()
    if (local.date() - today).days > settings["booking_window_days"]:
        raise ValidationFailedError(
            "the date is beyond the booking window",
            {"field": "starts_at", "booking_window_days": settings["booking_window_days"]},
        )
    start: time = settings["bookable_from"]
    end: time = settings["bookable_until"]
    if not start <= local.time().replace(tzinfo=None) <= end:
        raise ValidationFailedError(
            "outside the bookable hours",
            {"field": "starts_at", "bookable_from": str(start)[:5], "bookable_until": str(end)[:5]},
        )


def check_party(party_size: int, settings: dict[str, Any]) -> None:
    if party_size > settings["max_party_size"]:
        raise ValidationFailedError(
            "the party is larger than the outlet allows",
            {"field": "party_size", "max_party_size": settings["max_party_size"]},
        )


def hold_until(row: dict[str, Any]) -> datetime | None:
    if row["status"] == "booked" and row["source"] != "walk_in":
        return row["starts_at"] + HOLD
    return None


def allowed_actions(row: dict[str, Any], now: datetime) -> list[str]:
    """Buttons S6 / M4 may show for this reservation (the UI renders only these)."""
    status, source = row["status"], row["source"]
    if status == "booked":
        actions = ["move", "cancel"]
        if now < row["starts_at"] + HOLD:
            actions.insert(0, "seat")
        if now >= row["starts_at"]:
            actions.append("no_show")
        return actions
    if status == "seated":
        actions = ["complete", "move"]
        if source == "walk_in":
            actions.append("cancel")  # marked occupied by mistake
        return actions
    return []


# Availability (T-058) ------------------------------------------------------------------
async def _candidate_tables(
    conn: AsyncConnection,
    outlet_id: UUID,
    party_size: int,
    starts_at: datetime,
    ends_at: datetime,
    *,
    skip: set[UUID] | frozenset[UUID] = frozenset(),
) -> list[UUID]:
    """Free bookable tables that fit the party, smallest first (then by name); `skip` are
    tables occupied now (FR9.11), passed for a start today."""
    cur = await conn.execute(
        """
        select t.id from app.tables t
        where t.outlet_id = %s and t.is_active and t.is_bookable and t.capacity >= %s
          and not exists (
            select 1 from app.reservations r
            where r.table_id = t.id and r.status in ('booked', 'seated')
              and tstzrange(r.starts_at, r.ends_at, '[)') && tstzrange(%s, %s, '[)'))
        order by t.capacity, t.name
        """,
        (outlet_id, party_size, starts_at, ends_at),
    )
    return [r[0] for r in await cur.fetchall() if r[0] not in skip]


async def _occupied_if_today(
    conn: AsyncConnection, outlet_id: UUID, starts_at: datetime, tz: str, now: datetime
) -> set[UUID]:
    """Tables to skip for a booking starting at `starts_at`: the occupied ones when it starts
    today (outlet-local), none for another day (FR9.11)."""
    if not occupancy.starts_today(starts_at, tz, now):
        return set()
    return await occupancy.occupied_table_ids(conn, outlet_id)


async def available_start_times(
    conn: AsyncConnection, outlet_id: UUID, day: date, party_size: int, *, now: datetime
) -> list[datetime]:
    """Start times on an outlet-local `day` with a free table for the party, every 30
    minutes within the bookable hours, inside the booking window and not in the past.
    Used by the WhatsApp reservation flow (T-060) to offer only valid times (US-023)."""
    settings = await get_settings(conn, outlet_id)
    check_party(party_size, settings)
    tz = await _outlet_tz(conn, outlet_id)
    zone = ZoneInfo(tz)
    duration = timedelta(minutes=settings["default_duration_minutes"])
    slot = datetime.combine(day, settings["bookable_from"], tzinfo=zone)
    last = datetime.combine(day, settings["bookable_until"], tzinfo=zone)
    await release_no_shows(conn, outlet_id)
    occupied = await _occupied_if_today(conn, outlet_id, slot, tz, now)
    times: list[datetime] = []
    while slot <= last:
        try:
            check_booking_time(slot, settings, tz, now)
        except ValidationFailedError:
            slot += SLOT_STEP
            continue
        if await _candidate_tables(
            conn, outlet_id, party_size, slot, slot + duration, skip=occupied
        ):
            times.append(slot.astimezone(UTC))
        slot += SLOT_STEP
    return times


# No-show release (T-064) ----------------------------------------------------------------
async def release_no_shows(conn: AsyncConnection, outlet_id: UUID) -> int:
    """Mark bookings still `booked` 15 minutes after their start as `no_show` (actor
    system) and close their scheduler jobs. Idempotent; safe to run on every request."""
    cur = await conn.execute(
        """
        update app.reservations set status = 'no_show'
        where outlet_id = %s and status = 'booked' and source <> 'walk_in'
          and starts_at + %s <= now()
        returning id, tenant_id, starts_at
        """,
        (outlet_id, HOLD),
    )
    released = await cur.fetchall()
    for res_id, tenant_id, starts_at in released:
        await conn.execute(
            "insert into app.reservation_events (tenant_id, outlet_id, reservation_id, event,"
            " from_status, to_status, data, actor_type) values"
            " (%s, %s, %s, 'status_changed', 'booked', 'no_show', %s, 'system')",
            (
                tenant_id,
                outlet_id,
                res_id,
                Jsonb({"reason": "hold_expired", "hold_until": (starts_at + HOLD).isoformat()}),
            ),
        )
        await _finish_job(conn, res_id, "done")
    return len(released)


async def _schedule_no_show(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, res_id: UUID, starts_at: datetime
) -> None:
    await conn.execute(
        "insert into app.scheduled_jobs (job_key, type, tenant_id, outlet_id, run_at, payload)"
        " values (%s, 'no_show_release', %s, %s, %s, %s) on conflict (job_key) do nothing",
        (
            f"no_show_release:{res_id}",
            ctx.tenant_id,
            outlet_id,
            starts_at + HOLD,
            Jsonb({"reservation_id": str(res_id)}),
        ),
    )


async def _finish_job(conn: AsyncConnection, res_id: UUID, status: str) -> None:
    await conn.execute(
        "update app.scheduled_jobs set status = %s, finished_at = now()"
        " where job_key = %s and status in ('pending', 'enqueued')",
        (status, f"no_show_release:{res_id}"),
    )


# Writes ----------------------------------------------------------------------------------
def phone_index(phone: str) -> str:
    """Blind index of the guest phone, digits only (same index as `customers.phone_index`)."""
    return crypto.blind_index("".join(c for c in phone if c.isdigit() or c == "+"), "phone")


def booking_code_index(code: str) -> str:
    return crypto.blind_index(code.strip().upper(), "booking_code")


async def _event(
    conn: AsyncConnection,
    ctx: ActorContext,
    row: dict[str, Any],
    event: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    await conn.execute(
        "insert into app.reservation_events (tenant_id, outlet_id, reservation_id, event,"
        " from_status, to_status, data, actor_type, actor_id)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            ctx.tenant_id,
            row["outlet_id"],
            row["id"],
            event,
            from_status,
            to_status,
            Jsonb({"correlation_id": ctx.correlation_id, **(data or {})}),
            ctx.actor_type.value,
            ctx.actor_id,
        ),
    )


async def _require_table(conn: AsyncConnection, outlet_id: UUID, table_id: UUID) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, name, capacity, is_bookable from app.tables"
        " where id = %s and outlet_id = %s and is_active",
        (table_id, outlet_id),
    )
    table = await cur.fetchone()
    if table is None:
        raise ValidationFailedError("unknown table", {"field": "table_id"})
    return table


def _check_fits(table: dict[str, Any], party_size: int) -> None:
    if table["capacity"] < party_size:
        raise ValidationFailedError(
            "the party does not fit this table",
            {"field": "table_id", "capacity": table["capacity"]},
        )


async def _insert(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    table_id: UUID,
    values: dict[str, Any],
) -> UUID | None:
    """Insert one reservation; None when the table is taken for that time (exclusion)."""
    res_id = uuid4()
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into app.reservations (id, tenant_id, outlet_id, table_id, contact_id,"
                " guest_name, guest_phone, party_size, starts_at, ends_at, source, status,"
                " created_by_actor, created_by_id, customer_id, booking_code, access_key_hash,"
                " guest_phone_index, booking_code_index)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                " %s, %s)",
                (
                    res_id,
                    ctx.tenant_id,
                    outlet_id,
                    table_id,
                    values.get("contact_id"),
                    # Personal data is stored encrypted (app.core.crypto, glossary §10).
                    crypto.encrypt(values.get("guest_name"), "reservations.guest_name"),
                    crypto.encrypt(values.get("guest_phone"), "reservations.guest_phone"),
                    values["party_size"],
                    values["starts_at"],
                    values["ends_at"],
                    values["source"],
                    values["status"],
                    ctx.actor_type.value,
                    ctx.actor_id,
                    values.get("customer_id"),
                    crypto.encrypt(values.get("booking_code"), "reservations.booking_code"),
                    values.get("access_key_hash"),
                    phone_index(values["guest_phone"]) if values.get("guest_phone") else None,
                    booking_code_index(values["booking_code"])
                    if values.get("booking_code")
                    else None,
                ),
            )
    except errors.ExclusionViolation:
        return None
    return res_id


async def create_booking(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    *,
    party_size: int,
    starts_at: datetime,
    source: str,
    guest_name: str | None = None,
    guest_phone: str | None = None,
    contact_id: UUID | None = None,
    table_id: UUID | None = None,
    now: datetime | None = None,
    web: dict[str, Any] | None = None,
) -> UUID:
    """S6 "+ Booking telepon / langsung" and the web chat (C10, source `web_chat`; `web`
    carries `customer_id`, `booking_code`, and `access_key_hash`).

    Without `table_id` the smallest free bookable table that fits is assigned; for a start
    today, occupied tables are skipped (FR9.11). Errors: `conflict` (the chosen table is
    taken), `table_occupied` (the chosen table is occupied and the start is today),
    `no_table_available`, `validation_failed` (party above the maximum, outside the hours or
    window, a table that is too small)."""
    now = now or datetime.now(UTC)
    if starts_at.tzinfo is None:
        raise ValidationFailedError("starts_at needs a time zone offset", {"field": "starts_at"})
    settings = await get_settings(conn, outlet_id)
    tz = await _outlet_tz(conn, outlet_id)
    check_party(party_size, settings)
    check_booking_time(starts_at, settings, tz, now)
    ends_at = starts_at + timedelta(minutes=settings["default_duration_minutes"])
    await release_no_shows(conn, outlet_id)
    values = {
        "guest_name": (guest_name or "").strip() or None,
        "guest_phone": (guest_phone or "").strip() or None,
        "contact_id": contact_id,
        "party_size": party_size,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "source": source,
        "status": "booked",
        **(web or {}),
    }
    occupied = await _occupied_if_today(conn, outlet_id, starts_at, tz, now)
    res_id: UUID | None = None
    if table_id is not None:
        table = await _require_table(conn, outlet_id, table_id)
        if not table["is_bookable"]:
            raise ValidationFailedError(
                "this table is not open for reservations", {"field": "table_id"}
            )
        _check_fits(table, party_size)
        if table_id in occupied:
            raise ConflictError("table_occupied", "this table is in use today")
        res_id = await _insert(conn, ctx, outlet_id, table_id, values)
        if res_id is None:
            raise ConflictError("conflict", "this table is already booked or occupied at that time")
    else:
        for candidate in await _candidate_tables(
            conn, outlet_id, party_size, starts_at, ends_at, skip=occupied
        ):
            res_id = await _insert(conn, ctx, outlet_id, candidate, values)
            if res_id is not None:
                table_id = candidate
                break
        if res_id is None:
            raise ConflictError("no_table_available", "no free table fits this party at that time")
    row = {"id": res_id, "outlet_id": outlet_id}
    await _event(
        conn,
        ctx,
        row,
        "created",
        to_status="booked",
        data={"source": source, "table_id": str(table_id)},
    )
    await _schedule_no_show(conn, ctx, outlet_id, res_id, starts_at)
    return res_id


async def create_walk_in(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, *, table_id: UUID, party_size: int
) -> UUID:
    """S6 "Tandai meja terisi (tanpa reservasi)": the table is occupied from now for the
    outlet's default duration. Any table may be used (bookable or not), but not one that is
    already occupied by an open order or bill (`table_occupied`, FR9.11)."""
    settings = await get_settings(conn, outlet_id)
    table = await _require_table(conn, outlet_id, table_id)
    _check_fits(table, party_size)
    if await occupancy.is_occupied(conn, table_id):
        raise ConflictError("table_occupied", "this table is already in use")
    await release_no_shows(conn, outlet_id)
    cur = await conn.execute("select now()")
    start = (await cur.fetchone())[0]  # type: ignore[index]
    values = {
        "party_size": party_size,
        "starts_at": start,
        "ends_at": start + timedelta(minutes=settings["default_duration_minutes"]),
        "source": "walk_in",
        "status": "seated",
    }
    res_id = await _insert(conn, ctx, outlet_id, table_id, values)
    if res_id is None:
        raise ConflictError("conflict", "this table is booked or occupied during the next visit")
    await _event(
        conn,
        ctx,
        {"id": res_id, "outlet_id": outlet_id},
        "created",
        to_status="seated",
        data={"source": "walk_in", "table_id": str(table_id)},
    )
    return res_id


async def _lock(conn: AsyncConnection, res_id: UUID) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute("select outlet_id from app.reservations where id = %s", (res_id,))
    found = await cur.fetchone()
    if found is None:
        raise NotFoundError("reservation")
    await release_no_shows(conn, found["outlet_id"])
    await cur.execute(
        "select id, outlet_id, table_id, party_size, starts_at, ends_at, status::text as status,"
        " source::text as source from app.reservations where id = %s for update",
        (res_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("reservation")
    return row


def _require_action(row: dict[str, Any], action: str, now: datetime) -> None:
    if action not in allowed_actions(row, now):
        if action == "seat" and row["status"] in ("booked", "no_show"):
            raise ConflictError("hold_expired", "the 15-minute hold has passed")
        if action == "no_show" and row["status"] == "booked":
            raise ConflictError("too_early", "the booking time has not started yet")
        raise ConflictError("invalid_transition", f"cannot {action} a {row['status']} reservation")


async def _set_status(
    conn: AsyncConnection,
    ctx: ActorContext,
    res_id: UUID,
    action: str,
    to_status: str,
    reason: str | None = None,
) -> None:
    row = await _lock(conn, res_id)
    _require_action(row, action, datetime.now(UTC))
    await conn.execute("update app.reservations set status = %s where id = %s", (to_status, res_id))
    await _event(
        conn,
        ctx,
        row,
        "status_changed",
        from_status=row["status"],
        to_status=to_status,
        data={"reason": reason} if reason else None,
    )
    if row["status"] == "booked":
        await _finish_job(conn, res_id, "cancelled")


async def seat(conn: AsyncConnection, ctx: ActorContext, res_id: UUID) -> None:
    await _set_status(conn, ctx, res_id, "seat", "seated")


async def cancel(
    conn: AsyncConnection, ctx: ActorContext, res_id: UUID, reason: str | None = None
) -> None:
    """`reason` shows in the S6 history (e.g. the customer cancelled in the web chat)."""
    await _set_status(conn, ctx, res_id, "cancel", "cancelled", reason)


async def mark_no_show(conn: AsyncConnection, ctx: ActorContext, res_id: UUID) -> None:
    await _set_status(conn, ctx, res_id, "no_show", "no_show")


async def complete(conn: AsyncConnection, ctx: ActorContext, res_id: UUID) -> None:
    """Guests left: the table is free again for the rest of the slot."""
    await _set_status(conn, ctx, res_id, "complete", "completed")


async def move(conn: AsyncConnection, ctx: ActorContext, res_id: UUID, table_id: UUID) -> None:
    row = await _lock(conn, res_id)
    _require_action(row, "move", datetime.now(UTC))
    if table_id == row["table_id"]:
        return
    table = await _require_table(conn, row["outlet_id"], table_id)
    if row["status"] == "booked" and not table["is_bookable"]:
        raise ValidationFailedError(
            "this table is not open for reservations", {"field": "table_id"}
        )
    _check_fits(table, row["party_size"])
    if (
        row["status"] == "booked"
        and occupancy.starts_today(
            row["starts_at"], await _outlet_tz(conn, row["outlet_id"]), datetime.now(UTC)
        )
        and await occupancy.is_occupied(conn, table_id)
    ):
        raise ConflictError("table_occupied", "this table is in use today")
    try:
        async with conn.transaction():
            await conn.execute(
                "update app.reservations set table_id = %s where id = %s", (table_id, res_id)
            )
    except errors.ExclusionViolation:
        raise ConflictError(
            "conflict", "this table is already booked or occupied at that time"
        ) from None
    await _event(
        conn,
        ctx,
        row,
        "table_changed",
        data={"from_table_id": str(row["table_id"]), "to_table_id": str(table_id)},
    )


async def reschedule(
    conn: AsyncConnection,
    ctx: ActorContext,
    res_id: UUID,
    starts_at: datetime,
    *,
    now: datetime | None = None,
) -> None:
    """C12 "Jadwal ulang": a new time for a `booked` booking, same party. The current table is
    kept when it is still free, otherwise the smallest free table that fits is taken; the
    exclusion constraint still guards every move (FR9.3); occupied tables are skipped for a
    new time today (FR9.11). The caller checks the cutoff."""
    now = now or datetime.now(UTC)
    if starts_at.tzinfo is None:
        raise ValidationFailedError("starts_at needs a time zone offset", {"field": "starts_at"})
    row = await _lock(conn, res_id)
    if row["status"] != "booked":
        raise ConflictError("invalid_transition", f"cannot reschedule a {row['status']} booking")
    settings = await get_settings(conn, row["outlet_id"])
    tz = await _outlet_tz(conn, row["outlet_id"])
    check_booking_time(starts_at, settings, tz, now)
    if starts_at == row["starts_at"]:
        return
    ends_at = starts_at + timedelta(minutes=settings["default_duration_minutes"])
    # The current table first, but only while the outlet still offers it for this party
    # (active, bookable, big enough), like `move` and `_candidate_tables` (PR #64 review).
    occupied = await _occupied_if_today(conn, row["outlet_id"], starts_at, tz, now)
    candidates: list[UUID] = []
    cur = await conn.execute(
        "select 1 from app.tables where id = %s and outlet_id = %s and is_active"
        " and is_bookable and capacity >= %s",
        (row["table_id"], row["outlet_id"], row["party_size"]),
    )
    if await cur.fetchone() is not None and row["table_id"] not in occupied:
        candidates.append(row["table_id"])
    for t in await _candidate_tables(
        conn, row["outlet_id"], row["party_size"], starts_at, ends_at, skip=occupied
    ):
        if t not in candidates:
            candidates.append(t)
    moved_to: UUID | None = None
    for table_id in candidates:
        try:
            async with conn.transaction():
                await conn.execute(
                    "update app.reservations set table_id = %s, starts_at = %s, ends_at = %s"
                    " where id = %s",
                    (table_id, starts_at, ends_at, res_id),
                )
        except errors.ExclusionViolation:
            continue
        moved_to = table_id
        break
    if moved_to is None:
        raise ConflictError("no_table_available", "no free table fits this party at that time")
    await _event(
        conn,
        ctx,
        row,
        "rescheduled",
        data={
            "from_starts_at": row["starts_at"].isoformat(),
            "to_starts_at": starts_at.isoformat(),
            "from_table_id": str(row["table_id"]),
            "to_table_id": str(moved_to),
        },
    )
    await conn.execute(
        "update app.scheduled_jobs set run_at = %s where job_key = %s"
        " and status in ('pending', 'enqueued')",
        (starts_at + HOLD, f"no_show_release:{res_id}"),
    )


# Reads -----------------------------------------------------------------------------------
_ROW_SQL = """
select r.id, r.outlet_id, r.table_id, t.name as table_name,
       r.guest_name as guest_name_enc, c.display_name as contact_name, r.guest_phone,
       c.phone as contact_phone,
       r.party_size, r.starts_at, r.ends_at, r.status::text as status, r.source::text as source,
       (select e.created_at from app.reservation_events e
         where e.reservation_id = r.id and e.to_status = 'no_show'
         order by e.created_at desc limit 1) as no_show_at
from app.reservations r
join app.tables t on t.id = r.table_id
left join app.whatsapp_contacts c on c.id = r.contact_id
"""


def _decrypt_row(row: dict[str, Any]) -> dict[str, Any]:
    """Guest name and phone are stored encrypted; WhatsApp contacts (Phase 3) are not."""
    name = crypto.decrypt(row.pop("guest_name_enc"), "reservations.guest_name")
    contact = row.pop("contact_name")
    row["guest_name"] = name or contact
    row["guest_phone"] = crypto.decrypt(row["guest_phone"], "reservations.guest_phone")
    return row


def _public(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    out = {k: v for k, v in row.items() if k not in ("guest_phone", "contact_phone", "outlet_id")}
    out["hold_until"] = hold_until(row)
    out["allowed_actions"] = allowed_actions(row, now)
    return out


async def board(conn: AsyncConnection, outlet_id: UUID, day: date | None) -> dict[str, Any]:
    """S6 day timeline: tables and the day's reservations (cancelled ones are left out)."""
    tz = await _outlet_tz(conn, outlet_id)
    settings = await get_settings(conn, outlet_id)
    await release_no_shows(conn, outlet_id)
    now = datetime.now(UTC)
    day = day or now.astimezone(ZoneInfo(tz)).date()
    start, end = local_day_bounds(day, tz)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        _ROW_SQL + " where r.outlet_id = %s and r.status <> 'cancelled'"
        " and tstzrange(r.starts_at, r.ends_at, '[)') && tstzrange(%s, %s, '[)')"
        " order by r.starts_at, t.name",
        (outlet_id, start, end),
    )
    rows = [_decrypt_row(r) for r in await cur.fetchall()]
    used = {r["table_id"] for r in rows}
    await cur.execute(
        "select id, name, capacity, area, is_bookable, is_active from app.tables"
        " where outlet_id = %s order by name",
        (outlet_id,),
    )
    is_today = day == now.astimezone(ZoneInfo(tz)).date()
    occupied = await occupancy.details(conn, outlet_id) if is_today else {}
    tables = [
        {
            **{k: t[k] for k in ("id", "name", "capacity", "area", "is_bookable")},
            "occupancy": occupied.get(t["id"]),
        }
        for t in await cur.fetchall()
        if t["is_active"] or t["id"] in used
    ]
    public_rows = []
    for r in rows:
        out = _public(r, now)
        # A booking later today on a table in use: staff move one of them (FR9.11).
        out["table_occupied"] = (
            r["status"] == "booked"
            and r["table_id"] in occupied
            and occupancy.starts_today(r["starts_at"], tz, now)
        )
        public_rows.append(out)
    return {
        "date": day,
        "timezone": tz,
        "settings": {
            k: settings[k]
            for k in (
                "bookable_from",
                "bookable_until",
                "default_duration_minutes",
                "max_party_size",
                "booking_window_days",
                "hold_minutes",
            )
        },
        "tables": tables,
        "reservations": public_rows,
    }


async def detail(conn: AsyncConnection, res_id: UUID) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute("select outlet_id from app.reservations where id = %s", (res_id,))
    found = await cur.fetchone()
    if found is None:
        raise NotFoundError("reservation")
    await release_no_shows(conn, found["outlet_id"])
    await cur.execute(_ROW_SQL + " where r.id = %s", (res_id,))
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("reservation")
    row = _decrypt_row(row)
    await cur.execute(
        """
        select e.event, e.from_status::text as from_status, e.to_status::text as to_status,
               e.data, e.actor_type::text as actor_type, u.display_name as actor_name, e.created_at
        from app.reservation_events e
        left join app.users u on u.id = e.actor_id
        where e.reservation_id = %s order by e.created_at, e.id
        """,
        (res_id,),
    )
    events = await cur.fetchall()
    names: dict[str, str] = {}
    table_ids = {
        e["data"].get(k)
        for e in events
        for k in ("from_table_id", "to_table_id")
        if e["data"].get(k)
    }
    if table_ids:
        await cur.execute(
            "select id::text, name from app.tables where id = any(%s::uuid[])", (list(table_ids),)
        )
        names = {r["id"]: r["name"] for r in await cur.fetchall()}
    for e in events:
        data = e.pop("data")
        e["from_table"] = names.get(data.get("from_table_id", ""))
        e["to_table"] = names.get(data.get("to_table_id", ""))
        e["reason"] = data.get("reason")
    tz = await _outlet_tz(conn, row["outlet_id"])
    out = _public(row, datetime.now(UTC))
    out["phone_masked"] = mask_phone(row["guest_phone"] or row["contact_phone"])
    out["timezone"] = tz
    out["events"] = events
    return out
