"""QRIS payment-proof review (T-037) — screen S4 "Review Pembayaran QRIS".

A customer's screenshot (`payment_proof`, received through WhatsApp in T-036) moves the
order to `proof_submitted` and stops the unpaid timer. Staff then either:

- **Tandai paid**: only after confirming the transfer in the merchant QRIS account
  (`merchant_account_checked`). Records the QRIS payment, posts the ledger, confirms the
  order. Actor and time are stored on the proof, the payment, and the order events.
- **Tolak bukti bayar**: reason required. The order is cancelled at once, payment stays
  `unpaid`, stock returns as a `sale_reversal` movement, no ledger entry, and the customer
  is told to contact the outlet (notification hook).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core import notifications, orders, payments
from app.core.actor import ActorContext
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.payments import PaymentInput


def mask_phone(phone: str | None) -> str | None:
    """S4 "+62 812-xxxx-221": country code, first three digits, last three digits."""
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 8:
        return "xxxx"
    if digits.startswith("62"):
        return f"+62 {digits[2:5]}-xxxx-{digits[-3:]}"
    return f"{digits[:3]}-xxxx-{digits[-3:]}"


_QUEUE = """
select distinct on (p.order_id)
       p.id as proof_id, p.kind, p.order_id, p.received_at, o.order_no, ou.order_prefix,
       ou.timezone,
       o.channel::text as channel, o.type::text as order_type, t.name as table_name, o.total
from app.payment_proofs p
join app.orders o on o.id = p.order_id
join app.outlets ou on ou.id = p.outlet_id
left join app.tables t on t.id = o.table_id
where p.outlet_id = %s and p.status = 'pending' and o.payment_status = 'proof_submitted'
order by p.order_id, p.received_at desc
"""


def _queue_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "proof_id": r["proof_id"],
        "kind": r["kind"],
        "order_id": r["order_id"],
        "order_no": orders.order_label(r["order_prefix"], r["order_no"]),
        "channel": r["channel"],
        "order_type": r["order_type"],
        "table": r["table_name"],
        "total": r["total"],
        "received_at": r["received_at"],
        "timezone": r["timezone"],
    }


async def pending_queue(conn: AsyncConnection, outlet_id: UUID) -> list[dict[str, Any]]:
    """S4 "Antrian · proof_submitted": the latest pending screenshot per order, oldest first."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(_QUEUE, (outlet_id,))
    rows = sorted(await cur.fetchall(), key=lambda r: r["received_at"])
    return [_queue_row(r) for r in rows]


_PROOF_SQL = """
select p.id, p.kind, p.order_id, p.outlet_id, p.status::text as status, p.storage_path,
       p.received_at, p.reviewed_at, p.rejection_reason, u.display_name as reviewed_by,
       coalesce(cu.phone, c.phone) as phone, o.customer_name
from app.payment_proofs p
join app.orders o on o.id = p.order_id
left join app.whatsapp_contacts c on c.id = o.contact_id
left join app.customers cu on cu.id = o.customer_id
left join app.users u on u.id = p.reviewed_by
where p.id = %s
"""


async def _load(conn: AsyncConnection, proof_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    if lock:
        await cur.execute("select 1 from app.payment_proofs where id = %s for update", (proof_id,))
    await cur.execute(_PROOF_SQL, (proof_id,))
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("payment proof")
    return row


async def detail(conn: AsyncConnection, proof_id: UUID) -> dict[str, Any]:
    """S4 detail panel. `image_url` is a short-lived signed URL once proof storage exists
    (T-036); until then it is null and the panel shows the placeholder."""
    proof = await _load(conn, proof_id)
    order = await orders.detail(conn, proof["order_id"])
    return {
        "proof_id": proof["id"],
        "kind": proof["kind"],
        "status": proof["status"],
        "image_url": None,
        "order_id": order["id"],
        "order_no": order["order_no"],
        "channel": order["channel"],
        "order_type": order["type"],
        "table": order["table"],
        "total": order["total"],
        "order_status": order["status"],
        "payment_status": order["payment_status"],
        "customer_phone_masked": mask_phone(proof["phone"]),
        "received_at": proof["received_at"],
        "timezone": order["timezone"],
        # The unpaid timer stops when a proof arrives (glossary §5 rule 6).
        "timer_stopped": order["payment_status"] == "proof_submitted",
        "reviewed_by": proof["reviewed_by"],
        "reviewed_at": proof["reviewed_at"],
        "rejection_reason": proof["rejection_reason"],
    }


async def _reviewable(
    conn: AsyncConnection, proof_id: UUID
) -> tuple[dict[str, Any], dict[str, Any]]:
    proof = await _load(conn, proof_id, lock=True)
    order = await orders.load_for_update(conn, proof["order_id"])
    if (
        proof["status"] != "pending"
        or order["payment_status"] != "proof_submitted"
        or order["status"] in orders.FINAL_STATUSES
    ):
        raise ConflictError(
            "proof_not_pending",
            "this proof was already reviewed or the order is no longer waiting for payment",
            {"proof_status": proof["status"], "payment_status": order["payment_status"]},
        )
    return proof, order


async def accept(
    conn: AsyncConnection, ctx: ActorContext, proof_id: UUID, *, merchant_account_checked: bool
) -> dict[str, Any]:
    """S4 "✓ Tandai paid" (active only after the merchant-account checkbox)."""
    if not merchant_account_checked:
        raise ValidationFailedError(
            "confirm the transaction in the merchant QRIS account first",
            {"field": "merchant_account_checked"},
        )
    _, order = await _reviewable(conn, proof_id)
    now = datetime.now(UTC)
    result = await payments.capture(
        conn,
        ctx,
        order["outlet_id"],
        PaymentInput("qris"),
        amount=order["total"],
        subtotal=order["subtotal"],
        pb1_amount=order["pb1_amount"],
        delivery_fee=order["delivery_fee"],
        order_id=order["id"],
    )
    await conn.execute(
        "update app.payment_proofs set status = 'accepted', reviewed_by = %s, reviewed_at = %s,"
        " merchant_checked_at = %s where id = %s",
        (ctx.user_id, now, now, proof_id),
    )
    await orders.mark_paid(
        conn,
        ctx,
        order,
        from_payment="proof_submitted",
        data={
            "method": "qris",
            "amount": result.amount,
            "proof_id": str(proof_id),
            "merchant_account_checked": True,
        },
    )
    await notifications.order_customer(conn, ctx, order["id"], "payment_confirmed")
    return await detail(conn, proof_id)


async def reject(
    conn: AsyncConnection, ctx: ActorContext, proof_id: UUID, reason: str
) -> dict[str, Any]:
    """S4 "✕ Tolak bukti bayar & batalkan order"."""
    ctx = ctx.with_reason(reason)
    _, order = await _reviewable(conn, proof_id)
    await conn.execute(
        "update app.payment_proofs set status = 'rejected', reviewed_by = %s, reviewed_at = now(),"
        " rejection_reason = %s where id = %s",
        (ctx.user_id, ctx.reason, proof_id),
    )
    await orders.cancel_rejected_proof(conn, ctx, order, proof_id)
    await notifications.order_customer(conn, ctx, order["id"], "proof_rejected")
    return await detail(conn, proof_id)
