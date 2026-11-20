"""Append-only ledger (T-041, T-042) — glossary §2 and §7, screen O9.

Every money movement is one row in `app.ledger_entries` with a signed amount (+ money in,
- money out), the outlet, the outlet-local business date, and the actor. Rows are never
updated or deleted (no privilege, plus a trigger); a mistake is corrected with a new
`reversal` row that points at the original. Posting happens only at confirmed payment
(revenue, PB1, delivery fee), at reversal (refund), at shift close (cash shortage/surplus),
and when the owner records an expense.
"""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row

from app.core.actor import ActorContext
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.localtime import local_date

EntryType = Literal[
    "revenue",
    "pb1",
    "delivery_fee",
    "refund",
    "expense",
    "cash_shortage",
    "cash_surplus",
    "reversal",
]
Method = Literal["cash", "qris", "transfer"]

DESCRIPTION_MAX = 120
EXPENSE_MAX = 1_000_000_000


async def post(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    entry_type: EntryType,
    amount: int,
    method: Method | None,
    business_date: date,
    *,
    order_id: UUID | None = None,
    bill_id: UUID | None = None,
    payment_id: UUID | None = None,
    shift_id: UUID | None = None,
    description: str | None = None,
    pb1_portion: int = 0,
    reverses_entry_id: int | None = None,
    purchase_order_id: UUID | None = None,
) -> int:
    """Insert one ledger row and return its id."""
    cur = await conn.execute(
        """
        insert into app.ledger_entries (tenant_id, outlet_id, type, amount, payment_method,
          order_id, bill_id, payment_id, shift_id, description, business_date, actor_type, actor_id,
          pb1_portion, reverses_entry_id, purchase_order_id)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            ctx.tenant_id,
            outlet_id,
            entry_type,
            amount,
            method,
            order_id,
            bill_id,
            payment_id,
            shift_id,
            description,
            business_date,
            ctx.actor_type.value,
            ctx.actor_id,
            pb1_portion,
            reverses_entry_id,
            purchase_order_id,
        ),
    )
    return (await cur.fetchone())[0]  # type: ignore[index]


async def outlet_timezone(conn: AsyncConnection, outlet_id: UUID) -> str:
    cur = await conn.execute("select timezone from app.outlets where id = %s", (outlet_id,))
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("outlet")
    return row[0]


async def today(conn: AsyncConnection, outlet_id: UUID) -> date:
    """The outlet-local business date right now."""
    return local_date(datetime.now(UTC), await outlet_timezone(conn, outlet_id))


# Expenses (O9 "Catat pengeluaran") -----------------------------------------------------------


_EXPENSE_SELECT = """
select l.id, l.business_date, l.outlet_id, o.name as outlet_name, l.description,
       -l.amount as amount, l.created_at, u.display_name as recorded_by,
       r.id as reversal_id, r.description as reversal_reason,
       l.payment_method::text as method, l.purchase_order_id,
       po.po_no, o.order_prefix, po.payment_term::text as po_term,
       s.id as supplier_id, s.name as supplier_name, pu.display_name as po_created_by,
       pu.role::text as po_creator_role, po.amount_payable as po_payable,
       (select coalesce(sum(pp.amount), 0) from app.purchase_order_payments pp
         where pp.purchase_order_id = l.purchase_order_id
           and pp.ledger_entry_id <= l.id)::bigint as po_paid_through
from app.ledger_entries l
join app.outlets o on o.id = l.outlet_id
left join app.users u on u.id = l.actor_id
left join app.ledger_entries r on r.reverses_entry_id = l.id
left join app.purchase_orders po on po.id = l.purchase_order_id
left join app.suppliers s on s.id = po.supplier_id
left join app.users pu on pu.id = po.created_by
where l.type = 'expense'
"""


def _expense_out(row: dict[str, Any]) -> dict[str, Any]:
    # Local import: purchase_orders imports this module (it posts the payment entries).
    from app.core.purchase_orders import _payment_status, po_label

    return {
        "id": row["id"],
        "business_date": row["business_date"],
        "outlet": {"id": row["outlet_id"], "name": row["outlet_name"]},
        "description": row["description"],
        "amount": row["amount"],
        "recorded_by": row["recorded_by"],
        "created_at": row["created_at"],
        "reversed": row["reversal_id"] is not None,
        "reversal_reason": row["reversal_reason"],
        "source": "po" if row["purchase_order_id"] else "direct",
        "payment_method": row["method"],
        "purchase_order": {
            "id": row["purchase_order_id"],
            "number": po_label(row["order_prefix"], row["po_no"]),
            "supplier": {"id": row["supplier_id"], "name": row["supplier_name"]},
            "created_by": row["po_created_by"],
            "created_by_role": row["po_creator_role"],
            "payment_term": row["po_term"],
            # As it stood right after this payment (payments are never reversed, US-058), so
            # the first instalment of a PO paid off later still reads "partially_paid".
            "payment_status": _payment_status(row["po_paid_through"], row["po_payable"]),
        }
        if row["purchase_order_id"]
        else None,
    }


async def record_expense(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    *,
    amount: int,
    business_date: date,
    description: str,
) -> dict[str, Any]:
    """Owner-only manual expense (T-042): outlet, amount, description, date, actor."""
    text = description.strip()
    if not text:
        raise ValidationFailedError("describe the expense", {"field": "description"})
    if not 0 < amount <= EXPENSE_MAX:
        raise ValidationFailedError("enter an amount above zero", {"field": "amount"})
    if business_date > await today(conn, outlet_id):
        raise ValidationFailedError("the date cannot be in the future", {"field": "business_date"})
    entry_id = await post(
        conn, ctx, outlet_id, "expense", -amount, None, business_date, description=text
    )
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(_EXPENSE_SELECT + " and l.id = %s", (entry_id,))
    return _expense_out(await cur.fetchone())  # type: ignore[arg-type]


def _encode_cursor(row: dict[str, Any]) -> str:
    raw = f"{row['business_date'].isoformat()}|{row['id']}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[date, int]:
    try:
        day, entry_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return date.fromisoformat(day), int(entry_id)
    except (ValueError, UnicodeDecodeError):
        raise ValidationFailedError("invalid cursor", {"field": "cursor"}) from None


async def list_expenses(
    conn: AsyncConnection,
    *,
    outlet_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
    cursor: str | None,
    limit: int,
    source: str | None = None,
) -> dict[str, Any]:
    """O9 "Pengeluaran terbaru" / "Lihat semua" and O9b "Riwayat pengeluaran": newest business
    date first. `source` = "po" (supplier payments) or "direct" (owner-logged), else both."""
    after = _decode_cursor(cursor) if cursor else None
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        _EXPENSE_SELECT
        + """
          and (%(outlet)s::uuid is null or l.outlet_id = %(outlet)s)
          and (%(from)s::date is null or l.business_date >= %(from)s)
          and (%(to)s::date is null or l.business_date <= %(to)s)
          and (%(source)s::text is null
               or (l.purchase_order_id is not null) = (%(source)s::text = 'po'))
          and (%(after_date)s::date is null
               or (l.business_date, l.id) < (%(after_date)s::date, %(after_id)s::bigint))
        order by l.business_date desc, l.id desc
        limit %(limit)s
        """,
        {
            "outlet": outlet_id,
            "from": date_from,
            "to": date_to,
            "source": source,
            "after_date": after[0] if after else None,
            "after_id": after[1] if after else None,
            "limit": limit + 1,
        },
    )
    rows = await cur.fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [_expense_out(r) for r in rows],
        "next_cursor": _encode_cursor(rows[-1]) if more and rows else None,
    }


async def expense_summary(
    conn: AsyncConnection, *, outlet_id: UUID | None, date_from: date, date_to: date
) -> dict[str, Any]:
    """O9b KPI cards and "Pengeluaran PO per supplier": expenses in the range that were not
    reversed, split into supplier payments (PO) and direct ones."""
    cur = conn.cursor(row_factory=dict_row)
    params = {"outlet": outlet_id, "from": date_from, "to": date_to}
    where = """
        where l.type = 'expense'
          and not exists (select 1 from app.ledger_entries r where r.reverses_entry_id = l.id)
          and (%(outlet)s::uuid is null or l.outlet_id = %(outlet)s)
          and l.business_date between %(from)s and %(to)s
    """
    await cur.execute(
        "select (l.purchase_order_id is not null) as is_po,"  # noqa: S608
        " coalesce(sum(-l.amount), 0)::bigint as amount, count(*)::int as count,"
        " count(distinct l.purchase_order_id)::int as po_count"
        " from app.ledger_entries l" + where + " group by 1",
        params,
    )
    split = {bool(r["is_po"]): r for r in await cur.fetchall()}
    po, direct = split.get(True), split.get(False)
    # `count` = payment rows (matches the list and its chip); `po_count` = distinct POs paid.
    po_out = {
        "amount": po["amount"] if po else 0,
        "count": po["count"] if po else 0,
        "po_count": po["po_count"] if po else 0,
    }
    direct_out = {
        "amount": direct["amount"] if direct else 0,
        "count": direct["count"] if direct else 0,
    }
    await cur.execute(
        "select s.id as supplier_id, s.name, coalesce(sum(-l.amount), 0)::bigint as amount,"  # noqa: S608
        " count(*)::int as count from app.ledger_entries l"
        " join app.purchase_orders p on p.id = l.purchase_order_id"
        " join app.suppliers s on s.id = p.supplier_id"
        + where
        + " group by s.id, s.name order by amount desc, s.name",
        params,
    )
    return {
        "from": date_from,
        "to": date_to,
        "total": {
            "amount": po_out["amount"] + direct_out["amount"],
            "count": po_out["count"] + direct_out["count"],
        },
        "po": po_out,
        "direct": direct_out,
        "by_supplier": [
            {
                "supplier": {"id": r["supplier_id"], "name": r["name"]},
                "amount": r["amount"],
                "count": r["count"],
            }
            for r in await cur.fetchall()
        ],
    }


async def reverse_entry(conn: AsyncConnection, ctx: ActorContext, entry_id: int) -> dict[str, Any]:
    """O9 "Salah input? Buat entry reversal, bukan edit." A new row with the opposite amount,
    on the original's business date so the corrected period adds up. Only expenses are
    reversed here; sales are reversed through the order (S3), which also handles stock."""
    if not (ctx.reason or "").strip():
        raise ValidationFailedError("a reason is required", {"field": "reason"})
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, outlet_id, type::text as type, amount, payment_method::text as method,"
        " business_date, purchase_order_id from app.ledger_entries where id = %s",
        (entry_id,),
    )
    entry = await cur.fetchone()
    if entry is None:
        raise NotFoundError("ledger entry")
    if entry["type"] != "expense":
        raise ConflictError(
            "not_reversible", "only expenses are reversed here; reverse sales from the order"
        )
    if entry["purchase_order_id"] is not None:
        raise ConflictError("not_reversible", "supplier payments cannot be reversed (US-058)")
    try:  # a concurrent second reversal hits the unique index (no row lock: append-only table)
        async with conn.transaction():
            reversal_id = await post(
                conn,
                ctx,
                entry["outlet_id"],
                "reversal",
                -entry["amount"],
                entry["method"],
                entry["business_date"],
                description=ctx.reason,
                reverses_entry_id=entry["id"],
            )
    except errors.UniqueViolation:
        raise ConflictError("already_reversed", "this entry was already reversed") from None
    await cur.execute(_EXPENSE_SELECT + " and l.id = %s", (entry_id,))
    return {"reversal_id": reversal_id, "expense": _expense_out(await cur.fetchone())}  # type: ignore[arg-type]
