"""Open bills (T-033) — screen S5.

One open bill per table (unique index) or per guest name. Orders from the counter or a
table QR join the table's bill. The bill is paid once, in full; split bills are not in
the MVP. PB1 on a bill is computed once on the bill subtotal at close (glossary §2,
proposed default until the product owner decides), so the running total shows the same
rule.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core import payments
from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.pricing import outlet_pb1
from app.core.tax import Quote, quote_totals


async def _insert(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    *,
    table_id: UUID | None,
    guest_name: str | None,
) -> UUID:
    bill_id = uuid4()
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into app.bills (id, tenant_id, outlet_id, table_id, guest_name,"
                " opened_by_actor, opened_by_id) values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    bill_id,
                    ctx.tenant_id,
                    outlet_id,
                    table_id,
                    guest_name,
                    ctx.actor_type.value,
                    ctx.actor_id,
                ),
            )
    except errors.UniqueViolation:
        raise ConflictError("conflict", "this table already has an open bill") from None
    except errors.ForeignKeyViolation:
        raise ValidationFailedError("unknown table", {"field": "table_id"}) from None
    return bill_id


async def open_bill(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    *,
    table_id: UUID | None,
    guest_name: str | None,
) -> UUID:
    """S5 "+ Buka bill": a table or a guest name. `conflict` when the table has one."""
    guest = (guest_name or "").strip() or None
    if (table_id is None) == (guest is None):
        raise ValidationFailedError("choose a table or enter a guest name", {"field": "table_id"})
    await _require_open_bill_outlet(conn, outlet_id)
    if guest is not None:
        cur = await conn.execute(
            "select 1 from app.bills where outlet_id = %s and status = 'open'"
            " and lower(guest_name) = lower(%s)",
            (outlet_id, guest),
        )
        if await cur.fetchone():
            raise ConflictError("conflict", "this guest already has an open bill")
    return await _insert(conn, ctx, outlet_id, table_id=table_id, guest_name=guest)


async def _require_open_bill_outlet(conn: AsyncConnection, outlet_id: UUID) -> None:
    cur = await conn.execute(
        "select payment_mode::text from app.outlets where id = %s", (outlet_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("outlet")
    if row[0] != "open_bill":
        raise ConflictError("payment_mode_pay_first", "this outlet uses pay first")


async def open_bill_for_table(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, table_id: UUID
) -> UUID:
    # FOR UPDATE, not a plain select: `void_empty` locks the same row, so a void and a new
    # order on the table serialize instead of leaving an order on a bill that got voided.
    existing = "select id from app.bills where table_id = %s and status = 'open' for update"
    cur = await conn.execute(existing, (table_id,))
    row = await cur.fetchone()
    if row:
        return row[0]
    try:
        return await _insert(conn, ctx, outlet_id, table_id=table_id, guest_name=None)
    except ConflictError:
        # Another order opened this table's bill between the select and the insert: join it.
        cur = await conn.execute(existing, (table_id,))
        row = await cur.fetchone()
        if row is None:
            raise
        return row[0]


async def void_if_empty(conn: AsyncConnection, bill_id: UUID) -> None:
    await conn.execute(
        "update app.bills set status = 'voided', closed_at = now()"
        " where id = %s and status = 'open'"
        " and not exists (select 1 from app.orders where bill_id = %s and status <> 'cancelled')",
        (bill_id, bill_id),
    )


async def void_empty(conn: AsyncConnection, ctx: ActorContext, bill_id: UUID) -> None:
    """S5: void an open bill that has no live orders (a wrong table, a guest who left).
    `bill_not_empty` when orders are on it: cancel or reverse those first."""
    cur = await conn.execute(
        "select outlet_id, status::text from app.bills where id = %s for update", (bill_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("bill")
    outlet_id, status = row
    if status != "open":
        raise ConflictError("bill_not_open", "this bill is already closed")
    cur = await conn.execute(
        "select exists (select 1 from app.orders where bill_id = %s and status <> 'cancelled')",
        (bill_id,),
    )
    if (await cur.fetchone())[0]:  # type: ignore[index]
        raise ConflictError("bill_not_empty", "this bill has orders; cancel them first")
    await conn.execute(
        "update app.bills set status = 'voided', closed_at = now(), closed_by = %s where id = %s",
        (ctx.user_id, bill_id),
    )
    await record_audit(
        conn,
        ctx,
        action="bill.voided",
        entity_type="bill",
        entity_id=bill_id,
        outlet_id=outlet_id,
    )


async def _totals(conn: AsyncConnection, outlet_id: UUID, subtotal: int) -> Quote:
    return quote_totals(subtotal, await outlet_pb1(conn, outlet_id))


_BILLS_SQL = """
select b.id, b.outlet_id, b.table_id, t.name as table_name, t.area as table_area, b.guest_name,
       b.status::text as status, b.opened_at,
       coalesce(sum(o.subtotal) filter (where o.status <> 'cancelled'), 0) as subtotal,
       count(o.id) filter (where o.status <> 'cancelled') as order_count
from app.bills b
left join app.tables t on t.id = b.table_id
left join app.orders o on o.bill_id = b.id
"""


async def list_open(conn: AsyncConnection, outlet_id: UUID) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        _BILLS_SQL + " where b.outlet_id = %s and b.status = 'open' group by b.id, t.id"
        " order by b.opened_at",
        (outlet_id,),
    )
    rows = await cur.fetchall()
    pb1 = await outlet_pb1(conn, outlet_id)  # one lookup for the whole list
    return [{**r, "running_total": quote_totals(int(r["subtotal"]), pb1).total} for r in rows]


async def detail(conn: AsyncConnection, bill_id: UUID) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(_BILLS_SQL + " where b.id = %s group by b.id, t.id", (bill_id,))
    bill = await cur.fetchone()
    if bill is None:
        raise NotFoundError("bill")
    await cur.execute(
        """
        select o.id, o.order_no, ou.order_prefix, o.channel::text as channel, o.created_at,
               o.status::text as status, o.subtotal as line_total
        from app.orders o join app.outlets ou on ou.id = o.outlet_id
        where o.bill_id = %s and o.status <> 'cancelled' order by o.created_at
        """,
        (bill_id,),
    )
    orders = await cur.fetchall()
    await cur.execute(
        """
        select i.order_id, i.name, i.quantity,
               coalesce(string_agg(a.name, ', '), '') as addons
        from app.order_items i left join app.order_item_addons a on a.order_item_id = i.id
        where i.order_id = any(%s) group by i.id order by i.name
        """,
        ([o["id"] for o in orders],),
    )
    items: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for r in await cur.fetchall():
        items[r.pop("order_id")].append(r)
    for o in orders:
        o["order_no"] = f"#{o.pop('order_prefix')}-{o['order_no']}"
        o["items"] = items.get(o["id"], [])
    if bill["status"] == "open":
        totals = await _totals(conn, bill["outlet_id"], int(bill["subtotal"]))
        pb1_rate, pb1, total = totals.pb1_rate_bps, totals.pb1_amount, totals.total
    else:
        # A closed or voided bill reads every money figure from its snapshot, so a reversal
        # after close does not make the subtotal disagree with the total that was paid.
        await cur.execute(
            "select subtotal, pb1_rate_bps, pb1_amount, total from app.bills where id = %s",
            (bill_id,),
        )
        snap = await cur.fetchone()
        assert snap is not None  # noqa: S101
        if snap["subtotal"] is not None:
            bill["subtotal"] = snap["subtotal"]
        pb1_rate, pb1, total = snap["pb1_rate_bps"], snap["pb1_amount"] or 0, snap["total"] or 0
    return {**bill, "orders": orders, "pb1_rate_bps": pb1_rate, "pb1_amount": pb1, "total": total}


async def close(
    conn: AsyncConnection, ctx: ActorContext, bill_id: UUID, payment: payments.PaymentInput
) -> dict[str, Any]:
    """S5 "Tutup bill & bayar": one full payment; every order on it becomes paid and completed."""
    cur = await conn.execute(
        "select outlet_id, status::text from app.bills where id = %s for update", (bill_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("bill")
    outlet_id, status = row
    if status != "open":
        raise ConflictError("bill_not_open", "this bill is already closed")
    cur = await conn.execute(
        "select id, status::text from app.orders where bill_id = %s and status <> 'cancelled'"
        " for update",
        (bill_id,),
    )
    orders = await cur.fetchall()
    if not orders:
        raise ConflictError("bill_empty", "this bill has no orders")
    cur = await conn.execute(
        "select coalesce(sum(subtotal), 0) from app.orders where bill_id = %s"
        " and status <> 'cancelled'",
        (bill_id,),
    )
    subtotal = int((await cur.fetchone())[0])  # type: ignore[index]
    totals = await _totals(conn, outlet_id, subtotal)
    result = await payments.capture(
        conn,
        ctx,
        outlet_id,
        payment,
        amount=totals.total,
        subtotal=totals.subtotal,
        pb1_amount=totals.pb1_amount,
        bill_id=bill_id,
    )
    # Closing a bill completes every live order on it, whatever its kitchen status
    # (confirmed, preparing, ready): the table has been served and paid (glossary §5). This
    # deliberately bypasses the per-order state machine; do not route it through it. The
    # order_events rows are written here (not via orders._event) to avoid an import cycle.
    for order_id, order_status in orders:
        await conn.execute(
            "update app.orders set payment_status = 'paid', status = 'completed' where id = %s",
            (order_id,),
        )
        for event, kwargs in (
            ("payment_changed", {"from_payment": "unpaid", "to_payment": "paid"}),
            ("status_changed", {"from_status": order_status, "to_status": "completed"}),
        ):
            await conn.execute(
                """
                insert into app.order_events (tenant_id, outlet_id, order_id, event, from_status,
                  to_status, from_payment, to_payment, data, actor_type, actor_id)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    ctx.tenant_id,
                    outlet_id,
                    order_id,
                    event,
                    kwargs.get("from_status"),
                    kwargs.get("to_status"),
                    kwargs.get("from_payment"),
                    kwargs.get("to_payment"),
                    Jsonb({"bill_id": str(bill_id), "method": result.method}),
                    ctx.actor_type.value,
                    ctx.actor_id,
                ),
            )
    await conn.execute(
        "update app.bills set status = 'closed', closed_at = now(), closed_by = %s, subtotal = %s,"
        " pb1_rate_bps = %s, pb1_amount = %s, total = %s where id = %s",
        (
            ctx.user_id,
            totals.subtotal,
            totals.pb1_rate_bps,
            totals.pb1_amount,
            totals.total,
            bill_id,
        ),
    )
    return {
        "bill_id": bill_id,
        "total": totals.total,
        "method": result.method,
        "change_due": result.change_due,
        "orders_completed": len(orders),
    }
