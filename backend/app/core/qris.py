"""Static QRIS per outlet (O3) and the staff cross-check of QRIS payments (S2), PoC demo.

O3 "QRIS statis outlet": the owner uploads one PNG/JPG (max 2 MB) per outlet. The counter
(S1) and the bill close (S5) show it so the customer can scan and pay.

S2 "Cek →": a QRIS payment is recorded when the cashier takes it, so the order goes to the
kitchen at once. Staff later match it against the receiving account and confirm with
"Saya sudah menemukan transaksi ini di akun merchant QRIS" (same step as S4).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core import orders
from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError

MAX_BYTES = 2 * 1024 * 1024
CONTENT_TYPES = {"image/png", "image/jpeg"}

# File signatures, so a renamed file of another type is refused.
_MAGIC = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}


def validate_image(content_type: str, data: bytes) -> str:
    """The normalised content type, or `ValidationFailedError` ("Hanya PNG/JPG, maks 2 MB")."""
    kind = (content_type or "").split(";")[0].strip().lower()
    if kind == "image/jpg":
        kind = "image/jpeg"
    if kind not in CONTENT_TYPES or not data.startswith(_MAGIC[kind]):
        raise ValidationFailedError("only PNG or JPG images", {"field": "image"})
    if len(data) > MAX_BYTES:
        raise ValidationFailedError("the image is larger than 2 MB", {"field": "image"})
    return kind


async def save_image(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
) -> dict[str, Any]:
    kind = validate_image(content_type, data)
    name = (filename or "").strip().replace("/", "_")[:200] or "qris"
    cur = await conn.execute("select tenant_id from app.outlets where id = %s", (outlet_id,))
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("outlet")
    await conn.execute(
        """
        insert into app.outlet_qris
          (outlet_id, tenant_id, filename, content_type, image, uploaded_by, uploaded_at)
        values (%s, %s, %s, %s, %s, %s, now())
        on conflict (outlet_id) do update
          set filename = excluded.filename, content_type = excluded.content_type,
              image = excluded.image, uploaded_by = excluded.uploaded_by,
              uploaded_at = excluded.uploaded_at
        """,
        (outlet_id, row[0], name, kind, data, ctx.user_id),
    )
    await record_audit(
        conn,
        ctx,
        action="outlet.qris_uploaded",
        entity_type="outlet",
        entity_id=outlet_id,
        outlet_id=outlet_id,
        data={"filename": name, "size": len(data)},
    )
    meta = await image_meta(conn, outlet_id)
    if meta is None:  # not visible right after writing it: no access to this outlet
        raise NotFoundError("outlet")
    return meta


async def image_meta(conn: AsyncConnection, outlet_id: UUID) -> dict[str, Any] | None:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select filename, content_type, octet_length(image) as size, uploaded_at"
        " from app.outlet_qris where outlet_id = %s",
        (outlet_id,),
    )
    return await cur.fetchone()


async def image(conn: AsyncConnection, outlet_id: UUID) -> tuple[str, bytes]:
    cur = await conn.execute(
        "select content_type, image from app.outlet_qris where outlet_id = %s", (outlet_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("qris_image")
    return row[0], bytes(row[1])


async def check_order(
    conn: AsyncConnection, ctx: ActorContext, order_id: UUID, *, merchant_account_checked: bool
) -> dict[str, Any]:
    """S2 "Cek →" → "✓ Sudah masuk": the order's QRIS payment (its own, or its bill's) was
    found in the receiving account. Returns the order card."""
    if not merchant_account_checked:
        raise ValidationFailedError(
            "confirm the transaction in the merchant QRIS account first",
            {"field": "merchant_account_checked"},
        )
    order = await orders.detail(conn, order_id)
    if "qris_check" not in order["allowed_actions"]:
        code = "already_checked" if order["qris_checked"] else "not_checkable"
        raise ConflictError(
            code,
            "this QRIS payment is already checked"
            if code == "already_checked"
            else "only a paid QRIS order can be checked",
            {"allowed_actions": order["allowed_actions"]},
        )
    payment_id = order["payment_id"]
    cur = await conn.execute(
        "insert into app.qris_checks (payment_id, tenant_id, outlet_id, checked_by)"
        " select id, tenant_id, outlet_id, %s from app.payments where id = %s"
        " on conflict (payment_id) do nothing returning outlet_id",
        (ctx.user_id, payment_id),
    )
    inserted = await cur.fetchone()
    if inserted is None:
        raise ConflictError("already_checked", "this QRIS payment is already checked")
    await record_audit(
        conn,
        ctx,
        action="payment.qris_checked",
        entity_type="payment",
        entity_id=payment_id,
        outlet_id=inserted[0],
        data={
            "order_id": str(order_id),
            "bill_id": str(order["bill_id"]) if order["bill_id"] else None,
            "amount": order["total"],
        },
    )
    return await orders.detail(conn, order_id)
