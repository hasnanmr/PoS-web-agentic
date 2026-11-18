"""Order service (T-025, T-026, T-028, T-030 to T-032): one code path for every channel.

`create_order` checks stock and deducts every ingredient (items + add-ons) in the same
transaction as the order rows; the stock trigger's row lock plus the on_hand >= 0 check
make the last portion go to exactly one order (FR4.6, AC2.10). The counter (S1) is the
first caller; WhatsApp and the Phase 2 agent call the same function later.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core import bills as bills_core
from app.core import order_flow, payments, stock
from app.core.actor import ActorContext
from app.core.errors import ConflictError, DomainError, NotFoundError, ValidationFailedError
from app.core.localtime import local_date, local_day_bounds
from app.core.pricing import LineInput, PricedLine, PricedOrder, quote
from app.core.units import NegativeQuantityError, recipe_with_addons, scale_recipe

OrderType = Literal["dine_in", "takeaway", "delivery", "pickup"]
Channel = Literal["counter", "whatsapp_online", "whatsapp_table"]


class SoldOutError(DomainError):
    status_code = 409

    def __init__(self, product_id: UUID, name: str) -> None:
        super().__init__(
            "item_sold_out", f"{name} habis", {"product_id": str(product_id), "name": name}
        )


def order_label(prefix: str, number: int) -> str:
    return f"#{prefix}-{number}"


# Stock -------------------------------------------------------------------------------


async def _line_requirements(
    conn: AsyncConnection, lines: tuple[PricedLine, ...]
) -> list[dict[UUID, Decimal]]:
    recipes = await stock.load_recipes(conn)
    out = []
    for line in lines:
        base = recipes.products.get(line.product_id, {})
        if not base:
            raise SoldOutError(line.product_id, line.name)  # no recipe → cannot be sold
        deltas = [recipes.options.get(a.option_id, {}) for a in line.addons]
        try:
            portion = recipe_with_addons(base, deltas)
        except NegativeQuantityError:
            raise SoldOutError(line.product_id, line.name) from None
        out.append(scale_recipe(portion, line.quantity) if portion else {})
    return out


def _first_short(
    lines: tuple[PricedLine, ...],
    per_line: list[dict[UUID, Decimal]],
    on_hand: dict[UUID, Decimal],
) -> PricedLine | None:
    """The first line whose ingredients (cumulative over the order) exceed what is on hand."""
    total: dict[UUID, Decimal] = defaultdict(Decimal)
    for line, need in zip(lines, per_line, strict=True):
        for sid, qty in need.items():
            total[sid] += qty
            if total[sid] > on_hand.get(sid, Decimal(0)):
                return line
    return None


async def _deduct_stock(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    order_id: UUID,
    lines: tuple[PricedLine, ...],
) -> None:
    per_line = await _line_requirements(conn, lines)
    short = _first_short(lines, per_line, await stock.on_hand(conn, outlet_id))
    if short is not None:
        raise SoldOutError(short.product_id, short.name)
    total: dict[UUID, Decimal] = defaultdict(Decimal)
    for need in per_line:
        for sid, qty in need.items():
            total[sid] += qty
    try:
        async with conn.transaction():  # all-or-nothing: a failure undoes the earlier rows
            for sid, qty in sorted(total.items(), key=lambda kv: str(kv[0])):  # stable lock order
                await conn.execute(
                    "insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type,"
                    " quantity, order_id, actor_type, actor_id) values (%s, %s, %s, 'sale', %s,"
                    " %s, %s, %s)",
                    (
                        ctx.tenant_id,
                        outlet_id,
                        sid,
                        -qty,
                        order_id,
                        ctx.actor_type.value,
                        ctx.actor_id,
                    ),
                )
    except errors.CheckViolation as exc:
        if getattr(exc.diag, "constraint_name", None) != "outlet_stock_on_hand_check":
            raise
        # Another order took stock between the check and the insert. Look at the stock as it
        # is now and name the line that no longer fits (not just the first line).
        short = _first_short(lines, per_line, await stock.on_hand(conn, outlet_id))
        culprit = short or lines[0]
        raise SoldOutError(culprit.product_id, culprit.name) from None


async def _return_stock(
    conn: AsyncConnection, ctx: ActorContext, order: dict[str, Any], *, as_waste: bool
) -> None:
    """Undo the order's sale movements. `as_waste` keeps the stock out but records it as
    waste (prepared food), so history shows why it is gone."""
    cur = await conn.execute(
        "select stock_item_id, -sum(quantity) from app.stock_movements"
        " where order_id = %s and type in ('sale', 'sale_reversal') group by stock_item_id"
        " having sum(quantity) < 0 order by stock_item_id",  # same lock order as _deduct_stock
        (order["id"],),
    )
    for sid, qty in await cur.fetchall():
        await conn.execute(
            "insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity,"
            " order_id, note, actor_type, actor_id) values (%s, %s, %s, 'sale_reversal', %s, %s,"
            " %s, %s, %s)",
            (
                ctx.tenant_id,
                order["outlet_id"],
                sid,
                qty,
                order["id"],
                ctx.reason,
                ctx.actor_type.value,
                ctx.actor_id,
            ),
        )
        if as_waste:
            await conn.execute(
                "insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type,"
                " quantity, order_id, note, actor_type, actor_id) values (%s, %s, %s, 'waste',"
                " %s, %s, %s, %s, %s)",
                (
                    ctx.tenant_id,
                    order["outlet_id"],
                    sid,
                    -qty,
                    order["id"],
                    "reversal: sudah diprepare",
                    ctx.actor_type.value,
                    ctx.actor_id,
                ),
            )


# Events ------------------------------------------------------------------------------


async def _event(
    conn: AsyncConnection,
    ctx: ActorContext,
    order: dict[str, Any],
    event: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    from_payment: str | None = None,
    to_payment: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    await conn.execute(
        """
        insert into app.order_events (tenant_id, outlet_id, order_id, event, from_status,
          to_status, from_payment, to_payment, reason, data, actor_type, actor_id)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            ctx.tenant_id,
            order["outlet_id"],
            order["id"],
            event,
            from_status,
            to_status,
            from_payment,
            to_payment,
            ctx.reason,
            Jsonb(data or {}),
            ctx.actor_type.value,
            ctx.actor_id,
        ),
    )


# Create ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CounterOrder:
    type: Literal["dine_in", "takeaway"]
    lines: list[LineInput]
    table_id: UUID | None = None
    payment: payments.PaymentInput | None = None
    to_open_bill: bool = False


async def _outlet(conn: AsyncConnection, outlet_id: UUID) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, order_prefix, payment_mode::text as payment_mode, timezone"
        " from app.outlets where id = %s and is_active",
        (outlet_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("outlet")
    return row


async def _check_table(conn: AsyncConnection, outlet_id: UUID, table_id: UUID | None) -> None:
    if table_id is None:
        return
    cur = await conn.execute(
        "select 1 from app.tables where id = %s and outlet_id = %s and is_active",
        (table_id, outlet_id),
    )
    if await cur.fetchone() is None:
        raise ValidationFailedError("unknown table", {"field": "table_id"})


async def create_counter_order(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, draft: CounterOrder
) -> dict[str, Any]:
    """S1 "Buat order & terima bayar": dine-in at an open-bill outlet goes onto the table's
    bill (opened if needed); everything else is paid now (cash or QRIS)."""
    outlet = await _outlet(conn, outlet_id)
    if draft.type == "takeaway" and draft.table_id is not None:
        raise ValidationFailedError("a takeaway order has no table", {"field": "table_id"})
    await _check_table(conn, outlet_id, draft.table_id)
    open_bill_flow = draft.type == "dine_in" and outlet["payment_mode"] == "open_bill"
    if open_bill_flow:
        if not draft.to_open_bill or draft.payment is not None:
            raise ValidationFailedError(
                "dine-in at an open-bill outlet goes to the table's bill",
                {"field": "payment"},
            )
        if draft.table_id is None:
            raise ValidationFailedError("choose a table for the open bill", {"field": "table_id"})
    else:
        if draft.to_open_bill:
            raise ValidationFailedError("this order must be paid now", {"field": "payment"})
        if draft.payment is None:
            raise ValidationFailedError("choose a payment method", {"field": "payment"})

    priced = await quote(conn, outlet_id, draft.lines)
    bill_id = None
    if open_bill_flow:
        assert draft.table_id is not None  # noqa: S101
        bill_id = await bills_core.open_bill_for_table(conn, ctx, outlet_id, draft.table_id)

    order = await _insert_order(
        conn,
        ctx,
        outlet,
        priced,
        channel="counter",
        type=draft.type,
        table_id=draft.table_id,
        bill_id=bill_id,
        payment_mode=outlet["payment_mode"] if draft.type == "dine_in" else "pay_first",
        status="confirmed",
    )
    change = None
    if draft.payment is not None:
        result = await payments.capture(
            conn,
            ctx,
            outlet_id,
            draft.payment,
            amount=priced.quote.total,
            subtotal=priced.quote.subtotal,
            pb1_amount=priced.quote.pb1_amount,
            order_id=order["id"],
        )
        await mark_paid(
            conn,
            ctx,
            order,
            from_payment="unpaid",
            data={
                "method": result.method,
                "amount": result.amount,
                "cash_received": draft.payment.cash_received,
            },
        )
        change = result.change_due
    return {
        "id": order["id"],
        "order_no": order_label(outlet["order_prefix"], order["order_no"]),
        "status": order["status"],
        "payment_status": order["payment_status"],
        "subtotal": priced.quote.subtotal,
        "pb1_amount": priced.quote.pb1_amount,
        "total": priced.quote.total,
        "change_due": change,
        "bill_id": bill_id,
    }


async def _insert_order(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet: dict[str, Any],
    priced: PricedOrder,
    *,
    channel: Channel,
    type: OrderType,
    table_id: UUID | None,
    bill_id: UUID | None,
    payment_mode: str,
    status: str,
) -> dict[str, Any]:
    order_id = uuid4()
    cur = await conn.execute("select app.next_order_no(%s)", (outlet["id"],))
    order_no = (await cur.fetchone())[0]  # type: ignore[index]
    q = priced.quote
    await conn.execute(
        """
        insert into app.orders (id, tenant_id, outlet_id, order_no, channel, type, payment_mode,
          status, table_id, bill_id, subtotal, pb1_rate_bps, pb1_amount, delivery_fee, total,
          created_by_actor, created_by_id)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            order_id,
            ctx.tenant_id,
            outlet["id"],
            order_no,
            channel,
            type,
            payment_mode,
            status,
            table_id,
            bill_id,
            q.subtotal,
            q.pb1_rate_bps,
            q.pb1_amount,
            q.delivery_fee,
            q.total,
            ctx.actor_type.value,
            ctx.actor_id,
        ),
    )
    for line in priced.lines:
        item_id = uuid4()
        await conn.execute(
            "insert into app.order_items (id, tenant_id, outlet_id, order_id, product_id, name,"
            " unit_price, quantity, line_total, note) values (%s, %s, %s, %s, %s, %s, %s, %s, %s,"
            " %s)",
            (
                item_id,
                ctx.tenant_id,
                outlet["id"],
                order_id,
                line.product_id,
                line.name,
                line.unit_price,
                line.quantity,
                line.line_total,
                line.note,
            ),
        )
        for addon in line.addons:
            await conn.execute(
                "insert into app.order_item_addons (tenant_id, order_item_id, addon_option_id,"
                " name, price) values (%s, %s, %s, %s, %s)",
                (ctx.tenant_id, item_id, addon.option_id, addon.name, addon.price),
            )
    order = {
        "id": order_id,
        "outlet_id": outlet["id"],
        "order_no": order_no,
        "status": status,
        "payment_status": "unpaid",
    }
    await _deduct_stock(conn, ctx, outlet["id"], order_id, priced.lines)
    await _event(
        conn,
        ctx,
        order,
        "created",
        to_status=status,
        data={"channel": channel, "type": type, "total": q.total},
    )
    return order


# Status changes ------------------------------------------------------------------------


_ORDER_SELECT = """
select o.id, o.outlet_id, o.order_no, o.channel::text as channel, o.type::text as type,
       o.payment_mode::text as payment_mode, o.status::text as status,
       o.payment_status::text as payment_status, o.table_id, o.bill_id, o.subtotal,
       o.pb1_rate_bps, o.pb1_amount, o.delivery_fee, o.total, o.created_at,
       ou.order_prefix, ou.timezone, t.name as table_name, b.guest_name
from app.orders o
join app.outlets ou on ou.id = o.outlet_id
left join app.tables t on t.id = o.table_id
left join app.bills b on b.id = o.bill_id
"""
_ORDER_SQL = _ORDER_SELECT + "where o.id = %s"


async def _load(conn: AsyncConnection, order_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    if lock:
        await cur.execute("select 1 from app.orders where id = %s for update", (order_id,))
    await cur.execute(_ORDER_SQL, (order_id,))
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("order")
    return row


FINAL_STATUSES = order_flow.FINAL


async def load_for_update(conn: AsyncConnection, order_id: UUID) -> dict[str, Any]:
    """The order row (with outlet prefix and time zone), locked for a payment decision."""
    return await _load(conn, order_id, lock=True)


async def mark_paid(
    conn: AsyncConnection,
    ctx: ActorContext,
    order: dict[str, Any],
    *,
    from_payment: str,
    data: dict[str, Any],
) -> None:
    """Payment confirmed (the ledger was posted by `payments.capture`). An order waiting for
    payment (pay-first, online) becomes `confirmed` at the same moment (glossary §5)."""
    await conn.execute(
        "update app.orders set payment_status = 'paid',"
        " status = case when status = 'pending_payment' then 'confirmed' else status end"
        " where id = %s",
        (order["id"],),
    )
    await _event(
        conn, ctx, order, "payment_changed", from_payment=from_payment, to_payment="paid", data=data
    )
    if order["status"] == "pending_payment":
        await _event(
            conn, ctx, order, "status_changed", from_status="pending_payment", to_status="confirmed"
        )
        order["status"] = "confirmed"
    order["payment_status"] = "paid"


async def cancel_rejected_proof(
    conn: AsyncConnection, ctx: ActorContext, order: dict[str, Any], proof_id: UUID
) -> None:
    """S4 rejection: cancelled at once, payment back to `unpaid`, stock returned, no ledger.
    `ctx.reason` carries the rejection reason (required on the event)."""
    await _return_stock(conn, ctx, order, as_waste=False)
    await conn.execute(
        "update app.orders set status = 'cancelled', payment_status = 'unpaid' where id = %s",
        (order["id"],),
    )
    await _event(
        conn,
        ctx,
        order,
        "proof_rejected",
        from_status=order["status"],
        to_status="cancelled",
        from_payment="proof_submitted",
        to_payment="unpaid",
        data={"proof_id": str(proof_id), "stock": "returned"},
    )


async def transition(
    conn: AsyncConnection, ctx: ActorContext, order_id: UUID, to_status: str
) -> dict[str, Any]:
    order = await _load(conn, order_id, lock=True)
    if to_status not in order_flow.next_statuses(order):
        raise ConflictError(
            "invalid_transition",
            f"cannot move from {order['status']} to {to_status}",
            {
                "from": order["status"],
                "to": to_status,
                "allowed_actions": order_flow.allowed_actions(order),
            },
        )
    await conn.execute("update app.orders set status = %s where id = %s", (to_status, order_id))
    await _event(
        conn, ctx, order, "status_changed", from_status=order["status"], to_status=to_status
    )
    return await detail(conn, order_id)


async def cancel(
    conn: AsyncConnection, ctx: ActorContext, order_id: UUID, reason: str | None
) -> dict[str, Any]:
    """Cancel an unpaid order: stock returns (S3 "Batalkan")."""
    order = await _load(conn, order_id, lock=True)
    if "cancel" not in order_flow.allowed_actions(order):
        raise ConflictError(
            "invalid_transition",
            "only unpaid open orders can be cancelled; use reversal",
            {"allowed_actions": order_flow.allowed_actions(order)},
        )
    ctx = ctx.with_reason(reason) if reason and reason.strip() else ctx
    await _return_stock(conn, ctx, order, as_waste=False)
    await conn.execute("update app.orders set status = 'cancelled' where id = %s", (order_id,))
    await _event(
        conn,
        ctx,
        order,
        "status_changed",
        from_status=order["status"],
        to_status="cancelled",
        data={"stock": "returned"},
    )
    if order["bill_id"]:
        await bills_core.void_if_empty(conn, order["bill_id"])
    return await detail(conn, order_id)


async def reverse(
    conn: AsyncConnection,
    ctx: ActorContext,
    order_id: UUID,
    reason: str,
    ingredients: Literal["waste", "return"] | None,
) -> dict[str, Any]:
    """Reverse a paid order (S3): reason required, refund ledger entry, stock returned or
    recorded as waste. Money goes back to the customer outside the system."""
    ctx = ctx.with_reason(reason)
    order = await _load(conn, order_id, lock=True)
    if "reversal" not in order_flow.allowed_actions(order):
        raise ConflictError("invalid_transition", "only paid orders can be reversed")
    ingredients = ingredients or order_flow.default_ingredients(order["status"])
    cur = await conn.execute(
        "select method::text from app.payments where order_id = %s or bill_id = %s limit 1",
        (order_id, order["bill_id"]),
    )
    pay = await cur.fetchone()
    method = pay[0] if pay else "cash"
    await _return_stock(conn, ctx, order, as_waste=ingredients == "waste")
    await payments.post_refund(
        conn,
        ctx,
        order["outlet_id"],
        order_id=order_id,
        amount=order["total"],
        pb1_portion=order["pb1_amount"],
        method=method,
    )
    await conn.execute(
        "update app.orders set status = 'cancelled', payment_status = 'refunded' where id = %s",
        (order_id,),
    )
    await _event(
        conn,
        ctx,
        order,
        "reversed",
        from_status=order["status"],
        to_status="cancelled",
        from_payment="paid",
        to_payment="refunded",
        data={"ingredients": ingredients, "refund": order["total"], "method": method},
    )
    result = await detail(conn, order_id)
    result["refund"] = {"amount": order["total"], "method": method}
    return result


# Reads -------------------------------------------------------------------------------------


async def _items(conn: AsyncConnection, order_ids: list[UUID]) -> dict[UUID, list[dict[str, Any]]]:
    if not order_ids:
        return {}
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select i.order_id, i.id, i.product_id, i.name, i.unit_price, i.quantity, i.line_total,
               i.note,
               coalesce(json_agg(json_build_object('name', a.name, 'price', a.price))
                        filter (where a.id is not null), '[]') as addons
        from app.order_items i
        left join app.order_item_addons a on a.order_item_id = i.id
        where i.order_id = any(%s)
        group by i.id order by i.name
        """,
        (order_ids,),
    )
    out: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for r in await cur.fetchall():
        out[r.pop("order_id")].append(r)
    return out


async def _payment_methods(
    conn: AsyncConnection, orders: list[dict[str, Any]]
) -> dict[UUID, dict[str, Any]]:
    """Per order: the payment that settled it (its own, or its bill's), with whether a QRIS
    payment has been cross-checked against the receiving account (S2 "Cek →"). A QRIS
    payment accepted from a proof in S4 was checked there."""
    ids = [o["id"] for o in orders]
    bill_ids = [o["bill_id"] for o in orders if o["bill_id"]]
    cur = await conn.execute(
        """
        select p.order_id, p.bill_id, p.id, p.method::text,
               c.payment_id is not null
                 or exists (select 1 from app.payment_proofs pp
                            where pp.order_id = p.order_id and pp.status = 'accepted')
        from app.payments p
        left join app.qris_checks c on c.payment_id = p.id
        where p.order_id = any(%s) or p.bill_id = any(%s)
        """,
        (ids, bill_ids),
    )
    by_order: dict[UUID, dict[str, Any]] = {}
    by_bill: dict[UUID, dict[str, Any]] = {}
    for order_id, bill_id, payment_id, method, checked in await cur.fetchall():
        info = {"payment_id": payment_id, "method": method, "checked": bool(checked)}
        if order_id:
            by_order[order_id] = info
        else:
            by_bill[bill_id] = info
    return {o["id"]: by_order.get(o["id"]) or by_bill.get(o["bill_id"]) for o in orders}  # type: ignore[misc]


def _summary(items: list[dict[str, Any]]) -> str:
    return ", ".join(f"{i['quantity']}× {i['name']}" for i in items)  # noqa: RUF001 - S2 copy


async def detail(conn: AsyncConnection, order_id: UUID) -> dict[str, Any]:
    order = await _load(conn, order_id)
    items = (await _items(conn, [order_id])).get(order_id, [])
    payment = (await _payment_methods(conn, [order])).get(order_id)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select e.created_at as at, e.event as kind, e.from_status::text as "from",
               e.to_status::text as "to", e.from_payment::text as from_payment,
               e.to_payment::text as to_payment, e.reason, e.data,
               e.actor_type::text as actor_type, u.display_name as actor_name,
               u.role::text as actor_role
        from app.order_events e left join app.users u on u.id = e.actor_id
        where e.order_id = %s order by e.id
        """,
        (order_id,),
    )
    events = await cur.fetchall()
    for e in events:
        e["actor"] = {
            "type": e.pop("actor_type"),
            "name": e.pop("actor_name"),
            "role": e.pop("actor_role"),
        }
    return {
        **_card(order, items, payment),
        "items": items,
        "subtotal": order["subtotal"],
        "pb1_rate_bps": order["pb1_rate_bps"],
        "pb1_amount": order["pb1_amount"],
        "delivery_fee": order["delivery_fee"],
        "timezone": order["timezone"],
        "events": events,
    }


def _card(
    order: dict[str, Any], items: list[dict[str, Any]], payment: dict[str, Any] | None
) -> dict[str, Any]:
    method = payment["method"] if payment else None
    # Only a paid QRIS order still waiting for the cross-check offers "qris_check".
    qris_checked = (
        payment["checked"]
        if payment and method == "qris" and order["payment_status"] == "paid"
        else None
    )
    order = {**order, "qris_unchecked": qris_checked is False}
    return {
        "id": order["id"],
        "order_no": order_label(order["order_prefix"], order["order_no"]),
        "channel": order["channel"],
        "type": order["type"],
        "payment_mode": order["payment_mode"],
        "status": order["status"],
        "payment_status": order["payment_status"],
        "payment_method": method,
        "payment_id": payment["payment_id"] if payment else None,
        "qris_checked": qris_checked,
        "table": order["table_name"],
        "customer_name": order.get("guest_name"),
        "item_summary": _summary(items),
        "total": order["total"],
        "bill_id": order["bill_id"],
        "created_at": order["created_at"],
        "auto_cancel_at": None,  # unpaid timeout (T-034) arrives with WhatsApp ordering
        "allowed_actions": order_flow.allowed_actions(order),
    }


BOARD_COLUMNS = ("awaiting_payment", "confirmed", "preparing", "ready", "done_today")


def _column(order: dict[str, Any]) -> str:
    status = order["status"]
    if status == "pending_payment":
        return "awaiting_payment"
    if status in ("ready", "out_for_delivery", "served"):
        return "ready"
    if status in ("completed", "cancelled"):
        return "done_today"
    return status


async def board(
    conn: AsyncConnection,
    outlet_id: UUID,
    *,
    channel: str | None = None,
    type: str | None = None,
    q: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """S2: active orders by column, plus orders finished today (outlet-local day)."""
    cur = await conn.execute("select timezone from app.outlets where id = %s", (outlet_id,))
    tz = (await cur.fetchone())[0]  # type: ignore[index]
    start, _ = local_day_bounds(local_date(datetime.now(UTC), tz), tz)
    dcur = conn.cursor(row_factory=dict_row)
    await dcur.execute(
        _ORDER_SELECT
        + """
        where o.outlet_id = %s
          and (o.status not in ('completed', 'cancelled') or o.updated_at >= %s)
          and (%s::text is null or o.channel::text = %s)
          and (%s::text is null or o.type::text = %s)
        order by o.created_at
        """,
        (outlet_id, start, channel, channel, type, type),
    )
    orders = await dcur.fetchall()
    items = await _items(conn, [o["id"] for o in orders])
    methods = await _payment_methods(conn, orders) if orders else {}
    needle = (q or "").strip().lower().lstrip("#")
    columns: dict[str, list[dict[str, Any]]] = {c: [] for c in BOARD_COLUMNS}
    for o in orders:
        card = _card(o, items.get(o["id"], []), methods.get(o["id"]))
        haystack = f"{card['order_no']} {card['table'] or ''} {card['customer_name'] or ''}".lower()
        if needle and needle not in haystack:
            continue
        columns[_column(o)].append(card)
    columns["done_today"].reverse()
    return columns
