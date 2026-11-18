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
Method = Literal["cash", "qris"]

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
) -> int:
    """Insert one ledger row and return its id."""
    cur = await conn.execute(
        """
        insert into app.ledger_entries (tenant_id, outlet_id, type, amount, payment_method,
          order_id, bill_id, payment_id, shift_id, description, business_date, actor_type, actor_id,
          pb1_portion, reverses_entry_id)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
       r.id as reversal_id, r.description as reversal_reason
from app.ledger_entries l
join app.outlets o on o.id = l.outlet_id
left join app.users u on u.id = l.actor_id
left join app.ledger_entries r on r.reverses_entry_id = l.id
where l.type = 'expense'
"""


def _expense_out(row: dict[str, Any]) -> dict[str, Any]:
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
) -> dict[str, Any]:
    """O9 "Pengeluaran terbaru" / "Lihat semua": newest business date first."""
    after = _decode_cursor(cursor) if cursor else None
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        _EXPENSE_SELECT
        + """
          and (%(outlet)s::uuid is null or l.outlet_id = %(outlet)s)
          and (%(from)s::date is null or l.business_date >= %(from)s)
          and (%(to)s::date is null or l.business_date <= %(to)s)
          and (%(after_date)s::date is null
               or (l.business_date, l.id) < (%(after_date)s::date, %(after_id)s::bigint))
        order by l.business_date desc, l.id desc
        limit %(limit)s
        """,
        {
            "outlet": outlet_id,
            "from": date_from,
            "to": date_to,
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


async def reverse_entry(conn: AsyncConnection, ctx: ActorContext, entry_id: int) -> dict[str, Any]:
    """O9 "Salah input? Buat entry reversal, bukan edit." A new row with the opposite amount,
    on the original's business date so the corrected period adds up. Only expenses are
    reversed here; sales are reversed through the order (S3), which also handles stock."""
    if not (ctx.reason or "").strip():
        raise ValidationFailedError("a reason is required", {"field": "reason"})
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, outlet_id, type::text as type, amount, payment_method::text as method,"
        " business_date from app.ledger_entries where id = %s",
        (entry_id,),
    )
    entry = await cur.fetchone()
    if entry is None:
        raise NotFoundError("ledger entry")
    if entry["type"] != "expense":
        raise ConflictError(
            "not_reversible", "only expenses are reversed here; reverse sales from the order"
        )
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
