"""Reservations in the customer web chat — wireframes C10-C12 on page 07 (T-060, T-061).

Only from the outlet link (`/o/<slug>`) and only when the outlet has reservations enabled. The
booking itself goes through `reservations.create_booking` (smallest free table, database
exclusion against double booking, 15-minute hold) with source `web_chat`.

Rules (PRD FR9.2, FR9.4, FR9.5, AC9.1-AC9.6, AC9.11, AC9.12):

- Name and phone number without verification, after the privacy notice (FR12.1); stored on a
  `customers` row and on the booking for the S6 board, and anonymized once it is finished.
- One phone number holds at most 2 upcoming bookings per outlet (`booking_limit_reached`).
- The chat gets a booking code (6 characters without look-alikes) and an access key. Another
  phone finds the booking with code + phone number and gets its own key; a wrong code or phone
  gives the same `booking_not_found`.
- Cancel and reschedule are allowed until the outlet's cancellation cutoff before the booking
  time (`change_window_closed`).
- No reminder message: the calendar file (.ics) carries an alert at the reminder offset (FR9.4).
"""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row

from app.core import reservations, web_chat
from app.core.actor import ActorContext
from app.core.errors import ConflictError, DomainError, NotFoundError, ValidationFailedError
from app.core.tables import HOLD_MINUTES, get_settings

MAX_UPCOMING_PER_PHONE = 2
MAX_EXTRA_KEYS = 5  # keys from "Cari dengan kode + HP" kept per booking
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
CUSTOMER_CANCEL_REASON = "Dibatalkan pelanggan dari web chat"


class PartyTooLargeError(DomainError):
    status_code = 422

    def __init__(self, maximum: int) -> None:
        super().__init__(
            "party_too_large", "the party is larger than the outlet allows", {"max": maximum}
        )


def _require_reservations(scope: web_chat.ChatScope) -> None:
    if scope.table_id is not None or not scope.reservations_enabled:
        raise ConflictError("reservations_unavailable", "this outlet does not take bookings here")


async def _settings(conn: AsyncConnection, scope: web_chat.ChatScope) -> dict[str, Any]:
    settings = await get_settings(conn, scope.outlet_id)
    return settings


def _check_party(party_size: int, settings: dict[str, Any]) -> None:
    if party_size > settings["max_party_size"]:
        raise PartyTooLargeError(settings["max_party_size"])


def time_label(start: datetime, tz: str) -> str:
    return start.astimezone(ZoneInfo(tz)).strftime("%H:%M")


# C10 times -------------------------------------------------------------------------------------


async def availability(
    conn: AsyncConnection, scope: web_chat.ChatScope, party_size: int, day: date
) -> dict[str, Any]:
    """Start times on the outlet-local `day` with a free table for the party (AC9.1, AC9.3)."""
    _require_reservations(scope)
    settings = await _settings(conn, scope)
    _check_party(party_size, settings)
    times = await reservations.available_start_times(
        conn, scope.outlet_id, day, party_size, now=datetime.now(UTC)
    )
    today = datetime.now(ZoneInfo(scope.timezone)).date()
    return {
        "date": day,
        "timezone": scope.timezone,
        "max_party_size": settings["max_party_size"],
        "last_date": today + timedelta(days=settings["booking_window_days"]),
        "times": [{"start_at": t, "label": time_label(t, scope.timezone)} for t in times],
    }


# C10 Konfirmasi booking ------------------------------------------------------------------------


async def _new_code(conn: AsyncConnection, outlet_id: UUID) -> str:
    for _ in range(10):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        cur = await conn.execute(
            "select 1 from app.reservations where outlet_id = %s and booking_code = %s",
            (outlet_id, code),
        )
        if await cur.fetchone() is None:
            return code
    raise ConflictError("conflict", "could not create a booking code; try again")


async def create(
    conn: AsyncConnection,
    ctx: ActorContext,
    scope: web_chat.ChatScope,
    *,
    party_size: int,
    start_at: datetime,
    name: str,
    phone: str,
    notice_version: str,
    access_key_hash: str,
) -> dict[str, Any]:
    _require_reservations(scope)
    settings = await _settings(conn, scope)
    _check_party(party_size, settings)
    # Two confirms with the same number at once must not both pass the limit (AC9.11).
    await conn.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"web_booking:{scope.outlet_id}:{phone}",),
    )
    cur = await conn.execute(
        "select count(*) from app.reservations where outlet_id = %s and source = 'web_chat'"
        " and guest_phone = %s and status = 'booked' and starts_at > now()",
        (scope.outlet_id, phone),
    )
    if (await cur.fetchone())[0] >= MAX_UPCOMING_PER_PHONE:  # type: ignore[index]
        raise ConflictError(
            "booking_limit_reached",
            "this phone number already has 2 upcoming bookings here",
            {"max": MAX_UPCOMING_PER_PHONE},
        )
    customer_id = await web_chat.record_customer(
        conn, ctx, scope.outlet_id, name=name, phone=phone, notice_version=notice_version
    )
    res_id: UUID | None = None
    for _ in range(5):
        code = await _new_code(conn, scope.outlet_id)
        try:
            # A savepoint: two confirms at once can draw the same code; the loser retries
            # with a new one instead of failing (PR #64 review).
            async with conn.transaction():
                res_id = await reservations.create_booking(
                    conn,
                    ctx,
                    scope.outlet_id,
                    party_size=party_size,
                    starts_at=start_at,
                    source="web_chat",
                    guest_name=name,
                    guest_phone=phone,
                    web={
                        "customer_id": customer_id,
                        "booking_code": code,
                        "access_key_hash": access_key_hash,
                    },
                )
            break
        except errors.UniqueViolation as exc:
            if "reservations_booking_code_key" not in str(exc):
                raise
        except ConflictError as exc:
            if exc.code in ("no_table_available", "conflict"):
                raise ConflictError("slot_unavailable", "that time was just taken") from None
            raise
    if res_id is None:
        raise ConflictError("conflict", "could not create a booking code; try again")
    return await booking(conn, scope, res_id)


# C11 · C12 -------------------------------------------------------------------------------------


_BOOKING_SQL = """
select r.id, r.booking_code, r.starts_at, r.ends_at, r.party_size, r.status::text as status,
       r.source::text as source, r.guest_name
from app.reservations r
where r.id = %s and r.outlet_id = %s and r.source = 'web_chat'
"""


async def booking(conn: AsyncConnection, scope: web_chat.ChatScope, res_id: UUID) -> dict[str, Any]:
    settings = await _settings(conn, scope)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(_BOOKING_SQL, (res_id, scope.outlet_id))
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("reservation")
    cutoff = timedelta(minutes=settings["cancellation_cutoff_minutes"])
    change_until = row["starts_at"] - cutoff
    now = datetime.now(UTC)
    return {
        "reservation_id": row["id"],
        "booking_code": row["booking_code"],
        "start_at": row["starts_at"],
        "label": time_label(row["starts_at"], scope.timezone),
        "timezone": scope.timezone,
        "party_size": row["party_size"],
        "status": row["status"],
        "guest_name": row["guest_name"],
        "hold_until": reservations.hold_until(row),
        "change_until": change_until,
        "can_change": row["status"] == "booked" and now < change_until,
        "outlet_name": scope.outlet_name,
    }


async def _check_key(
    conn: AsyncConnection, scope: web_chat.ChatScope, res_id: UUID, key: str | None
) -> None:
    """The booking, only with a key of this phone; anything else is `not_found` (ACN6)."""
    if not key:
        raise NotFoundError("reservation")
    digest = web_chat.hash_key(key)
    cur = await conn.execute(
        "select 1 from app.reservations r where r.id = %s and r.outlet_id = %s"
        " and r.source = 'web_chat' and (r.access_key_hash = %s or exists ("
        "   select 1 from app.reservation_access_keys k"
        "   where k.reservation_id = r.id and k.key_hash = %s))",
        (res_id, scope.outlet_id, digest, digest),
    )
    if await cur.fetchone() is None:
        raise NotFoundError("reservation")


async def read(
    conn: AsyncConnection, scope: web_chat.ChatScope, res_id: UUID, key: str | None
) -> dict[str, Any]:
    _require_reservations(scope)
    await reservations.release_no_shows(conn, scope.outlet_id)
    await _check_key(conn, scope, res_id, key)
    return await booking(conn, scope, res_id)


async def overview(
    conn: AsyncConnection, scope: web_chat.ChatScope, refs: list[tuple[UUID, str]]
) -> list[dict[str, Any]]:
    """C12 "Reservasi Saya": upcoming bookings whose keys this phone kept; others are left out
    silently (unknown, wrong key, finished, or in the past)."""
    _require_reservations(scope)
    await reservations.release_no_shows(conn, scope.outlet_id)
    now = datetime.now(UTC)
    out = []
    for res_id, key in refs:
        try:
            await _check_key(conn, scope, res_id, key)
        except NotFoundError:
            continue
        row = await booking(conn, scope, res_id)
        if row["status"] in ("booked", "seated") and row["start_at"] + reservations.HOLD > now:
            out.append(row)
    out.sort(key=lambda r: r["start_at"])
    return out


async def lookup(
    conn: AsyncConnection,
    ctx: ActorContext,
    scope: web_chat.ChatScope,
    code: str,
    phone: str,
    new_key_hash: str,
) -> UUID:
    """C12 "Cari dengan kode + HP": an upcoming booking with this code and phone gets a key for
    this phone. A wrong code and a wrong phone look the same (AC9.12)."""
    _require_reservations(scope)
    await reservations.release_no_shows(conn, scope.outlet_id)
    cur = await conn.execute(
        "select id from app.reservations where outlet_id = %s and source = 'web_chat'"
        " and booking_code = %s and guest_phone = %s and status in ('booked', 'seated')",
        (scope.outlet_id, code.strip().upper(), phone),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("reservation")
    await conn.execute(
        "insert into app.reservation_access_keys (tenant_id, outlet_id, reservation_id, key_hash)"
        " values (%s, %s, %s, %s)",
        (ctx.tenant_id, scope.outlet_id, row[0], new_key_hash),
    )
    # At most this many extra keys per booking: the oldest stop working first (PR #64 review).
    await conn.execute(
        "delete from app.reservation_access_keys where reservation_id = %s and id not in ("
        " select id from app.reservation_access_keys where reservation_id = %s"
        " order by id desc limit %s)",
        (row[0], row[0], MAX_EXTRA_KEYS),
    )
    return row[0]


async def _require_change_window(
    conn: AsyncConnection, scope: web_chat.ChatScope, res_id: UUID
) -> dict[str, Any]:
    row = await booking(conn, scope, res_id)
    if row["status"] != "booked":
        raise ConflictError(
            "booking_not_changeable",
            "this booking can no longer be changed here",
            {"status": row["status"]},
        )
    if not row["can_change"]:
        raise ConflictError(
            "change_window_closed",
            "too close to the booking time; contact the outlet",
            {"change_until": row["change_until"].isoformat()},
        )
    return row


async def cancel(
    conn: AsyncConnection,
    ctx: ActorContext,
    scope: web_chat.ChatScope,
    res_id: UUID,
    key: str | None,
) -> dict[str, Any]:
    """C12 "Batalkan": frees the table. Repeating it returns the same result (FR6.4)."""
    await read(conn, scope, res_id, key)
    await conn.execute("select 1 from app.reservations where id = %s for update", (res_id,))
    current = await booking(conn, scope, res_id)
    if current["status"] == "cancelled":
        return current
    await _require_change_window(conn, scope, res_id)
    await reservations.cancel(conn, ctx, res_id, CUSTOMER_CANCEL_REASON)
    return await booking(conn, scope, res_id)


async def reschedule(
    conn: AsyncConnection,
    ctx: ActorContext,
    scope: web_chat.ChatScope,
    res_id: UUID,
    key: str | None,
    start_at: datetime,
) -> dict[str, Any]:
    """C12 "Jadwal ulang": allowed until the cutoff; the new time must be free (AC9.6)."""
    await read(conn, scope, res_id, key)
    await conn.execute("select 1 from app.reservations where id = %s for update", (res_id,))
    await _require_change_window(conn, scope, res_id)
    try:
        await reservations.reschedule(conn, ctx, res_id, start_at)
    except ConflictError as exc:
        if exc.code == "no_table_available":
            raise ConflictError("slot_unavailable", "that time is not available") from None
        raise
    return await booking(conn, scope, res_id)


# C11 calendar file -------------------------------------------------------------------------------


def _ics_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


async def calendar(
    conn: AsyncConnection, scope: web_chat.ChatScope, res_id: UUID, key: str | None
) -> str:
    """The booking as an iCalendar event with an alert at the outlet's reminder offset
    (AC9.5). Times are UTC instants, so every calendar shows the outlet's local time."""
    row = await read(conn, scope, res_id, key)
    if row["status"] not in ("booked", "seated"):
        # A cancelled, finished, or no-show booking gets no calendar event (PR #64 review).
        raise NotFoundError("reservation")
    settings = await _settings(conn, scope)
    cur = await conn.execute("select ends_at from app.reservations where id = %s", (res_id,))
    ends_at = (await cur.fetchone())[0]  # type: ignore[index]
    reminder = settings["reminder_offset_minutes"]
    summary = _ics_text(f"Reservasi {scope.outlet_name} ({row['party_size']} orang)")
    description = _ics_text(
        f"Kode booking: {row['booking_code']}\nMeja ditahan sampai {HOLD_MINUTES} menit setelah"
        " jam booking."
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Thinker//Web Chat//ID",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{row['reservation_id']}@thinker",
        f"DTSTAMP:{_ics_time(datetime.now(UTC))}",
        f"DTSTART:{_ics_time(row['start_at'])}",
        f"DTEND:{_ics_time(ends_at)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{_ics_text(scope.outlet_name)}",
    ]
    if reminder > 0:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{summary}",
            f"TRIGGER:-PT{reminder}M",
            "END:VALARM",
        ]
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "".join(_fold(line) + "\r\n" for line in lines)


def _fold(line: str) -> str:
    """RFC 5545 §3.1: content lines are at most 75 octets; longer ones continue on the next
    line after CRLF + one space, never splitting a UTF-8 character."""
    out: list[str] = []
    current, size = "", 0
    for ch in line:
        width = len(ch.encode())
        limit = 75 if not out else 74  # continuation lines start with a space
        if size + width > limit:
            out.append(current)
            current, size = "", 0
        current += ch
        size += width
    out.append(current)
    return "\r\n ".join(out)


def validate_name(name: str) -> str:
    name = (name or "").strip()
    if not 1 <= len(name) <= 60:
        raise ValidationFailedError("name is required", {"field": "name"})
    return name
