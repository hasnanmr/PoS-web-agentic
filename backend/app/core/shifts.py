"""Cashier shifts per drawer (T-039) — S8 open, S1 header. Closing with the blind count
(T-040) comes in Wave 4. One open shift per drawer (unique index); cash payments need
an open shift and are linked to it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row

from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError

_OPEN_SHIFTS = """
select s.id, s.drawer_id, d.name as drawer_name, s.opened_at, s.starting_cash,
       s.opened_by, u.display_name as opened_by_name,
       (select count(*) from app.cash_drawers d2
        where d2.outlet_id = d.outlet_id and d2.is_active and d2.created_at <= d.created_at)
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
    return chosen


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
    return _unambiguous(await open_shifts(conn, outlet_id), ctx)
