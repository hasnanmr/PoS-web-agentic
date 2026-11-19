"""Attendance reports and corrections (T-118, T-119, T-122) — screens O14, S9 and M6.

- Missing clock-out (T-118): a record still open at the outlet's closing time (of its clock-in
  day, outlet-local) plus the grace period becomes ``needs_correction``. No clock-out time is
  invented. ``flagged_at`` is that due instant ("Ditandai otomatis 23:00 (tutup 22:00 + 1 jam)").
  Until the T-104 scheduler exists the check runs lazily (`run_due_checks`) before every
  attendance read or write, re-checking that the record is still open.
- Selfie purge (T-122): photos older than 30 days are deleted; the records stay.
- O14 (owner): records by outlet, staff and date range (outlet-local days), totals per staff
  member without flagged or open records, corrections with a required reason that keep the
  original values (append-only ``attendance_events``).
- S9/M6 (staff): today's status, own history and own selfies only (RLS).
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app import db
from app.core.actor import ActorContext
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.localtime import to_local, zone_label

SELFIE_RETENTION_DAYS = 30
COUNTED = ("closed", "corrected")

# T-118: due instant per open record. closes_at <= opens_at means the outlet closes after
# midnight; a day without opening hours counts as closing at local midnight; a clock-in after
# closing is flagged `grace` after the clock-in.
_FLAG_DUE = """
with o as (
  select r.id, r.clock_in_at, ou.attendance_grace_minutes as grace, ou.timezone,
         (r.clock_in_at at time zone ou.timezone)::date as day, oh.opens_at, oh.closes_at
  from app.attendance_records r
  join app.outlets ou on ou.id = r.outlet_id
  left join app.outlet_opening_hours oh
    on oh.outlet_id = r.outlet_id
   and oh.weekday = extract(isodow from (r.clock_in_at at time zone ou.timezone))
  where r.status = 'open'
), d as (
  select id, grace, timezone, closes_at,
         greatest(
           (case when closes_at is null then (day + 1)::timestamp
                 when closes_at <= opens_at then (day + 1) + closes_at
                 else day + closes_at end) at time zone timezone,
           clock_in_at) as closes_instant
  from o
)
update app.attendance_records r
   set status = 'needs_correction',
       flagged_at = d.closes_instant + make_interval(mins => d.grace)
  from d
 where r.id = d.id and r.status = 'open'
   and d.closes_instant + make_interval(mins => d.grace) <= now()
returning r.id, r.flagged_at, d.closes_instant, d.grace, d.timezone
"""


async def run_due_checks(pool: AsyncConnectionPool, tenant_id: UUID) -> dict[str, int]:
    """Flag forgotten clock-outs and purge old selfies for one tenant (system actor)."""
    ctx = ActorContext.for_system(tenant_id)
    async with db.transaction(pool, ctx) as conn:
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(_FLAG_DUE)
        flagged = await cur.fetchall()
        for r in flagged:
            await _event(
                conn,
                ctx,
                r["id"],
                "flag",
                {
                    "due_at": r["flagged_at"].isoformat(),
                    "closes_at": to_local(r["closes_instant"], r["timezone"]).strftime("%H:%M"),
                    "grace_minutes": r["grace"],
                },
            )
        cur2 = await conn.execute(
            "delete from app.attendance_selfies"
            " where created_at < now() - make_interval(days => %s)",
            (SELFIE_RETENTION_DAYS,),
        )
        purged = cur2.rowcount
    return {"flagged": len(flagged), "purged": purged}


async def _event(
    conn: AsyncConnection,
    ctx: ActorContext,
    record_id: UUID,
    kind: str,
    data: dict[str, Any],
    reason: str | None = None,
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
            reason,
            ctx.actor_type.value,
            ctx.actor_id,
            record_id,
        ),
    )


# Shared record shape ------------------------------------------------------------------------

_RECORD_SELECT = """
select r.id, (r.clock_in_at at time zone o.timezone)::date as date,
       r.user_id, u.display_name as user_name, r.outlet_id, o.name as outlet_name, o.timezone,
       r.clock_in_at, r.clock_out_at, r.status::text as status, r.flagged_at,
       r.clock_in_selfie_id is not null as has_selfie_in,
       r.clock_out_selfie_id is not null as has_selfie_out,
       r.clock_in_device_id, r.clock_out_device_id
from app.attendance_records r
join app.outlets o on o.id = r.outlet_id
join app.users u on u.id = r.user_id
"""


def _shape(r: dict[str, Any]) -> dict[str, Any]:
    minutes = None
    if r["clock_out_at"] is not None and r["status"] in COUNTED:
        minutes = int((r["clock_out_at"] - r["clock_in_at"]).total_seconds() // 60)
    return {
        "id": r["id"],
        "date": r["date"],
        "user": {"id": r["user_id"], "name": r["user_name"]},
        "outlet": {"id": r["outlet_id"], "name": r["outlet_name"]},
        "timezone": r["timezone"],
        "clock_in_at": r["clock_in_at"],
        "clock_out_at": r["clock_out_at"],
        "duration_minutes": minutes,
        "has_selfie_in": r["has_selfie_in"],
        "has_selfie_out": r["has_selfie_out"],
        "status": r["status"],
    }


async def _records(
    conn: AsyncConnection, where: list[str], params: list[Any]
) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    sql = _RECORD_SELECT + (" where " + " and ".join(where) if where else "")
    await cur.execute(sql + " order by r.clock_in_at desc", params)
    return await cur.fetchall()


# O14 · owner report ---------------------------------------------------------------------------


async def owner_report(
    conn: AsyncConnection,
    *,
    outlet_id: UUID | None,
    user_id: UUID | None,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    where = ["(r.clock_in_at at time zone o.timezone)::date between %s and %s"]
    params: list[Any] = [date_from, date_to]
    if outlet_id:
        where.append("r.outlet_id = %s")
        params.append(outlet_id)
    if user_id:
        where.append("r.user_id = %s")
        params.append(user_id)
    rows = [_shape(r) for r in await _records(conn, where, params)]

    summary: dict[UUID, dict[str, Any]] = {}
    for r in rows:
        s = summary.setdefault(
            r["user"]["id"],
            {"user": r["user"], "outlets": [], "worked_minutes": 0, "days": set()},
        )
        if r["outlet"]["name"] not in s["outlets"]:
            s["outlets"].append(r["outlet"]["name"])
        if r["status"] in COUNTED and r["duration_minutes"] is not None:
            s["worked_minutes"] += r["duration_minutes"]
            s["days"].add(r["date"])
    out = sorted(summary.values(), key=lambda s: s["user"]["name"].lower())
    for s in out:
        s["days"] = len(s["days"])
    return {
        "from": date_from,
        "to": date_to,
        "summary": out,
        "needs_correction_count": sum(1 for r in rows if r["status"] == "needs_correction"),
        "records": rows,
    }


CSV_COLUMNS = (
    "tanggal",
    "staf",
    "outlet",
    "zona",
    "masuk",
    "pulang",
    "durasi_menit",
    "status",
)


def report_csv(report: dict[str, Any]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for r in reversed(report["records"]):
        tz = r["timezone"]
        writer.writerow(
            [
                r["date"].isoformat(),
                r["user"]["name"],
                r["outlet"]["name"],
                zone_label(tz),
                to_local(r["clock_in_at"], tz).strftime("%H:%M"),
                to_local(r["clock_out_at"], tz).strftime("%H:%M") if r["clock_out_at"] else "",
                "" if r["duration_minutes"] is None else r["duration_minutes"],
                r["status"],
            ]
        )
    return out.getvalue()


async def _device_names(conn: AsyncConnection, ids: list[UUID | None]) -> dict[UUID, str]:
    wanted = [i for i in ids if i is not None]
    if not wanted:
        return {}
    cur = await conn.execute(
        "select id, name from app.attendance_device_names(%s::uuid[])", (wanted,)
    )
    return {row[0]: row[1] for row in await cur.fetchall()}


async def record_detail(conn: AsyncConnection, record_id: UUID) -> dict[str, Any]:
    """O14 right panel: the record, its original values, the flag and the correction history."""
    rows = await _records(conn, ["r.id = %s"], [record_id])
    if not rows:
        raise NotFoundError("attendance record")
    raw = rows[0]
    names = await _device_names(conn, [raw["clock_in_device_id"], raw["clock_out_device_id"]])
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select e.type::text as type, e.data, e.reason, e.created_at,
               e.actor_type::text as actor_type, u.display_name as actor_name
        from app.attendance_events e
        left join app.users u on u.id = e.actor_id and e.actor_type = 'user'
        where e.record_id = %s order by e.id
        """,
        (record_id,),
    )
    events = await cur.fetchall()
    original = {"clock_in_at": raw["clock_in_at"], "clock_out_at": None}
    flag: dict[str, Any] | None = None
    corrections = []
    for e in events:
        data = e["data"] or {}
        if e["type"] == "clock_in":
            original["clock_in_at"] = datetime.fromisoformat(data["at"])
        elif e["type"] == "clock_out":
            original["clock_out_at"] = datetime.fromisoformat(data["at"])
        elif e["type"] == "flag":
            flag = {
                "at": datetime.fromisoformat(data["due_at"]),
                "closes_at": data.get("closes_at"),
                "grace_minutes": data.get("grace_minutes"),
            }
        elif e["type"] == "correction":
            corrections.append(
                {
                    "at": e["created_at"],
                    "by": e["actor_name"] or "Owner",
                    "from": _times(data.get("from", {})),
                    "to": _times(data.get("to", {})),
                    "reason": e["reason"],
                }
            )
    return {
        **_shape(raw),
        "devices": {
            "clock_in": names.get(raw["clock_in_device_id"]),
            "clock_out": names.get(raw["clock_out_device_id"]),
        },
        "original": original,
        "flag": flag,
        "corrections": corrections,
    }


def _times(d: dict[str, Any]) -> dict[str, datetime | None]:
    return {
        k: (datetime.fromisoformat(d[k]) if d.get(k) else None)
        for k in ("clock_in_at", "clock_out_at")
    }


async def correct_record(
    conn: AsyncConnection,
    ctx: ActorContext,
    record_id: UUID,
    *,
    clock_in_at: datetime | None,
    clock_out_at: datetime | None,
) -> dict[str, Any]:
    """O14 "Simpan koreksi": `ctx.reason` is required (ActorContext.with_reason)."""
    if not ctx.reason:
        raise ValidationFailedError("a reason is required", {"field": "reason"})
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select status::text as status, clock_in_at, clock_out_at, now() as now"
        " from app.attendance_records where id = %s for update",
        (record_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("attendance record")
    if row["status"] == "open":
        raise ConflictError("record_open", "the staff member is still working; nothing to correct")
    new_in = clock_in_at or row["clock_in_at"]
    new_out = clock_out_at or row["clock_out_at"]
    if new_out is None:
        raise ValidationFailedError("the clock-out time is required", {"field": "clock_out_at"})
    if new_out <= new_in:
        raise ValidationFailedError("clock-out must be after clock-in", {"field": "clock_out_at"})
    if new_out > row["now"] or new_in > row["now"]:
        raise ValidationFailedError("times cannot be in the future", {"field": "clock_out_at"})
    if new_in == row["clock_in_at"] and new_out == row["clock_out_at"]:
        raise ValidationFailedError("nothing changed", {"field": "clock_out_at"})
    await cur.execute(
        "update app.attendance_records set clock_in_at = %s, clock_out_at = %s,"
        " status = 'corrected' where id = %s",
        (new_in, new_out, record_id),
    )

    def iso(v: datetime | None) -> str | None:
        return v.isoformat() if v else None

    await _event(
        conn,
        ctx,
        record_id,
        "correction",
        {
            "from": {
                "clock_in_at": iso(row["clock_in_at"]),
                "clock_out_at": iso(row["clock_out_at"]),
            },
            "to": {"clock_in_at": iso(new_in), "clock_out_at": iso(new_out)},
        },
        reason=ctx.reason,
    )
    return await record_detail(conn, record_id)


async def selfie_image(conn: AsyncConnection, record_id: UUID, which: str) -> tuple[str, bytes]:
    """The photo of a clock-in (`in`) or clock-out (`out`). RLS: owner or the person in it."""
    column = {"in": "clock_in_selfie_id", "out": "clock_out_selfie_id"}[which]
    cur = await conn.execute(
        f"select s.content_type, s.image from app.attendance_records r"  # noqa: S608 - fixed column
        f" join app.attendance_selfies s on s.id = r.{column} where r.id = %s",
        (record_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("selfie")
    return row[0], bytes(row[1])


# S9 / M6 · own attendance ---------------------------------------------------------------------


async def my_today(conn: AsyncConnection, user_id: UUID) -> dict[str, Any]:
    rows = await _records(
        conn, ["r.user_id = %s", "r.status in ('open', 'needs_correction')"], [user_id]
    )
    working = next((r for r in rows if r["status"] == "open"), None)
    names = await _device_names(conn, [working["clock_in_device_id"]] if working else [])
    return {
        "status": "working" if working else "not_clocked_in",
        "clock_in_at": working["clock_in_at"] if working else None,
        "device_name": names.get(working["clock_in_device_id"]) if working else None,
        "outlet": {"name": working["outlet_name"], "timezone": working["timezone"]}
        if working
        else None,
        "flagged_records": [
            {"id": r["id"], "date": r["date"], "outlet": {"name": r["outlet_name"]}}
            for r in rows
            if r["status"] == "needs_correction"
        ],
    }


async def my_history(
    conn: AsyncConnection, user_id: UUID, date_from: date, date_to: date
) -> dict[str, Any]:
    rows = [
        _shape(r)
        for r in await _records(
            conn,
            ["r.user_id = %s", "(r.clock_in_at at time zone o.timezone)::date between %s and %s"],
            [user_id, date_from, date_to],
        )
    ]
    total = sum(r["duration_minutes"] or 0 for r in rows if r["status"] in COUNTED)
    return {"from": date_from, "to": date_to, "records": rows, "total_minutes": total}
