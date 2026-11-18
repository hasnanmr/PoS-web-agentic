"""Cashier shifts per drawer (T-039, T-040) — S8, S1 header, O10.

One open shift per drawer (unique index); cash payments need an open shift and are linked
to it. Closing is a blind count: the cashier submits the counted notes and coins first,
and only the response reveals the expected cash and the difference, which is posted to
the ledger as `cash_shortage` or `cash_surplus` (glossary §7).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core import ledger
from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.localtime import local_date

# S8 blind count: note counts per denomination, plus "Rp 1.000 & koin" entered as an amount.
NOTES = (100_000, 50_000, 20_000, 10_000, 5_000, 2_000)
COINS_KEY = "coins"
MAX_NOTES = 100_000
MAX_COINS = 100_000_000

_OPEN_SHIFTS = """
select s.id, s.drawer_id, d.name as drawer_name, s.opened_at, s.starting_cash,
       s.opened_by, u.display_name as opened_by_name,
       (select count(*) from app.cash_drawers d2
        where d2.outlet_id = d.outlet_id and d2.created_at <= d.created_at)
         as drawer_number
from app.cashier_shifts s
join app.cash_drawers d on d.id = s.drawer_id
left join app.users u on u.id = s.opened_by
where s.outlet_id = %s and s.status = 'open'
order by d.created_at
"""


async def open_shifts(conn: AsyncConnection, outlet_id: UUID) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(_OPEN_SHIFTS, (outlet_id,))
    return await cur.fetchall()


async def drawers_with_shift(conn: AsyncConnection, outlet_id: UUID) -> list[dict[str, Any]]:
    """S8 drawer cards. No expected cash before the count (blind count)."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, name from app.cash_drawers where outlet_id = %s and is_active"
        " order by created_at",
        (outlet_id,),
    )
    drawers = await cur.fetchall()
    await cur.execute(
        """
        select s.id, s.drawer_id, s.opened_at, s.starting_cash, u.display_name as opened_by,
               coalesce(sum(p.amount) filter (where p.method = 'cash'), 0) as cash_in,
               count(p.id) filter (where p.method = 'cash') as cash_in_count,
               coalesce((select -sum(l.amount) from app.ledger_entries l
                         where l.shift_id = s.id and l.type = 'refund'), 0) as cash_refunds
        from app.cashier_shifts s
        left join app.users u on u.id = s.opened_by
        left join app.payments p on p.shift_id = s.id
        where s.outlet_id = %s and s.status = 'open'
        group by s.id, u.display_name
        """,
        (outlet_id,),
    )
    by_drawer = {r.pop("drawer_id"): r for r in await cur.fetchall()}
    return [{"drawer": d, "shift": by_drawer.get(d["id"])} for d in drawers]


async def open_shift(
    conn: AsyncConnection, ctx: ActorContext, drawer_id: UUID, starting_cash: int
) -> UUID:
    cur = await conn.execute(
        "select outlet_id from app.cash_drawers where id = %s and is_active", (drawer_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("drawer")
    outlet_id = row[0]
    shift_id = uuid4()
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into app.cashier_shifts (id, tenant_id, outlet_id, drawer_id, opened_by,"
                " starting_cash) values (%s, %s, %s, %s, %s, %s)",
                (shift_id, ctx.tenant_id, outlet_id, drawer_id, ctx.user_id, starting_cash),
            )
    except errors.UniqueViolation:
        raise ConflictError("shift_already_open", "this drawer already has an open shift") from None
    await record_audit(
        conn,
        ctx,
        action="shift.opened",
        entity_type="cashier_shift",
        entity_id=shift_id,
        outlet_id=outlet_id,
        data={"drawer_id": str(drawer_id), "starting_cash": starting_cash},
    )
    return shift_id


async def shift_for_cash(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, drawer_id: UUID | None
) -> UUID:
    """The open shift that receives a cash payment. With a drawer_id, that drawer's shift.
    Without one, the cashier's own shift, or the only open shift; when it is ambiguous
    (several open shifts and none, or more than one, is the cashier's) the client must send
    `drawer_id`, so money never lands in someone else's drawer by accident.
    `shift_not_open` when there is none."""
    shifts = await open_shifts(conn, outlet_id)
    if drawer_id is not None:
        shifts = [s for s in shifts if s["drawer_id"] == drawer_id]
    if not shifts:
        raise ConflictError("shift_not_open", "open a cashier shift before taking cash")
    chosen = _unambiguous(shifts, ctx)
    if chosen is None:
        raise ValidationFailedError(
            "several cashier shifts are open; choose the drawer", {"field": "drawer_id"}
        )
    if not await _still_open(conn, chosen):
        raise ConflictError("shift_not_open", "open a cashier shift before taking cash")
    return chosen


async def _still_open(conn: AsyncConnection, shift_id: UUID) -> bool:
    """Share-lock the shift until the payment commits. A blind count closing it at the same
    time (FOR UPDATE) waits for this payment and counts it, or closes first and the payment
    sees `closed` here, so cash never lands on a shift after its count."""
    cur = await conn.execute(
        "select status::text from app.cashier_shifts where id = %s for share", (shift_id,)
    )
    row = await cur.fetchone()
    return row is not None and row[0] == "open"


def _unambiguous(shifts: list[dict[str, Any]], ctx: ActorContext) -> UUID | None:
    if len(shifts) == 1:
        return shifts[0]["id"]
    mine = [s for s in shifts if s["opened_by"] == ctx.user_id]
    return mine[0]["id"] if len(mine) == 1 else None


async def shift_for_refund(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID
) -> UUID | None:
    """The shift a cash refund leaves from: the cashier's own or the only open one, else
    None (no shift is touched; a closed shift's final count is never changed)."""
    chosen = _unambiguous(await open_shifts(conn, outlet_id), ctx)
    return chosen if chosen is not None and await _still_open(conn, chosen) else None


# Close with blind count (T-040) -------------------------------------------------------------


def counted_total(breakdown: Mapping[str, int]) -> int:
    """Sum the S8 count: notes x denomination + the coins amount. Unknown keys are refused."""
    allowed = {str(n) for n in NOTES} | {COINS_KEY}
    unknown = sorted(set(breakdown) - allowed)
    if unknown:
        raise ValidationFailedError(
            "unknown denomination", {"field": "count_breakdown", "keys": unknown}
        )
    total = 0
    for key, value in breakdown.items():
        limit = MAX_COINS if key == COINS_KEY else MAX_NOTES
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= limit:
            raise ValidationFailedError("enter a whole number", {"field": f"count_breakdown.{key}"})
        total += value if key == COINS_KEY else value * int(key)
    return total


def difference_kind(difference: int) -> Literal["shortage", "surplus", "none"]:
    if difference < 0:
        return "shortage"
    if difference > 0:
        return "surplus"
    return "none"


async def _cash_movements(conn: AsyncConnection, shift_id: UUID) -> tuple[int, int, int]:
    """Cash received (payments), how many, and cash refunded (positive) for one shift."""
    cur = await conn.execute(
        """
        select coalesce((select sum(amount) from app.payments
                         where shift_id = %(s)s and method = 'cash'), 0),
               (select count(*) from app.payments where shift_id = %(s)s and method = 'cash'),
               coalesce((select -sum(amount) from app.ledger_entries
                         where shift_id = %(s)s and type = 'refund'), 0)
        """,
        {"s": shift_id},
    )
    cash_in, count, refunds = await cur.fetchone()  # type: ignore[misc]
    return int(cash_in), int(count), int(refunds)


async def close_shift(
    conn: AsyncConnection, ctx: ActorContext, shift_id: UUID, breakdown: Mapping[str, int]
) -> dict[str, Any]:
    """S8 "Submit hitungan & tutup shift". Expected = starting cash + cash received - cash
    refunded; difference = counted - expected; non-zero difference posts to the ledger."""
    counted = counted_total(breakdown)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select s.id, s.outlet_id, s.drawer_id, s.status::text as status, s.starting_cash,"
        " s.opened_at, o.timezone from app.cashier_shifts s"
        " join app.outlets o on o.id = s.outlet_id where s.id = %s for update of s",
        (shift_id,),
    )
    shift = await cur.fetchone()
    if shift is None:
        raise NotFoundError("shift")
    if shift["status"] != "open":
        raise ConflictError("shift_closed", "this shift is already closed")
    cash_in, _, refunds = await _cash_movements(conn, shift_id)
    expected = shift["starting_cash"] + cash_in - refunds
    difference = counted - expected
    kind = difference_kind(difference)
    closed_at = datetime.now(UTC)
    await conn.execute(
        """
        update app.cashier_shifts
        set status = 'closed', closed_by = %s, closed_at = %s, counted_cash = %s,
            count_breakdown = %s, expected_cash = %s, difference = %s
        where id = %s
        """,
        (ctx.user_id, closed_at, counted, Jsonb(dict(breakdown)), expected, difference, shift_id),
    )
    if difference:
        await ledger.post(
            conn,
            ctx,
            shift["outlet_id"],
            "cash_shortage" if difference < 0 else "cash_surplus",
            difference,
            "cash",
            local_date(closed_at, shift["timezone"]),
            shift_id=shift_id,
        )
    await record_audit(
        conn,
        ctx,
        action="shift.closed",
        entity_type="cashier_shift",
        entity_id=shift_id,
        outlet_id=shift["outlet_id"],
        data={"counted_cash": counted, "expected_cash": expected, "difference": difference},
    )
    await cur.execute(
        "select d.id, d.name, u.display_name from app.cash_drawers d, app.users u"
        " where d.id = %s and u.id = %s",
        (shift["drawer_id"], ctx.user_id),
    )
    names = await cur.fetchone()
    return {
        "id": shift_id,
        "drawer": {"id": shift["drawer_id"], "name": names["name"] if names else None},
        "opened_at": shift["opened_at"],
        "closed_at": closed_at,
        "timezone": shift["timezone"],
        "starting_cash": shift["starting_cash"],
        "cash_in": cash_in,
        "cash_refunds": refunds,
        "expected_cash": expected,
        "counted_cash": counted,
        "difference": difference,
        "kind": kind,
        "counted_by": names["display_name"] if names else None,
    }
