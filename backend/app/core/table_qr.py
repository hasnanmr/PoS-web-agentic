"""Customer table web page (T-134, T-136) — wireframes Q0-Q5 and O8 "Tujuan QR meja".

One QR per table opens `/t/<qr_token>`. The page has no sign-in: every call resolves the token
to one outlet and table (`app.resolve_table_qr`) and then runs as the `system` actor for that
tenant, touching only that outlet's menu and QRIS and the orders placed from that table.

Rules (PRD FR2.13-FR2.16, docs/architecture/screen-endpoint-map.md → Q0-Q5):

- Web orders are always paid first with the outlet's static QRIS and never join the open bill.
- Each web order gets an access key, returned once to the phone that placed it; only its
  SHA-256 is stored. Reading or acting on an order needs that key (FR2.15).
- "Saya sudah bayar" is a payment proof without a screenshot (`kind = customer_claim`): the
  order becomes `proof_submitted`, the unpaid timer stops, and staff accept or reject it in S4.
- An unpaid web order is cancelled when the outlet's unpaid-order limit passes (FR10.4). There
  is no poller yet, so this runs lazily whenever the table page or the order board is read.
"""

from __future__ import annotations

import hashlib
import io
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote as urlquote
from uuid import UUID

import segno
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core import orders
from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError

Target = Literal["web_whatsapp", "web", "whatsapp"]

TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
# After an order is completed or cancelled, the phone can still open it for this long (FR2.15).
READABLE_AFTER_FINAL = timedelta(hours=1)
AUTO_CANCEL_REASON = "Batal otomatis: belum dibayar sebelum batas waktu"
CUSTOMER_CANCEL_REASON = "Dibatalkan pelanggan dari halaman QR meja"


# Token → table ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TableRef:
    token: str
    tenant_id: UUID
    outlet_id: UUID
    table_id: UUID
    table_name: str
    area: str | None
    outlet_name: str
    timezone: str
    target: Target
    whatsapp_connected: bool
    whatsapp_phone: str | None
    unpaid_timeout_minutes: int
    has_qris: bool

    def actor(self) -> ActorContext:
        return ActorContext.for_system(self.tenant_id)

    @property
    def effective_target(self) -> Target:
        """While WhatsApp isn't connected the QR always leads to the web page (FR2.16)."""
        return self.target if self.whatsapp_connected else "web"

    @property
    def web_ordering(self) -> bool:
        """Web orders are paid with the outlet's static QRIS, so they need one (FR2.13)."""
        return self.has_qris

    @property
    def whatsapp_url(self) -> str | None:
        if self.effective_target == "web" or not self.whatsapp_phone:
            return None
        digits = "".join(c for c in self.whatsapp_phone if c.isdigit())
        text = urlquote(f"MEJA {self.table_name} · {self.token}")
        return f"https://wa.me/{digits}?text={text}"


async def resolve(conn: AsyncConnection, token: str) -> TableRef | None:
    """No tenant context is needed (definer function). None = unknown or replaced token (Q0)."""
    if not TOKEN_PATTERN.match(token):
        return None
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute("select * from app.resolve_table_qr(%s)", (token,))
    row = await cur.fetchone()
    if row is None:
        return None
    return TableRef(
        token=token,
        tenant_id=row["tenant_id"],
        outlet_id=row["outlet_id"],
        table_id=row["table_id"],
        table_name=row["table_name"],
        area=row["area"],
        outlet_name=row["outlet_name"],
        timezone=row["timezone"],
        target=row["table_qr_target"],
        whatsapp_connected=row["whatsapp_status"] == "connected",
        whatsapp_phone=row["whatsapp_phone"],
        unpaid_timeout_minutes=row["unpaid_timeout_minutes"],
        has_qris=row["has_qris"],
    )


def new_access_key() -> str:
    return secrets.token_urlsafe(24)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# Unpaid timeout (lazy, FR10.4) ---------------------------------------------------------------


async def expire_unpaid(conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID) -> int:
    """Cancel this outlet's web orders still unpaid past the limit; stock returns. Runs as
    `system`. Orders whose customer tapped "Saya sudah bayar" wait for staff instead."""
    cur = await conn.execute(
        """
        select o.id from app.orders o join app.outlets ou on ou.id = o.outlet_id
        where o.outlet_id = %s and o.channel = 'web_table' and o.status = 'pending_payment'
          and o.payment_status = 'unpaid'
          and o.created_at + make_interval(mins => ou.unpaid_timeout_minutes) <= now()
        order by o.created_at
        for update of o skip locked
        """,
        (outlet_id,),
    )
    ids = [r[0] for r in await cur.fetchall()]
    for order_id in ids:
        await orders.cancel(conn, ctx, order_id, AUTO_CANCEL_REASON)
    return len(ids)


# Customer orders ------------------------------------------------------------------------------


_WEB_ORDER_SQL = """
select id, status::text as status, payment_status::text as payment_status, created_at, updated_at
from app.orders
where id = %s and outlet_id = %s and table_id = %s and channel = 'web_table'
  and access_key_hash = %s
"""
_WEB_ORDER_LOCK_SQL = _WEB_ORDER_SQL + "for update"


async def _web_order(
    conn: AsyncConnection, ref: TableRef, order_id: UUID, key: str | None, *, lock: bool = False
) -> dict[str, Any]:
    """The order, only when it was placed from this table with this key and is still readable.
    Anything else is `not_found` with no data (ACN6)."""
    if not key:
        raise NotFoundError("order")
    cur = conn.cursor(row_factory=dict_row)
    sql = _WEB_ORDER_LOCK_SQL if lock else _WEB_ORDER_SQL
    await cur.execute(sql, (order_id, ref.outlet_id, ref.table_id, hash_key(key)))
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("order")
    if (
        row["status"] in orders.FINAL_STATUSES
        and row["updated_at"] < datetime.now(UTC) - READABLE_AFTER_FINAL
    ):
        raise NotFoundError("order")
    return row


async def place_order(
    conn: AsyncConnection, ctx: ActorContext, ref: TableRef, draft: orders.WebOrder
) -> dict[str, Any]:
    if not ref.web_ordering:
        raise ConflictError(
            "web_ordering_unavailable", "this outlet takes orders at the counter only"
        )
    created = await orders.create_web_order(conn, ctx, ref.outlet_id, draft)
    created["pay_by"] = await _pay_by(conn, ref, created["id"])
    return created


async def _pay_by(conn: AsyncConnection, ref: TableRef, order_id: UUID) -> datetime:
    cur = await conn.execute("select created_at from app.orders where id = %s", (order_id,))
    created_at = (await cur.fetchone())[0]  # type: ignore[index]
    return created_at + timedelta(minutes=ref.unpaid_timeout_minutes)


async def order_status(
    conn: AsyncConnection, ref: TableRef, order_id: UUID, key: str | None
) -> dict[str, Any]:
    """Q4/Q5: what the phone that placed the order may see — no staff names, no other orders."""
    await _web_order(conn, ref, order_id, key)
    detail = await orders.detail(conn, order_id)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select kind, status::text as status, received_at, rejection_reason"
        " from app.payment_proofs where order_id = %s order by received_at desc limit 1",
        (order_id,),
    )
    proof = await cur.fetchone()
    cancel_reason = None
    for e in detail["events"]:
        if e["to"] == "cancelled" and e["reason"]:
            cancel_reason = e["reason"]
    events = [
        {"status": e["to"], "at": e["at"]}
        for e in detail["events"]
        if e["to"] and e["kind"] in ("created", "status_changed", "proof_rejected")
    ]
    claimed_at = proof["received_at"] if proof and proof["kind"] == "customer_claim" else None
    rejected = proof is not None and proof["status"] == "rejected"
    return {
        "id": detail["id"],
        "order_no": detail["order_no"],
        "created_at": detail["created_at"],
        "customer_name": detail["customer_name"],
        "note": detail["note"],
        "status": detail["status"],
        "payment_status": detail["payment_status"],
        "claimed_at": claimed_at,
        "pay_by": detail["created_at"] + timedelta(minutes=ref.unpaid_timeout_minutes),
        "items": [
            {
                "name": i["name"],
                "quantity": i["quantity"],
                "addons": [a["name"] for a in i["addons"]],
                "note": i["note"],
                "line_total": i["line_total"],
            }
            for i in detail["items"]
        ],
        "subtotal": detail["subtotal"],
        "pb1_amount": detail["pb1_amount"],
        "total": detail["total"],
        "reject_reason": proof["rejection_reason"] if rejected else None,
        "cancel_reason": None if rejected else cancel_reason,
        "events": events,
        "timezone": ref.timezone,
    }


async def claim_payment(
    conn: AsyncConnection, ctx: ActorContext, ref: TableRef, order_id: UUID, key: str | None
) -> None:
    """Q4 "Saya sudah bayar": a proof without a screenshot, reviewed in S4 like any other."""
    row = await _web_order(conn, ref, order_id, key, lock=True)
    if row["payment_status"] == "proof_submitted":
        return  # idempotent
    if row["status"] != "pending_payment" or row["payment_status"] != "unpaid":
        raise ConflictError(
            "order_not_payable",
            "this order is no longer waiting for payment",
            {"status": row["status"], "payment_status": row["payment_status"]},
        )
    await conn.execute(
        "insert into app.payment_proofs (tenant_id, outlet_id, order_id, kind)"
        " values (%s, %s, %s, 'customer_claim')",
        (ctx.tenant_id, ref.outlet_id, order_id),
    )
    await conn.execute(
        "update app.orders set payment_status = 'proof_submitted' where id = %s", (order_id,)
    )
    await orders.record_event(
        conn,
        ctx,
        {"id": order_id, "outlet_id": ref.outlet_id},
        "payment_changed",
        from_payment="unpaid",
        to_payment="proof_submitted",
        data={"kind": "customer_claim"},
    )


async def customer_cancel(
    conn: AsyncConnection, ctx: ActorContext, ref: TableRef, order_id: UUID, key: str | None
) -> None:
    """Q4 "Batalkan pesanan": only before "Saya sudah bayar"; afterwards staff decide."""
    row = await _web_order(conn, ref, order_id, key, lock=True)
    if row["status"] != "pending_payment" or row["payment_status"] != "unpaid":
        raise ConflictError(
            "order_not_cancellable",
            "the order can no longer be cancelled here; ask the staff",
            {"status": row["status"], "payment_status": row["payment_status"]},
        )
    await orders.cancel(conn, ctx, order_id, CUSTOMER_CANCEL_REASON)


# Owner (O8) ------------------------------------------------------------------------------------


async def qr_settings(conn: AsyncConnection, outlet_id: UUID) -> dict[str, Any]:
    cur = await conn.execute(
        "select table_qr_target, whatsapp_status = 'connected' from app.outlets where id = %s",
        (outlet_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("outlet")
    return {"target": row[0], "whatsapp_connected": row[1]}


async def put_qr_settings(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, target: Target
) -> dict[str, Any]:
    """Saved even while WhatsApp isn't connected: it takes effect once WhatsApp connects."""
    before = await qr_settings(conn, outlet_id)
    await conn.execute(
        "update app.outlets set table_qr_target = %s where id = %s", (target, outlet_id)
    )
    if before["target"] != target:
        await record_audit(
            conn,
            ctx,
            action="table_qr_settings.updated",
            entity_type="outlet",
            entity_id=outlet_id,
            outlet_id=outlet_id,
            data={"from": before["target"], "to": target},
        )
    return await qr_settings(conn, outlet_id)


async def table_token(conn: AsyncConnection, table_id: UUID) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select t.id, t.name, t.qr_token, t.outlet_id, o.name as outlet_name from app.tables t"
        " join app.outlets o on o.id = t.outlet_id where t.id = %s and t.is_active",
        (table_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("table")
    return row


async def outlet_tokens(conn: AsyncConnection, outlet_id: UUID) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select t.id, t.name, t.qr_token, o.name as outlet_name from app.tables t"
        " join app.outlets o on o.id = t.outlet_id"
        " where t.outlet_id = %s and t.is_active order by t.name",
        (outlet_id,),
    )
    return await cur.fetchall()


async def replace_token(conn: AsyncConnection, ctx: ActorContext, table_id: UUID) -> str:
    """O8 "↻ Ganti": the old printed QR stops working at once (Q0)."""
    table = await table_token(conn, table_id)
    cur = await conn.execute(
        "update app.tables set qr_token = replace(gen_random_uuid()::text, '-', '')"
        " where id = %s returning qr_token",
        (table_id,),
    )
    token = (await cur.fetchone())[0]  # type: ignore[index]
    await record_audit(
        conn,
        ctx,
        action="table.qr_token_replaced",
        entity_type="table",
        entity_id=table_id,
        outlet_id=table["outlet_id"],
        data={"table": table["name"]},
    )
    return token


def table_url(app_url: str, token: str) -> str:
    return f"{app_url.rstrip('/')}/t/{token}"


def qr_png(url: str) -> bytes:
    out = io.BytesIO()
    segno.make(url, error="m").save(out, kind="png", scale=12, border=2)
    return out.getvalue()


def qr_pdf(pages: list[dict[str, str]]) -> bytes:
    """O8 "⭳ Unduh semua QR (PDF)": one A5 page per table with the QR (vector squares), the
    table name, and the outlet name. A hand-written PDF: segno only draws one QR per file."""
    width, height = 420.0, 595.0  # A5 portrait, points
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    page_ids: list[int] = []
    pages_id_placeholder = len(objects) + 1 + 2 * len(pages)  # pages tree comes after all pages
    for page in pages:
        matrix = [list(row) for row in segno.make(page["url"], error="m").matrix]
        modules = len(matrix)
        size = 300.0
        cell = size / modules
        left, top = (width - size) / 2, height - 110
        ops = ["0 0 0 rg"]
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    ops.append(
                        f"{left + x * cell:.2f} {top - (y + 1) * cell:.2f} {cell:.2f} {cell:.2f} re"
                    )
        ops.append("f")
        ops.append(_pdf_text(page["title"], 28, width, height - 70))
        ops.append(_pdf_text(page["subtitle"], 14, width, top - size - 40))
        ops.append(_pdf_text("Scan untuk pesan", 12, width, top - size - 64))
        stream = "\n".join(ops).encode("cp1252", errors="replace")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R"
                b" /Resources << /Font << /F1 %d 0 R >> >> >>"
                % (pages_id_placeholder, width, height, content, font)
            )
        )
    kids = b" ".join(b"%d 0 R" % i for i in page_ids)
    pages_id = add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids)))
    assert pages_id == pages_id_placeholder  # noqa: S101 - fixed object layout
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, catalog, xref)
    )
    return out.getvalue()


def _pdf_text(text: str, size: int, page_width: float, y: float) -> str:
    """Centered Helvetica-Bold text (approximate width: 0.55 em per character)."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    x = max(20.0, (page_width - len(text) * size * 0.55) / 2)
    return f"BT /F1 {size} Tf {x:.2f} {y:.2f} Td ({safe}) Tj ET"
