"""Purchase orders and supplier payments (T-125 to T-127) — glossary §7a.

Screens: O15 (owner list, detail, suppliers), O16/S12 (Buka PO), S10 (staff list), S11 (goods
cross-check), O17 (dashboard cards, T-128). Contract: docs/architecture/screen-endpoint-map.md.

Flow:
- Scheme 1, pay later: open → goods checked against the PO → closed → paid (instalments).
- Scheme 2, pay in advance: open → paid in full → goods checked → closed (not while unpaid).

Cash basis: opening, checking and closing never post to the ledger. Each payment posts one
`expense` entry (negative) on the payment date with the PO number and supplier. A cash payment
may come out of an open shift's drawer and then lowers that shift's expected cash.

Status: `open` until a line is short; `difference_found` while a received line is short;
`closed` by owner or staff when every line matches, or by the owner alone with a note when a
line stays short (pay later: amount owed becomes received x unit price); `cancelled` only with
no payment and no goods. Closed and cancelled POs never reopen.
"""

from __future__ import annotations

import base64
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row

from app.core import ledger, shifts
from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.units import to_quantity

PaymentTerm = Literal["pay_later", "pay_in_advance"]
ListFilter = Literal["open", "difference_found", "awaiting_payment", "overdue", "closed"]
# O17 Ringkasan PO drill-down (FR3.12): each figure lists exactly its POs.
StateFilter = Literal["open", "closed"]
GoodsFilter = Literal["not_arrived", "partly_arrived", "arrived"]
PaymentFilter = Literal["unpaid", "partially_paid", "paid"]
Viewer = Literal["owner", "staff"]

MAX_LINES = 50
MAX_AMOUNT = 1_000_000_000
# Base units per display unit for stock lines; free-text lines take any short unit.
UNIT_FACTOR: dict[str, dict[str, int]] = {
    "g": {"g": 1, "kg": 1000},
    "ml": {"ml": 1, "L": 1000},
    "pcs": {"pcs": 1},
}


def po_label(prefix: str, po_no: int) -> str:
    """`PO-A-0012`: the outlet's order prefix and a 4-digit per-outlet number."""
    return f"PO-{prefix}-{po_no:04d}"


def line_subtotal(quantity: Decimal, unit_price: int) -> int:
    """Whole rupiah, half up (money rule: integers, no fractional rupiah)."""
    return int((quantity * unit_price).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# Suppliers (O15 "Daftar supplier", owner; S12 dropdown, staff read-only) ----------------------


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


async def list_suppliers(conn: AsyncConnection, *, active_only: bool) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, name, phone, note, is_active from app.suppliers"
        " where (not %s or is_active) order by lower(name)",
        (active_only,),
    )
    return await cur.fetchall()


async def create_supplier(
    conn: AsyncConnection, ctx: ActorContext, *, name: str, phone: str | None, note: str | None
) -> dict[str, Any]:
    clean = _clean(name)
    if clean is None:
        raise ValidationFailedError("enter the supplier name", {"field": "name"})
    cur = conn.cursor(row_factory=dict_row)
    try:
        async with conn.transaction():
            await cur.execute(
                "insert into app.suppliers (tenant_id, name, phone, note) values (%s, %s, %s, %s)"
                " returning id, name, phone, note, is_active",
                (ctx.tenant_id, clean, _clean(phone), _clean(note)),
            )
            row = await cur.fetchone()
    except errors.UniqueViolation:
        raise ConflictError("supplier_exists", "a supplier with this name already exists") from None
    assert row is not None  # noqa: S101
    await record_audit(
        conn, ctx, action="supplier.created", entity_type="supplier", entity_id=row["id"]
    )
    return row


async def update_supplier(
    conn: AsyncConnection, ctx: ActorContext, supplier_id: UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    if "name" in changes:
        changes["name"] = _clean(changes["name"])
        if changes["name"] is None:
            raise ValidationFailedError("enter the supplier name", {"field": "name"})
    for key in ("phone", "note"):
        if key in changes:
            changes[key] = _clean(changes[key])
    cur = conn.cursor(row_factory=dict_row)
    sets = ", ".join(f"{k} = %({k})s" for k in changes) or "name = name"
    try:
        async with conn.transaction():
            await cur.execute(
                f"update app.suppliers set {sets} where id = %(id)s"  # noqa: S608 (fixed keys)
                " returning id, name, phone, note, is_active",
                {**changes, "id": supplier_id},
            )
            row = await cur.fetchone()
    except errors.UniqueViolation:
        raise ConflictError("supplier_exists", "a supplier with this name already exists") from None
    if row is None:
        raise NotFoundError("supplier")
    await record_audit(
        conn,
        ctx,
        action="supplier.updated",
        entity_type="supplier",
        entity_id=supplier_id,
        data={"fields": sorted(changes)},
    )
    return row


# Reading ---------------------------------------------------------------------------------------

_ROW_SELECT = """
select p.id, p.po_no, ou.order_prefix, p.outlet_id, ou.name as outlet_name, ou.timezone,
       p.supplier_id, s.name as supplier_name, p.payment_term::text as payment_term,
       p.ordered_on, p.due_date, p.expected_date, p.status::text as status,
       p.payment_status::text as payment_status, p.total, p.amount_payable, p.amount_paid,
       p.note, p.created_at, p.created_by, cu.display_name as created_by_name,
       p.closed_at, p.close_note, p.cancelled_at, p.cancel_reason,
       (timezone(ou.timezone, now()))::date as local_today,
       coalesce(g.lines, 0) as line_count, coalesce(g.received_lines, 0) as received_lines,
       coalesce(g.full_lines, 0) as full_lines
from app.purchase_orders p
join app.outlets ou on ou.id = p.outlet_id
join app.suppliers s on s.id = p.supplier_id
join app.users cu on cu.id = p.created_by
"""
# Per-PO line counts `g` behind goods_status (Python) and _GOODS (SQL); see _ROW_SELECT.
_LINE_COUNTS = """
left join lateral (
  select count(*) as lines,
         count(*) filter (where l.received_quantity > 0) as received_lines,
         count(*) filter (where l.received_quantity = l.quantity) as full_lines
  from app.purchase_order_lines l where l.purchase_order_id = p.id
) g on true
"""
_ROW_SELECT += _LINE_COUNTS

# "Menunggu bayar" (O15 chip) and the O17 Pembayaran supplier card: closed pay-later POs not
# fully paid, and open pay-in-advance POs not paid yet (US-058, US-059).
_AWAITING_PAYMENT = """
  p.status <> 'cancelled' and p.payment_status <> 'paid'
  and ((p.payment_term = 'pay_later' and p.status = 'closed')
       or (p.payment_term = 'pay_in_advance' and p.status <> 'closed'))
"""
# Overdue (FR3.7): a closed pay-later PO — its payment reminder is showing — not fully paid and
# past the due date in the outlet's time zone. A subset of _AWAITING_PAYMENT, so the O15 chip, the
# row badge and the O17 Pembayaran supplier card always agree. `now()` is the transaction start,
# so every query of one request sees the same "today".
_OVERDUE = """
  p.status = 'closed' and p.payment_term = 'pay_later' and p.payment_status <> 'paid'
  and p.due_date < (timezone(ou.timezone, now()))::date
"""
_FILTERS: dict[str, str] = {
    "open": "p.status = 'open'",
    "difference_found": "p.status = 'difference_found'",
    "awaiting_payment": _AWAITING_PAYMENT,
    "overdue": _OVERDUE,
    "closed": "p.status = 'closed'",
}
# Ringkasan PO buckets (cancelled POs are never counted). "Dibuka" = not closed yet, with or
# without a difference (AC3.14).
_STATE: dict[str, str] = {
    "open": "p.status in ('open', 'difference_found')",
    "closed": "p.status = 'closed'",
}
_GOODS: dict[str, str] = {
    "arrived": "coalesce(g.lines, 0) > 0 and g.full_lines = g.lines",
    "partly_arrived": "coalesce(g.received_lines, 0) > 0 and g.full_lines < g.lines",
    "not_arrived": "coalesce(g.received_lines, 0) = 0",
}


def month_bounds(month: str) -> tuple[date, date]:
    """`2026-11` → (1 Nov, 1 Dec): PO open dates are outlet-local, so no zone math here."""
    try:
        year, mon = (int(part) for part in month.split("-"))
        return date(year, mon, 1), date(year + mon // 12, mon % 12 + 1, 1)
    except ValueError:  # bad format, month 13, or past year 9999
        raise ValidationFailedError("use YYYY-MM", {"field": "month"}) from None


def goods_status(row: dict[str, Any]) -> Literal["not_arrived", "partly_arrived", "arrived"]:
    """Python twin of _GOODS (same `g` counts); a test checks both agree."""
    if row["line_count"] and row["full_lines"] == row["line_count"]:
        return "arrived"
    return "partly_arrived" if row["received_lines"] else "not_arrived"


def _overdue(row: dict[str, Any]) -> bool:
    """Python twin of _OVERDUE."""
    return (
        row["status"] == "closed"
        and row["payment_term"] == "pay_later"
        and row["payment_status"] != "paid"
        and row["due_date"] < row["local_today"]
    )


def _owed(row: dict[str, Any]) -> int:
    return 0 if row["status"] == "cancelled" else row["amount_payable"] - row["amount_paid"]


def allowed_actions(row: dict[str, Any], viewer: Viewer) -> list[str]:
    """Buttons the UI may render for this PO and viewer (computed by the server)."""
    status, term = row["status"], row["payment_term"]
    actions: list[str] = []
    if status in ("open", "difference_found"):
        actions.append("receive")
    fully_received = row["line_count"] > 0 and row["full_lines"] == row["line_count"]
    paid_if_needed = term == "pay_later" or row["payment_status"] == "paid"
    if status == "open" and fully_received and paid_if_needed:
        actions.append("close")
    if viewer == "owner":
        if status == "difference_found" and paid_if_needed:
            actions.append("close_with_note")
        if status != "cancelled" and row["payment_status"] != "paid" and _owed(row) > 0:
            actions.append("record_payment")
        if status == "open" and not row["received_lines"] and row["amount_paid"] == 0:
            actions.append("cancel")
    return actions


def _row_out(row: dict[str, Any], viewer: Viewer) -> dict[str, Any]:
    out = {
        "id": row["id"],
        "number": po_label(row["order_prefix"], row["po_no"]),
        "supplier": {"id": row["supplier_id"], "name": row["supplier_name"]},
        "outlet": {"id": row["outlet_id"], "name": row["outlet_name"]},
        "payment_term": row["payment_term"],
        "ordered_on": row["ordered_on"],
        "due_date": row["due_date"],
        "expected_date": row["expected_date"],
        "status": row["status"],
        "goods_status": goods_status(row),
        "payment_status": row["payment_status"],
        "overdue": _overdue(row),
        "total": row["total"],
        "created_at": row["created_at"],
        "created_by": row["created_by_name"],
    }
    if viewer == "owner":  # payments and debt are owner-only (US-061)
        out |= {"amount_paid": row["amount_paid"], "amount_owed": _owed(row)}
    return out


def _encode_cursor(row: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(
        f"{row['created_at'].isoformat()}|{row['id']}".encode()
    ).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        at, po_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(at), UUID(po_id)
    except (ValueError, UnicodeDecodeError):
        raise ValidationFailedError("invalid cursor", {"field": "cursor"}) from None


async def list_pos(
    conn: AsyncConnection,
    viewer: Viewer,
    *,
    outlet_id: UUID | None,
    status: ListFilter | None,
    cursor: str | None,
    limit: int,
    month: str | None = None,
    state: StateFilter | None = None,
    goods: GoodsFilter | None = None,
    payment: PaymentFilter | None = None,
    term: PaymentTerm | None = None,
) -> dict[str, Any]:
    """O15 list (owner, all outlets or one) and S10 list (staff, one outlet). Newest first.
    `month`, `state`, `goods`, `payment` and `term` are the O17 Ringkasan PO drill-down: like
    the report, they never include cancelled POs."""
    after = _decode_cursor(cursor) if cursor else None
    where = ["(%(outlet)s::uuid is null or p.outlet_id = %(outlet)s)"]
    if status:
        where.append(f"({_FILTERS[status]})")
    month_start, month_end = month_bounds(month) if month else (None, None)
    if month or state or goods or payment or term:
        where.append("p.status <> 'cancelled'")
    if month:
        where.append("p.ordered_on >= %(month_start)s and p.ordered_on < %(month_end)s")
    if state:
        where.append(f"({_STATE[state]})")
    if goods:
        where.append(f"({_GOODS[goods]})")
    if payment:
        where.append("p.payment_status = %(payment)s::app.po_payment_status")
    if term:
        where.append("p.payment_term = %(term)s::app.po_payment_term")
    if after:
        where.append("(p.created_at, p.id) < (%(after_at)s, %(after_id)s)")
    order = "p.created_at desc, p.id desc"
    if status in ("awaiting_payment", "overdue"):
        order = "p.due_date nulls last, " + order
        where = [w for w in where if not w.startswith("(p.created_at, p.id)")]
        after = None  # these lists are short; one page, sorted by urgency
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        _ROW_SELECT + " where " + " and ".join(where) + f" order by {order} limit %(limit)s",
        {
            "outlet": outlet_id,
            "month_start": month_start,
            "month_end": month_end,
            "payment": payment,
            "term": term,
            "after_at": after[0] if after else None,
            "after_id": after[1] if after else None,
            "limit": limit + 1 if status not in ("awaiting_payment", "overdue") else 500,
        },
    )
    rows = await cur.fetchall()
    paged = status not in ("awaiting_payment", "overdue")
    more = paged and len(rows) > limit
    rows = rows[:limit] if paged else rows
    return {
        "items": [_row_out(r, viewer) for r in rows],
        "next_cursor": _encode_cursor(rows[-1]) if more and rows else None,
    }


async def _load(conn: AsyncConnection, po_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    if lock:  # serialize receipts, payments, close and cancel on one PO
        await conn.execute("select 1 from app.purchase_orders where id = %s for update", (po_id,))
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(_ROW_SELECT + " where p.id = %s", (po_id,))
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("purchase order")
    return row


async def _lines(conn: AsyncConnection, po_id: UUID) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, line_no, stock_item_id, item_name, quantity, unit, base_factor, unit_price,"
        " subtotal, received_quantity from app.purchase_order_lines"
        " where purchase_order_id = %s order by line_no",
        (po_id,),
    )
    return await cur.fetchall()


def _line_out(line: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": line["id"],
        "item": line["item_name"],
        "stock_item_id": line["stock_item_id"],
        "quantity": line["quantity"],
        "unit": line["unit"],
        "unit_price": line["unit_price"],
        "subtotal": line["subtotal"],
        "received_quantity": line["received_quantity"],
        "remaining_quantity": line["quantity"] - line["received_quantity"],
        "check": "match" if line["received_quantity"] == line["quantity"] else "short",
    }


async def _events(conn: AsyncConnection, row: dict[str, Any], viewer: Viewer) -> list[dict]:
    """Riwayat: opened, each receipt, each payment (owner only), closed, cancelled; oldest first."""
    cur = conn.cursor(row_factory=dict_row)
    events: list[dict[str, Any]] = [
        {
            "at": row["created_at"],
            "kind": "opened",
            "actor": {"name": row["created_by_name"], "role": await _role(conn, row["created_by"])},
            "data": {"total": row["total"]},
        }
    ]
    await cur.execute(
        """
        select r.created_at as at, r.received_on, r.note, u.display_name, u.role::text as role,
               coalesce(jsonb_agg(jsonb_build_object('item', l.item_name, 'quantity', rl.quantity,
                 'unit', l.unit) order by l.line_no), '[]') as lines
        from app.purchase_order_receipts r
        left join app.users u on u.id = r.actor_id
        join app.purchase_order_receipt_lines rl on rl.receipt_id = r.id
        join app.purchase_order_lines l on l.id = rl.line_id
        where r.purchase_order_id = %s
        group by r.id, u.display_name, u.role
        """,
        (row["id"],),
    )
    for r in await cur.fetchall():
        events.append(
            {
                "at": r["at"],
                "kind": "received",
                "actor": {"name": r["display_name"], "role": r["role"]},
                "data": {"received_on": r["received_on"], "note": r["note"], "lines": r["lines"]},
            }
        )
    if viewer == "owner":
        await cur.execute(
            """
            select p.created_at as at, p.paid_on, p.amount, p.method::text as method,
                   p.shift_id is not null as from_drawer, u.display_name, u.role::text as role
            from app.purchase_order_payments p join app.users u on u.id = p.recorded_by
            where p.purchase_order_id = %s
            """,
            (row["id"],),
        )
        for p in await cur.fetchall():
            events.append(
                {
                    "at": p["at"],
                    "kind": "paid",
                    "actor": {"name": p["display_name"], "role": p["role"]},
                    "data": {
                        "paid_on": p["paid_on"],
                        "amount": p["amount"],
                        "method": p["method"],
                        "from_drawer": p["from_drawer"],
                    },
                }
            )
    for kind, at_key, by_col, data in (
        ("closed", "closed_at", "closed_by", {"note": row["close_note"]}),
        ("cancelled", "cancelled_at", "cancelled_by", {"reason": row["cancel_reason"]}),
    ):
        if row[at_key] is None:
            continue
        await cur.execute(
            f"select u.display_name, u.role::text as role from app.purchase_orders p"  # noqa: S608
            f" join app.users u on u.id = p.{by_col} where p.id = %s",
            (row["id"],),
        )
        who = await cur.fetchone() or {"display_name": None, "role": None}
        events.append(
            {
                "at": row[at_key],
                "kind": kind,
                "actor": {"name": who["display_name"], "role": who["role"]},
                "data": data,
            }
        )
    events.sort(key=lambda e: e["at"])
    return events


async def _role(conn: AsyncConnection, user_id: UUID) -> str | None:
    cur = await conn.execute("select role::text from app.users where id = %s", (user_id,))
    found = await cur.fetchone()
    return found[0] if found else None


async def detail(conn: AsyncConnection, po_id: UUID, viewer: Viewer) -> dict[str, Any]:
    """O15 detail (owner) and S11 form (staff): lines, history, and the allowed actions."""
    row = await _load(conn, po_id)
    return {
        **_row_out(row, viewer),
        "note": row["note"],
        "close_note": row["close_note"],
        "cancel_reason": row["cancel_reason"],
        "lines": [_line_out(line) for line in await _lines(conn, po_id)],
        "events": await _events(conn, row, viewer),
        "allowed_actions": allowed_actions(row, viewer),
    }


# Opening (O16 owner / S12 staff) ---------------------------------------------------------------


async def open_po(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet: dict[str, Any],
    *,
    supplier_id: UUID,
    ordered_on: date,
    payment_term: PaymentTerm,
    due_date: date | None,
    expected_date: date | None,
    lines: list[dict[str, Any]],
    note: str | None,
) -> UUID:
    """No approval; the creator is recorded. No ledger entry and no stock change (US-057)."""
    if not 1 <= len(lines) <= MAX_LINES:
        raise ValidationFailedError(f"add 1 to {MAX_LINES} items", {"field": "lines"})
    today = await ledger.today(conn, outlet["id"])
    if ordered_on > today:
        raise ValidationFailedError(
            "the order date cannot be in the future", {"field": "ordered_on"}
        )
    if payment_term == "pay_later":
        if due_date is None or expected_date is not None:
            raise ValidationFailedError("pay later needs a due date", {"field": "due_date"})
        if due_date < ordered_on:
            raise ValidationFailedError(
                "the due date is before the order date", {"field": "due_date"}
            )
    else:
        if expected_date is None or due_date is not None:
            raise ValidationFailedError(
                "pay in advance needs the expected delivery date", {"field": "expected_date"}
            )
        if expected_date < ordered_on:
            raise ValidationFailedError(
                "the delivery date is before the order date", {"field": "expected_date"}
            )
    cur = await conn.execute(
        "select 1 from app.suppliers where id = %s and is_active", (supplier_id,)
    )
    if await cur.fetchone() is None:
        raise ValidationFailedError("choose a supplier", {"field": "supplier_id"})

    prepared = [await _prepare_line(conn, i, line) for i, line in enumerate(lines)]
    total = sum(p["subtotal"] for p in prepared)
    if not 0 < total <= MAX_AMOUNT:
        raise ValidationFailedError("the PO total must be above zero", {"field": "lines"})

    cur = await conn.execute("select app.next_po_no(%s)", (outlet["id"],))
    po_no = (await cur.fetchone())[0]  # type: ignore[index]
    cur = await conn.execute(
        """
        insert into app.purchase_orders (tenant_id, outlet_id, po_no, supplier_id, ordered_on,
          payment_term, due_date, expected_date, note, total, amount_payable, created_by)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id
        """,
        (
            ctx.tenant_id,
            outlet["id"],
            po_no,
            supplier_id,
            ordered_on,
            payment_term,
            due_date,
            expected_date,
            _clean(note),
            total,
            total,
            ctx.user_id,
        ),
    )
    po_id = (await cur.fetchone())[0]  # type: ignore[index]
    for n, p in enumerate(prepared, start=1):
        await conn.execute(
            """
            insert into app.purchase_order_lines (tenant_id, outlet_id, purchase_order_id, line_no,
              stock_item_id, item_name, quantity, unit, base_factor, unit_price, subtotal)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                ctx.tenant_id,
                outlet["id"],
                po_id,
                n,
                p["stock_item_id"],
                p["item_name"],
                p["quantity"],
                p["unit"],
                p["base_factor"],
                p["unit_price"],
                p["subtotal"],
            ),
        )
    await record_audit(
        conn,
        ctx,
        action="po.opened",
        entity_type="purchase_order",
        entity_id=po_id,
        outlet_id=outlet["id"],
        data={"number": po_label(outlet["order_prefix"], po_no), "total": total},
    )
    return po_id


async def _prepare_line(conn: AsyncConnection, index: int, line: dict[str, Any]) -> dict[str, Any]:
    field = f"lines.{index}"
    try:
        quantity = to_quantity(line["quantity"], name="quantity")
    except (TypeError, ValueError):
        raise ValidationFailedError("enter a quantity", {"field": f"{field}.quantity"}) from None
    if quantity <= 0:
        raise ValidationFailedError("enter a quantity above zero", {"field": f"{field}.quantity"})
    unit_price = line["unit_price"]
    if not 0 <= unit_price <= MAX_AMOUNT:
        raise ValidationFailedError("enter the unit price", {"field": f"{field}.unit_price"})
    unit = (line.get("unit") or "").strip()
    stock_item_id = line.get("stock_item_id")
    if stock_item_id is not None:
        cur = await conn.execute(
            "select name, unit::text from app.stock_items where id = %s and is_active",
            (stock_item_id,),
        )
        item = await cur.fetchone()
        if item is None:
            raise ValidationFailedError(
                "this stock item does not exist", {"field": f"{field}.stock_item_id"}
            )
        name, base_unit = item
        factor = UNIT_FACTOR[base_unit].get(unit)
        if factor is None:
            raise ValidationFailedError(
                f"use {' or '.join(UNIT_FACTOR[base_unit])} for {name}",
                {"field": f"{field}.unit"},
            )
    else:
        name = (line.get("item_name") or "").strip()
        if not name:
            raise ValidationFailedError(
                "choose a stock item or type the item", {"field": f"{field}.item_name"}
            )
        if not unit:
            raise ValidationFailedError("enter the unit", {"field": f"{field}.unit"})
        factor = None
    return {
        "stock_item_id": stock_item_id,
        "item_name": name,
        "quantity": quantity,
        "unit": unit,
        "base_factor": factor,
        "unit_price": unit_price,
        "subtotal": line_subtotal(quantity, unit_price),
    }


# Goods check (S11) and close ---------------------------------------------------------------------


async def receive(
    conn: AsyncConnection,
    ctx: ActorContext,
    po_id: UUID,
    *,
    received_on: date,
    note: str | None,
    lines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Record one delivery: received quantity per line (never above what is still missing).
    Stock lines add `restock` movements in base units that reference the PO."""
    row = await _load(conn, po_id, lock=True)
    if row["status"] not in ("open", "difference_found"):
        raise ConflictError("po_not_open", f"this purchase order is {row['status']}")
    if not lines:
        raise ValidationFailedError("enter what arrived", {"field": "lines"})
    if received_on > row["local_today"]:
        raise ValidationFailedError("the date cannot be in the future", {"field": "received_on"})
    if received_on < row["ordered_on"]:
        raise ValidationFailedError("the date is before the order date", {"field": "received_on"})
    by_id = {line["id"]: line for line in await _lines(conn, po_id)}
    seen: set[UUID] = set()
    entries: list[tuple[dict[str, Any], Decimal]] = []
    for i, item in enumerate(lines):
        line = by_id.get(item["line_id"])
        if line is None or item["line_id"] in seen:
            raise ValidationFailedError("unknown PO line", {"field": f"lines.{i}.line_id"})
        seen.add(item["line_id"])
        try:
            qty = to_quantity(item["quantity"], name="quantity")
        except (TypeError, ValueError):
            raise ValidationFailedError(
                "enter a quantity", {"field": f"lines.{i}.quantity"}
            ) from None
        if qty == 0:
            continue
        remaining = line["quantity"] - line["received_quantity"]
        if qty > remaining:
            raise ConflictError(
                "over_receipt",
                "more than the PO still expects for this line",
                {"line_id": str(line["id"]), "remaining": str(remaining)},
            )
        entries.append((line, qty))
    if not entries:
        raise ValidationFailedError("enter what arrived", {"field": "lines"})

    label = po_label(row["order_prefix"], row["po_no"])
    cur = await conn.execute(
        "insert into app.purchase_order_receipts (tenant_id, outlet_id, purchase_order_id,"
        " received_on, note, actor_type, actor_id) values (%s, %s, %s, %s, %s, %s, %s)"
        " returning id",
        (
            ctx.tenant_id,
            row["outlet_id"],
            po_id,
            received_on,
            _clean(note),
            ctx.actor_type.value,
            ctx.actor_id,
        ),
    )
    receipt_id = (await cur.fetchone())[0]  # type: ignore[index]
    for line, qty in entries:
        movement_id = None
        if line["stock_item_id"] is not None:
            cur = await conn.execute(
                """
                insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type,
                  quantity, note, purchase_order_id, actor_type, actor_id)
                values (%s, %s, %s, 'restock', %s, %s, %s, %s, %s) returning id
                """,
                (
                    ctx.tenant_id,
                    row["outlet_id"],
                    line["stock_item_id"],
                    qty * line["base_factor"],
                    label,
                    po_id,
                    ctx.actor_type.value,
                    ctx.actor_id,
                ),
            )
            movement_id = (await cur.fetchone())[0]  # type: ignore[index]
        await conn.execute(
            "insert into app.purchase_order_receipt_lines (tenant_id, outlet_id, receipt_id,"
            " line_id, quantity, stock_movement_id) values (%s, %s, %s, %s, %s, %s)",
            (ctx.tenant_id, row["outlet_id"], receipt_id, line["id"], qty, movement_id),
        )
        await conn.execute(
            "update app.purchase_order_lines set received_quantity = received_quantity + %s"
            " where id = %s",
            (qty, line["id"]),
        )
    after = await _lines(conn, po_id)
    short = any(line["received_quantity"] < line["quantity"] for line in after)
    status = "difference_found" if short else "open"
    if status != row["status"]:
        await conn.execute(
            "update app.purchase_orders set status = %s where id = %s", (status, po_id)
        )
    await record_audit(
        conn,
        ctx,
        action="po.received",
        entity_type="purchase_order",
        entity_id=po_id,
        outlet_id=row["outlet_id"],
        data={"receipt_id": str(receipt_id), "lines": len(entries)},
    )
    return {"receipt_id": receipt_id, "status": status}


async def close(
    conn: AsyncConnection, ctx: ActorContext, po_id: UUID, *, note: str | None, viewer: Viewer
) -> None:
    """Without a note: owner or staff, only when every line matches (S11 "Tutup PO").
    With a note: owner only, for a PO with a difference (O15/O17 "Tutup dengan catatan");
    a pay-later PO then owes received x unit price."""
    row = await _load(conn, po_id, lock=True)
    if row["status"] in ("closed", "cancelled"):
        raise ConflictError("po_not_open", f"this purchase order is {row['status']}")
    if row["payment_term"] == "pay_in_advance" and row["payment_status"] != "paid":
        raise ConflictError("payment_required", "record the payment before closing this PO")
    clean_note = _clean(note)
    payable = row["amount_payable"]
    if clean_note is None:
        if row["status"] == "difference_found":
            raise ConflictError(
                "difference_found",
                "some items are short; only the owner can close this PO with a note",
            )
        if row["full_lines"] != row["line_count"]:
            raise ConflictError("goods_not_received", "check the goods before closing this PO")
    else:
        if viewer != "owner":
            raise ConflictError("owner_only", "only the owner can close a PO with a note")
        if row["status"] != "difference_found":
            raise ConflictError("no_difference", "close this PO without a note")
        if row["payment_term"] == "pay_later":
            payable = sum(
                line_subtotal(line["received_quantity"], line["unit_price"])
                for line in await _lines(conn, po_id)
            )
            if payable < row["amount_paid"]:
                raise ConflictError(
                    "paid_above_received",
                    "more was paid than the goods received are worth",
                    {"amount_paid": row["amount_paid"], "received_value": payable},
                )
    payment_status = _payment_status(row["amount_paid"], payable)
    await conn.execute(
        """
        update app.purchase_orders
        set status = 'closed', closed_at = now(), closed_by = %s, close_note = %s,
            amount_payable = %s, payment_status = %s
        where id = %s
        """,
        (ctx.user_id, clean_note, payable, payment_status, po_id),
    )
    await record_audit(
        conn,
        ctx,
        action="po.closed",
        entity_type="purchase_order",
        entity_id=po_id,
        outlet_id=row["outlet_id"],
        data={"with_note": clean_note is not None, "amount_payable": payable},
    )


def _payment_status(paid: int, payable: int) -> str:
    if paid >= payable:
        return "paid"
    return "partially_paid" if paid else "unpaid"


async def cancel(conn: AsyncConnection, ctx: ActorContext, po_id: UUID, reason: str) -> None:
    """Owner only; reason required; refused once paid or any goods were received."""
    text = (reason or "").strip()
    if not text:
        raise ValidationFailedError("a reason is required", {"field": "reason"})
    row = await _load(conn, po_id, lock=True)
    if "cancel" not in allowed_actions(row, "owner"):
        raise ConflictError(
            "not_cancellable", "a PO that is paid, received, or closed cannot be cancelled"
        )
    await conn.execute(
        "update app.purchase_orders set status = 'cancelled', cancelled_at = now(),"
        " cancelled_by = %s, cancel_reason = %s where id = %s",
        (ctx.user_id, text, po_id),
    )
    await record_audit(
        conn,
        ctx.with_reason(text),
        action="po.cancelled",
        entity_type="purchase_order",
        entity_id=po_id,
        outlet_id=row["outlet_id"],
    )


# Payments (owner, "Catat pembayaran")


async def record_payment(
    conn: AsyncConnection,
    ctx: ActorContext,
    po_id: UUID,
    *,
    paid_on: date,
    amount: int,
    method: Literal["cash", "transfer"],
    drawer_id: UUID | None,
) -> dict[str, Any]:
    """Pay later: instalments, never above what is owed. Pay in advance: the full amount at
    once. Posts one `expense` ledger entry on `paid_on`. Cash with a drawer comes out of that
    drawer's open shift (its expected cash drops); otherwise it was paid outside the drawer."""
    row = await _load(conn, po_id, lock=True)
    if row["status"] == "cancelled":
        raise ConflictError("po_cancelled", "this purchase order was cancelled")
    owed = _owed(row)
    if owed <= 0:
        raise ConflictError("already_paid", "this purchase order is fully paid")
    if not 0 < amount <= MAX_AMOUNT:
        raise ValidationFailedError("enter an amount above zero", {"field": "amount"})
    if amount > owed:
        raise ConflictError(
            "overpayment", "the amount is more than what is still owed", {"amount_owed": owed}
        )
    if row["payment_term"] == "pay_in_advance" and amount != owed:
        raise ValidationFailedError(
            "pay in advance is paid in full", {"field": "amount", "amount_owed": owed}
        )
    if paid_on > row["local_today"]:
        raise ValidationFailedError("the date cannot be in the future", {"field": "paid_on"})
    if paid_on < row["ordered_on"]:
        raise ValidationFailedError("the date is before the order date", {"field": "paid_on"})
    shift_id = None
    if drawer_id is not None:
        if method != "cash":
            raise ValidationFailedError("only cash comes out of a drawer", {"field": "drawer_id"})
        shift_id = await shifts.shift_for_cash(conn, ctx, row["outlet_id"], drawer_id)
    label = po_label(row["order_prefix"], row["po_no"])
    entry_id = await ledger.post(
        conn,
        ctx,
        row["outlet_id"],
        "expense",
        -amount,
        method,  # type: ignore[arg-type]
        paid_on,
        shift_id=shift_id,
        description=f"{label} · {row['supplier_name']}"[: ledger.DESCRIPTION_MAX],
        purchase_order_id=po_id,
    )
    cur = await conn.execute(
        "insert into app.purchase_order_payments (tenant_id, outlet_id, purchase_order_id,"
        " paid_on, amount, method, shift_id, ledger_entry_id, recorded_by)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
        (
            ctx.tenant_id,
            row["outlet_id"],
            po_id,
            paid_on,
            amount,
            method,
            shift_id,
            entry_id,
            ctx.user_id,
        ),
    )
    payment_id = (await cur.fetchone())[0]  # type: ignore[index]
    paid = row["amount_paid"] + amount
    await conn.execute(
        "update app.purchase_orders set amount_paid = %s, payment_status = %s where id = %s",
        (paid, _payment_status(paid, row["amount_payable"]), po_id),
    )
    await record_audit(
        conn,
        ctx,
        action="po.payment_recorded",
        entity_type="purchase_order",
        entity_id=po_id,
        outlet_id=row["outlet_id"],
        data={"amount": amount, "method": method, "shift_id": str(shift_id) if shift_id else None},
    )
    return {"payment_id": payment_id, "ledger_entry_id": entry_id}


# Dashboard tab "PO & Supplier" — O17 cards (T-128) ---------------------------------------------


_OWED = "(p.amount_payable - p.amount_paid)"
# Ringkasan PO buckets: (path, condition, amount). The conditions are the list drill-down filters.
_SUMMARY_BUCKETS: list[tuple[str, str, str]] = [
    ("total", "true", "p.total"),
    *((f"status.{k}", cond, "p.total") for k, cond in _STATE.items()),
    *((f"goods.{k}", cond, "p.total") for k, cond in _GOODS.items()),
    ("payment.unpaid", "p.payment_status = 'unpaid'", _OWED),
    ("payment.partially_paid", "p.payment_status = 'partially_paid'", _OWED),
    ("payment.paid", "p.payment_status = 'paid'", "p.amount_paid"),
    ("by_term.pay_later", "p.payment_term = 'pay_later'", "p.total"),
    ("by_term.pay_in_advance", "p.payment_term = 'pay_in_advance'", "p.total"),
]
# Built once from the constants above (no user input).
_SUMMARY_SQL = (
    "select "  # noqa: S608
    + ", ".join(
        f'count(*) filter (where {cond})::int as "{path}.count",'
        f' coalesce(sum({amount}) filter (where {cond}), 0)::bigint as "{path}.amount"'
        for path, cond, amount in _SUMMARY_BUCKETS
    )
    + " from app.purchase_orders p"
    + _LINE_COUNTS
    + " where p.status <> 'cancelled'"
    " and (%(outlet)s::uuid is null or p.outlet_id = %(outlet)s)"
    " and p.ordered_on >= %(start)s and p.ordered_on < %(end)s"
)


async def po_summary(
    conn: AsyncConnection, *, outlet_id: UUID | None, month: str
) -> dict[str, Any]:
    """Ringkasan PO (FR3.12, AC3.14): POs opened in `month` (outlet-local open date), cancelled
    ones left out, aggregated in SQL with the same conditions as the list drill-down. Amounts:
    status, goods and term buckets use the PO total; payment buckets use what that bucket means
    in money — unpaid: amount owed, partly paid: what is still owed ("sisa"), paid: amount
    paid."""
    start, end = month_bounds(month)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(_SUMMARY_SQL, {"outlet": outlet_id, "start": start, "end": end})
    row = await cur.fetchone() or {}
    out: dict[str, Any] = {"month": month}
    for path, _, _ in _SUMMARY_BUCKETS:
        node = out
        *parents, leaf = path.split(".")
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = {"count": row[f"{path}.count"], "amount": row[f"{path}.amount"]}
    return out


async def supplier_payments(conn: AsyncConnection, *, outlet_id: UUID | None) -> dict[str, Any]:
    """Pembayaran supplier (FR3.11, AC3.8, AC3.9, AC3.12): every PO that needs paying today,
    whatever the month — closed pay-later POs not fully paid and open pay-in-advance POs not
    paid. Overdue first, then the nearest due (or expected delivery) date. Supplier debt is
    what those pay-later POs still owe; goods paid for but not received are pay-in-advance
    POs paid and not closed yet. Neither is cash out (cash basis)."""
    cur = conn.cursor(row_factory=dict_row)
    where = "(%(outlet)s::uuid is null or p.outlet_id = %(outlet)s)"
    await cur.execute(
        _ROW_SELECT + f" where {where} and ({_AWAITING_PAYMENT})", {"outlet": outlet_id}
    )
    rows = await cur.fetchall()
    for row in rows:
        row["is_overdue"] = _overdue(row)
    rows.sort(
        key=lambda r: (
            not r["is_overdue"],
            r["due_date"] or r["expected_date"] or r["ordered_on"],
            r["created_at"],
        )
    )
    items = []
    debt = due_7d = due_7d_count = overdue_count = 0
    for row in rows:
        owed = _owed(row)
        if row["payment_term"] == "pay_later":
            debt += owed
            if row["is_overdue"]:
                overdue_count += 1
            elif (row["due_date"] - row["local_today"]).days <= 7:
                due_7d += owed
                due_7d_count += 1
        reason = (
            "overdue"
            if row["is_overdue"]
            else ("pay_in_advance" if row["payment_term"] == "pay_in_advance" else "due")
        )
        items.append(
            {
                "po_id": row["id"],
                "number": po_label(row["order_prefix"], row["po_no"]),
                "supplier": {"id": row["supplier_id"], "name": row["supplier_name"]},
                "outlet": {"id": row["outlet_id"], "name": row["outlet_name"]},
                "payment_term": row["payment_term"],
                "reason": reason,
                "status": row["status"],
                "due_date": row["due_date"],
                "expected_date": row["expected_date"],
                "days_overdue": (row["local_today"] - row["due_date"]).days
                if row["is_overdue"]
                else None,
                "total": row["total"],
                "amount_paid": row["amount_paid"],
                "amount_owed": owed,
                "created_by": row["created_by_name"],
                "allowed_actions": allowed_actions(row, "owner"),
            }
        )
    await cur.execute(
        "select coalesce(sum(p.amount_paid), 0)::bigint as amount, count(*)::int as count"
        " from app.purchase_orders p"
        " where (%(outlet)s::uuid is null or p.outlet_id = %(outlet)s)"
        " and p.payment_term = 'pay_in_advance' and p.amount_paid > 0"
        " and p.status in ('open', 'difference_found')",
        {"outlet": outlet_id},
    )
    prepaid = await cur.fetchone()
    return {
        "debt_total": debt,
        "overdue_count": overdue_count,
        "due_7d_amount": due_7d,
        "due_7d_count": due_7d_count,
        "prepaid_not_received": prepaid["amount"] if prepaid else 0,
        "prepaid_not_received_count": prepaid["count"] if prepaid else 0,
        "items": items,
    }


async def po_differences(conn: AsyncConnection, *, outlet_id: UUID | None) -> list[dict[str, Any]]:
    """PO ada selisih (FR3.11, AC4.10): every PO with status difference_found, whatever the
    month, with the short lines and the last delivery; oldest delivery first."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select x.*, r.last_received_on, r.last_received_at from ("  # noqa: S608 (constants)
        + _ROW_SELECT
        + " where p.status = 'difference_found'"
        " and (%(outlet)s::uuid is null or p.outlet_id = %(outlet)s)) x"
        """
        left join lateral (
          select max(received_on) as last_received_on, max(created_at) as last_received_at
          from app.purchase_order_receipts where purchase_order_id = x.id
        ) r on true
        order by r.last_received_at nulls first, x.created_at
        """,
        {"outlet": outlet_id},
    )
    pos = await cur.fetchall()
    if not pos:
        return []
    await cur.execute(
        "select purchase_order_id, item_name, quantity, received_quantity, unit"
        " from app.purchase_order_lines"
        " where purchase_order_id = any(%s) and received_quantity < quantity order by line_no",
        ([p["id"] for p in pos],),
    )
    short: dict[UUID, list[dict[str, Any]]] = {}
    for line in await cur.fetchall():
        short.setdefault(line["purchase_order_id"], []).append(
            {
                "item": line["item_name"],
                "ordered": line["quantity"],
                "received": line["received_quantity"],
                "short": line["quantity"] - line["received_quantity"],
                "unit": line["unit"],
            }
        )
    return [
        {
            "po_id": p["id"],
            "number": po_label(p["order_prefix"], p["po_no"]),
            "supplier": {"id": p["supplier_id"], "name": p["supplier_name"]},
            "outlet": {"id": p["outlet_id"], "name": p["outlet_name"]},
            "payment_term": p["payment_term"],
            "short_lines": short.get(p["id"], []),
            "last_received_on": p["last_received_on"],
            "last_received_at": p["last_received_at"],
            "days_since_last_received": (p["local_today"] - p["last_received_on"]).days
            if p["last_received_on"]
            else None,
            "allowed_actions": allowed_actions(p, "owner"),
        }
        for p in pos
    ]
