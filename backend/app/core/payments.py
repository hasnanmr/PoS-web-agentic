"""Payment capture and ledger posting (T-038, T-041).

Ledger entries are created only when a payment is confirmed (AC3.2): menu revenue,
PB1, and delivery fee as separate rows, tagged with outlet and payment method. A
reversal posts one negative `refund` row. The ledger is append-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from psycopg import AsyncConnection

from app.core import shifts
from app.core.actor import ActorContext
from app.core.errors import ConflictError, ValidationFailedError
from app.core.localtime import local_date
from app.core.money import InsufficientPaymentError, change_due

Method = Literal["cash", "qris"]


@dataclass(frozen=True, slots=True)
class PaymentInput:
    method: Method
    cash_received: int | None = None
    drawer_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PaymentResult:
    payment_id: UUID
    method: Method
    amount: int
    change_due: int | None
    shift_id: UUID | None


async def _outlet_timezone(conn: AsyncConnection, outlet_id: UUID) -> str:
    cur = await conn.execute("select timezone from app.outlets where id = %s", (outlet_id,))
    return (await cur.fetchone())[0]  # type: ignore[index]


async def capture(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    payment: PaymentInput,
    *,
    amount: int,
    subtotal: int,
    pb1_amount: int,
    delivery_fee: int = 0,
    order_id: UUID | None = None,
    bill_id: UUID | None = None,
) -> PaymentResult:
    """Record a full payment for an order or a bill and post its ledger entries."""
    shift_id = None
    change = None
    if payment.method == "cash":
        if payment.cash_received is None:
            raise ValidationFailedError("enter the cash received", {"field": "cash_received"})
        try:
            change = change_due(amount, payment.cash_received)
        except InsufficientPaymentError:
            raise ConflictError(
                "cash_insufficient",
                "cash received is less than the total",
                {"total": amount, "cash_received": payment.cash_received},
            ) from None
        shift_id = await shifts.shift_for_cash(conn, ctx, outlet_id, payment.drawer_id)
    payment_id = uuid4()
    await conn.execute(
        """
        insert into app.payments (id, tenant_id, outlet_id, order_id, bill_id, method, amount,
                                  cash_received, change_due, shift_id, confirmed_by)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            payment_id,
            ctx.tenant_id,
            outlet_id,
            order_id,
            bill_id,
            payment.method,
            amount,
            payment.cash_received if payment.method == "cash" else None,
            change,
            shift_id,
            ctx.user_id,
        ),
    )
    business_date = local_date(datetime.now(UTC), await _outlet_timezone(conn, outlet_id))
    for entry_type, value in (
        ("revenue", subtotal),
        ("pb1", pb1_amount),
        ("delivery_fee", delivery_fee),
    ):
        if value:
            await _post(
                conn,
                ctx,
                outlet_id,
                entry_type,
                value,
                payment.method,
                business_date,
                order_id=order_id,
                bill_id=bill_id,
                payment_id=payment_id,
                shift_id=shift_id,
            )
    return PaymentResult(payment_id, payment.method, amount, change, shift_id)


async def post_refund(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    *,
    order_id: UUID,
    amount: int,
    pb1_portion: int,
    method: Method,
) -> None:
    """Refund for a reversed paid order (money goes back outside the system). One negative
    entry for the whole amount; `pb1_portion` is the PB1 part of it, so reports can net PB1
    collected against PB1 refunded."""
    business_date = local_date(datetime.now(UTC), await _outlet_timezone(conn, outlet_id))
    shift_id = None
    description = ctx.reason
    if method == "cash":
        # A cash refund leaves the drawer that is open now. With no (or an ambiguous) open
        # shift it is recorded without a shift: it must not change the final count of a shift
        # that already closed, and the description says why for the owner's review.
        shift_id = await shifts.shift_for_refund(conn, ctx, outlet_id)
        if shift_id is None:
            description = f"[tunai tanpa shift terbuka] {ctx.reason or ''}".strip()
    await _post(
        conn,
        ctx,
        outlet_id,
        "refund",
        -amount,
        method,
        business_date,
        order_id=order_id,
        shift_id=shift_id,
        description=description,
        pb1_portion=pb1_portion,
    )


async def _post(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    entry_type: str,
    amount: int,
    method: Method | None,
    business_date: object,
    *,
    order_id: UUID | None = None,
    bill_id: UUID | None = None,
    payment_id: UUID | None = None,
    shift_id: UUID | None = None,
    description: str | None = None,
    pb1_portion: int = 0,
) -> None:
    await conn.execute(
        """
        insert into app.ledger_entries (tenant_id, outlet_id, type, amount, payment_method,
          order_id, bill_id, payment_id, shift_id, description, business_date, actor_type, actor_id,
          pb1_portion)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        ),
    )
