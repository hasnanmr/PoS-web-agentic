"""Staff attendance on the outlet tablet (T-116, T-121, T-122) — screens K0-K4 and O3.

- O3 "Tablet absensi": the owner creates a one-time 6-digit pairing code (10 minutes), sees the
  paired tablet with its last activity, and forgets ("Lupakan perangkat") it. An outlet has at
  most one active tablet: a new code or pairing is refused (`tablet_already_paired`) until the
  current one is forgotten.
- K0: the tablet trades the code for a device token. Only a SHA-256 hash of the code and of the
  token is stored. Every tablet request resolves the token (`resolve_device`) and then runs as
  actor ``device`` scoped to its outlet; RLS lets that actor touch attendance tables only.
- K1-K4: the tablet lists the outlet's staff; a tap plus a required selfie clocks the person in,
  or out when they are working (one open record per staff member, FR5.1). Times are the
  database clock; the outlet zone is used only for display.

PoC demo: selfies are stored in the database (``app.attendance_selfies``), like the QRIS image.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from psycopg import AsyncConnection, AsyncCursor, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, DomainError, NotFoundError, ValidationFailedError

PAIRING_CODE_TTL = timedelta(minutes=10)
SELFIE_MAX_BYTES = 2 * 1024 * 1024
# A selfie must be linked to a clock in/out soon after it was taken (K2 → K3 → Simpan).
SELFIE_MAX_AGE = timedelta(minutes=10)
TOKEN_PREFIX = "dev_"  # noqa: S105 - a prefix, not a secret
ONE_TABLET_CONSTRAINT = "attendance_devices_one_active_per_outlet"


class DeviceForbiddenError(DomainError):
    status_code = 403


class SelfieRequiredError(DomainError):
    status_code = 422


def _tablet_already_paired() -> ConflictError:
    return ConflictError(
        "tablet_already_paired",
        "this outlet already has an attendance tablet; forget it before pairing a new one",
    )


def _is_one_tablet_violation(exc: errors.UniqueViolation) -> bool:
    return getattr(exc.diag, "constraint_name", None) == ONE_TABLET_CONSTRAINT


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def new_device_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


# O3 · Tablet absensi (owner) -----------------------------------------------------------------


async def create_pairing_code(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID
) -> dict[str, Any]:
    """`{code, expires_at}`. The code is shown once and only its hash is stored.
    `tablet_already_paired` (409) while the outlet still has an active tablet."""
    cur = await conn.execute("select now()")
    row = await cur.fetchone()
    assert row is not None  # noqa: S101
    expires_at = row[0] + PAIRING_CODE_TTL
    for _ in range(20):
        code = new_pairing_code()
        try:
            cur = await conn.execute(
                "select app.create_attendance_pairing_code(%s, %s, %s)",
                (outlet_id, hash_secret(code), expires_at),
            )
        except errors.UniqueViolation as exc:
            if _is_one_tablet_violation(exc):
                raise _tablet_already_paired() from exc
            raise
        created = await cur.fetchone()
        if created and created[0]:
            await record_audit(
                conn,
                ctx,
                action="attendance_device.pairing_code_created",
                entity_type="outlet",
                entity_id=outlet_id,
                outlet_id=outlet_id,
                data={"expires_at": expires_at.isoformat()},
            )
            return {"code": code, "expires_at": expires_at}
    raise ConflictError("pairing_code_unavailable", "could not draw a free pairing code")


async def list_devices(conn: AsyncConnection, outlet_id: UUID) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select id, name, paired_at, last_seen_at, revoked_at from app.attendance_devices
        where outlet_id = %s order by revoked_at is not null, paired_at
        """,
        (outlet_id,),
    )
    return await cur.fetchall()


async def revoke_device(
    conn: AsyncConnection, ctx: ActorContext, device_id: UUID
) -> dict[str, Any]:
    """O3 "Lupakan perangkat": the tablet is refused on its next request (`device_revoked`) and
    the outlet can pair a new one."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        update app.attendance_devices
           set revoked_at = coalesce(revoked_at, now()), revoked_by = coalesce(revoked_by, %s)
         where id = %s
        returning id, outlet_id, name, paired_at, last_seen_at, revoked_at
        """,
        (ctx.user_id, device_id),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("attendance device")
    await record_audit(
        conn,
        ctx,
        action="attendance_device.revoked",
        entity_type="attendance_device",
        entity_id=device_id,
        outlet_id=row["outlet_id"],
        data={"name": row["name"]},
    )
    row.pop("outlet_id")
    return row


# K0 · Pairing and the device session ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Device:
    device_id: UUID
    tenant_id: UUID
    outlet_id: UUID
    device_name: str
    outlet_name: str
    timezone: str
    revoked: bool = False

    def actor(self, correlation_id: str | None = None) -> ActorContext:
        return ActorContext.for_device(
            self.tenant_id, self.device_id, self.outlet_id, correlation_id=correlation_id
        )


async def pair_device(conn: AsyncConnection, code: str) -> tuple[str, Device]:
    """Trade a pairing code for `(device_token, device)`; `pairing_code_invalid` otherwise, and
    `tablet_already_paired` when the outlet still has an active tablet (the code stays unused)."""
    token = new_device_token()
    cur = conn.cursor(row_factory=dict_row)
    try:
        await cur.execute(
            "select * from app.pair_attendance_device(%s, %s)",
            (hash_secret(code), hash_secret(token)),
        )
    except errors.UniqueViolation as exc:
        if _is_one_tablet_violation(exc):
            raise _tablet_already_paired() from exc
        raise
    row = await cur.fetchone()
    if row is None:
        raise DomainError("pairing_code_invalid", "the code is wrong, used, or expired")
    return token, Device(**row)


async def resolve_device(conn: AsyncConnection, token: str) -> Device | None:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute("select * from app.resolve_attendance_device(%s)", (hash_secret(token),))
    row = await cur.fetchone()
    return Device(**row) if row else None


# K1 · Staff list -----------------------------------------------------------------------------


async def outlet_staff(conn: AsyncConnection) -> list[dict[str, Any]]:
    """Staff assigned to the tablet's outlet with today's state (device context)."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select s.user_id, s.display_name, not s.has_attendance as first_time,
               r.clock_in_at as since, s.assigned
        from app.device_outlet_staff() s
        left join app.attendance_records r
          on r.user_id = s.user_id and r.status = 'open'
         and r.outlet_id = app.current_device_outlet()
        order by s.display_name
        """
    )
    rows = await cur.fetchall()
    for r in rows:
        r["status"] = "working" if r["since"] else "not_clocked_in"
    # Unassigned people are listed only while they still have to clock out here.
    return [r for r in rows if r.pop("assigned") or r["since"]]


# K2/K3 · Selfie ------------------------------------------------------------------------------

_SELFIE_TYPES = {"image/jpeg", "image/webp"}


def validate_selfie(content_type: str, data: bytes) -> str:
    kind = (content_type or "").split(";")[0].strip().lower()
    if kind == "image/jpg":
        kind = "image/jpeg"
    ok_magic = (kind == "image/jpeg" and data.startswith(b"\xff\xd8\xff")) or (
        kind == "image/webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    )
    if kind not in _SELFIE_TYPES or not ok_magic:
        raise ValidationFailedError("only JPEG or WebP photos", {"field": "selfie"})
    if len(data) > SELFIE_MAX_BYTES:
        raise ValidationFailedError("the photo is larger than 2 MB", {"field": "selfie"})
    return kind


async def save_selfie(
    conn: AsyncConnection, ctx: ActorContext, *, content_type: str, data: bytes
) -> UUID:
    kind = validate_selfie(content_type, data)
    selfie_id = uuid4()
    await conn.execute(
        """
        insert into app.attendance_selfies
          (id, tenant_id, outlet_id, device_id, content_type, image)
        values (%s, %s, %s, %s, %s, %s)
        """,
        (selfie_id, ctx.tenant_id, ctx.device_outlet_id, ctx.device_id, kind, data),
    )
    return selfie_id


# K3 · Simpan: clock in or clock out -----------------------------------------------------------


async def _usable_selfie(cur: AsyncCursor[dict[str, Any]], selfie_id: UUID) -> None:
    """The selfie was uploaded by this tablet a few minutes ago and is not linked yet."""
    await cur.execute(
        """
        select 1 from app.attendance_selfies s
        where s.id = %s and s.device_id = app.current_device_id()
          and s.created_at > now() - %s
          and not exists (select 1 from app.attendance_records r
                          where s.id in (r.clock_in_selfie_id, r.clock_out_selfie_id))
        """,
        (selfie_id, SELFIE_MAX_AGE),
    )
    if await cur.fetchone() is None:
        raise SelfieRequiredError("selfie_required", "a new selfie is required")


Action = Literal["clock_in", "clock_out"]


async def _person(cur: AsyncCursor[dict[str, Any]], user_id: UUID) -> dict[str, Any] | None:
    await cur.execute(
        "select display_name, has_attendance, assigned from app.device_outlet_staff()"
        " where user_id = %s",
        (user_id,),
    )
    return await cur.fetchone()


async def _replay(
    cur: AsyncCursor[dict[str, Any]], user_id: UUID, selfie_id: UUID
) -> dict[str, Any] | None:
    """The stored result when this selfie already saved a clock in/out for this person (a
    retried or duplicated "Simpan"), so a retry never flips the result."""
    await cur.execute(
        """
        select r.clock_in_at, r.clock_out_at, r.clock_out_selfie_id = s.id as is_out
        from app.attendance_selfies s
        join app.attendance_records r on s.id in (r.clock_in_selfie_id, r.clock_out_selfie_id)
        where s.id = %s and s.device_id = app.current_device_id() and r.user_id = %s
        """,
        (selfie_id, user_id),
    )
    row = await cur.fetchone()
    if row is None:
        return None
    person = await _person(cur, user_id)
    name = person["display_name"] if person else ""
    if row["is_out"]:
        return _result("clock_out", name, row["clock_out_at"], row["clock_in_at"])
    return _result("clock_in", name, row["clock_in_at"], None)


def _result(
    action: Action, name: str, at: datetime, clock_in_at: datetime | None
) -> dict[str, Any]:
    minutes = int((at - clock_in_at).total_seconds() // 60) if clock_in_at else None
    return {"action": action, "display_name": name, "at": at, "duration_minutes": minutes}


def _state_changed() -> ConflictError:
    return ConflictError("state_changed", "this person's attendance changed; reload the staff list")


async def record_attendance(
    conn: AsyncConnection,
    ctx: ActorContext,
    *,
    user_id: UUID,
    selfie_id: UUID,
    action: Action,
) -> dict[str, Any]:
    """K3 "Simpan clock in" / "Simpan clock out". `action` is what K2/K3 showed the person; the
    server refuses it (`state_changed`) when the record says otherwise, so the tablet reloads K1
    instead of storing the opposite (K1 note: "Staf yang sedang bekerja tap namanya → otomatis
    jadi Clock out"). Idempotent per selfie: a retry with the same selfie returns the stored
    result."""
    cur = conn.cursor(row_factory=dict_row)
    replay = await _replay(cur, user_id, selfie_id)
    if replay is not None:
        return replay
    person = await _person(cur, user_id)
    if person is None:
        raise DeviceForbiddenError("not_assigned", "this person is not staff of this outlet")
    await _usable_selfie(cur, selfie_id)

    await cur.execute(
        """
        select id, clock_in_at from app.attendance_records
        where user_id = %s and status = 'open' for update
        """,
        (user_id,),
    )
    open_record = await cur.fetchone()
    if open_record is None and (replay := await _replay(cur, user_id, selfie_id)):
        return replay  # a concurrent duplicate committed while this one waited
    if open_record is None and action == "clock_out":
        # Worked past closing + grace: the missing clock-out check flagged the record just before
        # this tap (or earlier today). The person is clocking out now, so close it here instead
        # of starting a new shift; the flag stays in the history.
        await cur.execute(
            """
            select id, clock_in_at from app.attendance_records
            where user_id = %s and outlet_id = app.current_device_outlet()
              and status = 'needs_correction' and clock_out_at is null
              and clock_in_at > now() - interval '24 hours'
            order by clock_in_at desc limit 1 for update
            """,
            (user_id,),
        )
        open_record = await cur.fetchone()
    if (open_record is not None) != (action == "clock_out"):
        raise _state_changed()

    if open_record is not None:
        await cur.execute(
            """
            update app.attendance_records
               set status = 'closed',
                   clock_out_at = greatest(now(), clock_in_at + interval '1 second'),
                   clock_out_device_id = %s, clock_out_selfie_id = %s
             where id = %s
            returning id, clock_in_at, clock_out_at
            """,
            (ctx.device_id, selfie_id, open_record["id"]),
        )
        row = await cur.fetchone()
        assert row is not None  # noqa: S101
        await _event(conn, ctx, row["id"], "clock_out", {"at": row["clock_out_at"].isoformat()})
        return _result("clock_out", person["display_name"], row["clock_out_at"], row["clock_in_at"])

    if not person["assigned"]:
        raise DeviceForbiddenError("not_assigned", "this person is not staff of this outlet")
    record_id = uuid4()
    try:
        async with conn.transaction():
            await cur.execute(
                """
                insert into app.attendance_records
                  (id, tenant_id, outlet_id, user_id, status, clock_in_at, clock_in_device_id,
                   clock_in_selfie_id)
                values (%s, %s, %s, %s, 'open', now(), %s, %s)
                returning clock_in_at
                """,
                (record_id, ctx.tenant_id, ctx.device_outlet_id, user_id, ctx.device_id, selfie_id),
            )
    except errors.UniqueViolation as exc:
        if replay := await _replay(cur, user_id, selfie_id):
            return replay
        if "attendance_one_open" in str(exc):
            # Still clocked in at another outlet (this tablet cannot see that record).
            raise ConflictError(
                "open_elsewhere", "this person is still clocked in at another outlet"
            ) from None
        raise
    row = await cur.fetchone()
    assert row is not None  # noqa: S101
    await _event(conn, ctx, record_id, "clock_in", {"at": row["clock_in_at"].isoformat()})
    return _result("clock_in", person["display_name"], row["clock_in_at"], None)


async def _event(
    conn: AsyncConnection, ctx: ActorContext, record_id: UUID, kind: str, data: dict[str, Any]
) -> None:
    await conn.execute(
        """
        insert into app.attendance_events
          (tenant_id, outlet_id, record_id, type, data, reason, actor_type, actor_id)
        select tenant_id, outlet_id, id, %s, %s, %s, %s, %s
        from app.attendance_records where id = %s
        """,
        (
            kind,
            Jsonb({"correlation_id": ctx.correlation_id, **data}),
            ctx.reason,
            ctx.actor_type.value,
            ctx.actor_id,
            record_id,
        ),
    )
