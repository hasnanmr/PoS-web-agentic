"""Customer web chat — wireframes C1-C13 on page 07 (T-049, T-050-T-055, T-036, T-141).

The chat opens from the outlet link `/o/<slug>` (online pickup/delivery, reservations) or a
table QR `/t/<token>` (dine-in). Both are "scopes": the slug or token resolves through a definer
function to one tenant + outlet (+ table), and every call then runs as the `system` actor of
that tenant, touching only that outlet's menu and QRIS and the orders placed from that scope.

Rules (PRD §5.2, §5.6, §5.12; docs/architecture/screen-endpoint-map.md → C1-C15):

- Web chat orders are always paid first with the outlet's static QRIS and never join a bill.
- Each order gets an access key returned once to the phone; only its SHA-256 is stored. Reading
  or acting on an order needs that key (FR2.15), and the order must belong to this scope.
- "Saya sudah bayar" is a proof without a screenshot (`customer_claim`): `proof_submitted`
  stops the unpaid timer, and staff accept or reject it in S4 (FR2.14).
- An unpaid order is cancelled at the outlet's limit (FR10.4). There is no poller yet, so it
  runs lazily whenever the chat or the order board is read.
- Personal data (name, phone) goes to `customers` with the privacy notice version (FR12.1) and
  is anonymized by a trigger once the order is finished (FR12.2).
- The chat session (FR6.2) keeps the step and cart only; a cart idle for 2 hours is emptied.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core import crypto, orders
from app.core.actor import ActorContext
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError

Channel = Literal["web_table", "web_online"]

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
PHONE_PATTERN = re.compile(r"^\+?[0-9]{8,15}$")
# After an order is completed or cancelled, the phone can still open it for this long (FR2.15).
READABLE_AFTER_FINAL = timedelta(hours=1)
# A cart with no activity for this long is emptied (FR6.2, AC6.5).
CART_IDLE = timedelta(hours=2)
AUTO_CANCEL_REASON = "Batal otomatis: belum dibayar sebelum batas waktu"
CUSTOMER_CANCEL_REASON = "Dibatalkan pelanggan dari web chat"
PRIVACY_NOTICE_VERSION = "2026-11-20"


# Scope ----------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChatScope:
    """One entry point of the chat: the outlet link (`table_id` None) or one table's QR."""

    tenant_id: UUID
    outlet_id: UUID
    outlet_name: str
    timezone: str
    unpaid_timeout_minutes: int
    has_qris: bool
    delivery_fee: int = 0
    reservations_enabled: bool = False
    table_id: UUID | None = None
    table_name: str | None = None
    area: str | None = None

    def actor(self) -> ActorContext:
        return ActorContext.for_system(self.tenant_id)

    @property
    def channel(self) -> Channel:
        return "web_table" if self.table_id is not None else "web_online"

    @property
    def web_ordering(self) -> bool:
        """Web chat orders are paid with the outlet's static QRIS, so they need one (FR2.13);
        without it the menu shows "Pesan di kasir"."""
        return self.has_qris


async def resolve_slug(conn: AsyncConnection, slug: str) -> ChatScope | None:
    """No tenant context is needed (definer function). None = unknown or old slug (C13)."""
    slug = slug.lower()
    if not SLUG_PATTERN.match(slug):
        return None
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute("select * from app.resolve_outlet_slug(%s)", (slug,))
    row = await cur.fetchone()
    if row is None:
        return None
    return ChatScope(
        tenant_id=row["tenant_id"],
        outlet_id=row["outlet_id"],
        outlet_name=row["outlet_name"],
        timezone=row["timezone"],
        unpaid_timeout_minutes=row["unpaid_timeout_minutes"],
        has_qris=row["has_qris"],
        delivery_fee=row["delivery_fee"],
        reservations_enabled=row["reservations_enabled"],
    )


def new_access_key() -> str:
    return secrets.token_urlsafe(24)


def hash_key(key: str) -> str:
    return crypto.sha256_hex(key)


CLIENT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def check_client_key(key: str | None) -> str | None:
    """An access key the chat page created itself (sent as `X-Order-Key` / `X-Booking-Key` when
    creating): random, URL-safe, at least 32 characters."""
    if key is None or key == "":
        return None
    if not CLIENT_KEY_PATTERN.match(key):
        raise ValidationFailedError(
            "the access key must be 32-128 URL-safe characters", {"field": "access_key"}
        )
    return key


async def replace_order_key(
    conn: AsyncConnection, scope: ChatScope, order_id: UUID, key_hash: str
) -> None:
    """A replayed create without a page-made key gets a new key (the old one is not stored)."""
    await conn.execute(
        "update app.orders set access_key_hash = %s where id = %s and outlet_id = %s"
        " and channel = %s",
        (key_hash, order_id, scope.outlet_id, scope.channel),
    )


def short_name(name: str) -> str:
    """Initials for the outlet avatar in the chat header (C1): "Kopi Senja Dago" → "KS"."""
    # Only words that start with a letter or digit: an en dash between words is skipped.
    words = [w for w in re.split(r"\s+", name.strip()) if w and w[0].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


# C1 greeting ----------------------------------------------------------------------------------


async def outlet_info(conn: AsyncConnection, scope: ChatScope) -> dict[str, Any]:
    """Name, opening hours (ISO weekday → "08:00-22:00"), and whether it is open right now."""
    cur = await conn.execute(
        "select weekday, opens_at, closes_at from app.outlet_opening_hours"
        " where outlet_id = %s order by weekday",
        (scope.outlet_id,),
    )
    rows = await cur.fetchall()
    now = datetime.now(ZoneInfo(scope.timezone))
    hours = [
        {"weekday": wd, "opens_at": o.strftime("%H:%M"), "closes_at": c.strftime("%H:%M")}
        for wd, o, c in rows
    ]
    return {
        "name": scope.outlet_name,
        "short_name": short_name(scope.outlet_name),
        "timezone": scope.timezone,
        "opening_hours": hours,
        "is_open_now": _is_open(rows, now) if rows else None,
    }


def _is_open(rows: list[tuple[int, Any, Any]], now: datetime) -> bool:
    """Open now, including a night that runs past midnight from the previous day."""
    today, t = now.isoweekday(), now.time()
    yesterday = 7 if today == 1 else today - 1
    for wd, opens, closes in rows:
        overnight = closes <= opens
        if wd == today and (opens <= t < closes if not overnight else t >= opens):
            return True
        if wd == yesterday and overnight and t < closes:
            return True
    return False


# Unpaid timeout (lazy, FR10.4) ------------------------------------------------------------------


async def expire_unpaid(conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID) -> int:
    """Cancel this outlet's web chat orders still unpaid past the limit; stock returns. Orders
    whose customer tapped "Saya sudah bayar" wait for staff instead."""
    cur = await conn.execute(
        """
        select o.id from app.orders o join app.outlets ou on ou.id = o.outlet_id
        where o.outlet_id = %s and o.channel in ('web_table', 'web_online')
          and o.status = 'pending_payment' and o.payment_status = 'unpaid'
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


# Customer details (FR12.1) ----------------------------------------------------------------------


def phone_index(phone: str) -> str:
    """Blind index of a cleaned phone number (customers and bookings share it)."""
    return crypto.blind_index(phone, "phone")


def clean_phone(phone: str) -> str:
    """ "0812-3456 7890" → "081234567890"; refuses anything that is not a phone number."""
    digits = re.sub(r"[\s().-]", "", phone or "")
    if not PHONE_PATTERN.match(digits):
        raise ValidationFailedError("phone number is not valid", {"field": "phone"})
    return digits


async def record_customer(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    *,
    name: str,
    phone: str | None,
    notice_version: str | None,
) -> UUID:
    """One customer row per order or booking (no profile across visits, FR12.3), with the
    privacy notice version the chat showed before the details were sent (FR12.1)."""
    if notice_version != PRIVACY_NOTICE_VERSION:
        raise ValidationFailedError(
            "show the current privacy notice first", {"field": "privacy_notice_version"}
        )
    cur = await conn.execute(
        "insert into app.customers (tenant_id, outlet_id, name, phone, phone_index)"
        " values (%s, %s, %s, %s, %s) returning id",
        (
            ctx.tenant_id,
            outlet_id,
            crypto.encrypt(name, "customers.name"),
            crypto.encrypt(phone, "customers.phone"),
            phone_index(phone) if phone else None,
        ),
    )
    customer_id: UUID = (await cur.fetchone())[0]  # type: ignore[index]
    await conn.execute(
        "insert into app.privacy_notice_acknowledgements"
        " (tenant_id, outlet_id, customer_id, notice_version) values (%s, %s, %s, %s)",
        (ctx.tenant_id, outlet_id, customer_id, notice_version),
    )
    return customer_id


# Orders ---------------------------------------------------------------------------------------


_WEB_ORDER_SQL = """
select id, status::text as status, payment_status::text as payment_status, created_at, updated_at
from app.orders
where id = %s and outlet_id = %s and table_id is not distinct from %s and channel = %s
  and access_key_hash = %s
"""


async def _web_order(
    conn: AsyncConnection, scope: ChatScope, order_id: UUID, key: str | None, *, lock: bool = False
) -> dict[str, Any]:
    """The order, only when it was placed from this scope with this key and is still readable.
    Anything else is `not_found` with no data (ACN6)."""
    if not key:
        raise NotFoundError("order")
    cur = conn.cursor(row_factory=dict_row)
    sql = _WEB_ORDER_SQL + (" for update" if lock else "")
    await cur.execute(
        sql, (order_id, scope.outlet_id, scope.table_id, scope.channel, hash_key(key))
    )
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
    conn: AsyncConnection, ctx: ActorContext, scope: ChatScope, draft: orders.WebOrder
) -> dict[str, Any]:
    if not scope.web_ordering:
        raise ConflictError(
            "web_ordering_unavailable", "this outlet takes orders at the counter only"
        )
    created = await orders.create_web_order(conn, ctx, scope.outlet_id, draft)
    cur = await conn.execute("select created_at from app.orders where id = %s", (created["id"],))
    created_at = (await cur.fetchone())[0]  # type: ignore[index]
    created["pay_by"] = created_at + timedelta(minutes=scope.unpaid_timeout_minutes)
    return created


async def order_status(
    conn: AsyncConnection, scope: ChatScope, order_id: UUID, key: str | None
) -> dict[str, Any]:
    """C6/C7: what the phone that placed the order may see — no staff names, no other orders."""
    await _web_order(conn, scope, order_id, key)
    detail = await orders.detail(conn, order_id)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select o.type::text as type, o.delivery_address, o.delivery_fee"
        " from app.orders o where o.id = %s",
        (order_id,),
    )
    extra = await cur.fetchone()
    assert extra is not None  # noqa: S101 - just read above
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
        "fulfillment": extra["type"],
        "customer_name": detail["customer_name"],
        # Cleared by the anonymization trigger once the order is finished (FR12.2).
        "delivery_address": crypto.decrypt(extra["delivery_address"], "orders.delivery_address"),
        "note": detail["note"],
        "status": detail["status"],
        "payment_status": detail["payment_status"],
        "claimed_at": claimed_at,
        "pay_by": detail["created_at"] + timedelta(minutes=scope.unpaid_timeout_minutes),
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
        "delivery_fee": extra["delivery_fee"],
        "total": detail["total"],
        "reject_reason": proof["rejection_reason"] if rejected else None,
        "cancel_reason": None if rejected else cancel_reason,
        "events": events,
        "timezone": scope.timezone,
    }


async def orders_overview(
    conn: AsyncConnection, scope: ChatScope, refs: list[tuple[UUID, str]]
) -> list[dict[str, Any]]:
    """C1 "Pesanan Saya": the orders this phone kept keys for, still readable. Unknown, wrong,
    or expired keys are left out silently (FR2.15)."""
    out = []
    cur = conn.cursor(row_factory=dict_row)
    for order_id, key in refs:
        try:
            await _web_order(conn, scope, order_id, key)
        except NotFoundError:
            continue
        await cur.execute(
            "select o.id as order_id, ou.order_prefix, o.order_no, o.type::text as fulfillment,"
            " o.status::text as status, o.payment_status::text as payment_status, o.total,"
            " o.created_at from app.orders o join app.outlets ou on ou.id = o.outlet_id"
            " where o.id = %s",
            (order_id,),
        )
        row = await cur.fetchone()
        if row is None:
            continue
        row["order_no"] = orders.order_label(row.pop("order_prefix"), row["order_no"])
        out.append(row)
    out.sort(key=lambda r: r["created_at"], reverse=True)
    return out


async def claim_payment(
    conn: AsyncConnection, ctx: ActorContext, scope: ChatScope, order_id: UUID, key: str | None
) -> None:
    """C6 "Saya sudah bayar": a proof without a screenshot, reviewed in S4 like any other."""
    row = await _web_order(conn, scope, order_id, key, lock=True)
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
        (ctx.tenant_id, scope.outlet_id, order_id),
    )
    await conn.execute(
        "update app.orders set payment_status = 'proof_submitted' where id = %s", (order_id,)
    )
    await orders.record_event(
        conn,
        ctx,
        {"id": order_id, "outlet_id": scope.outlet_id},
        "payment_changed",
        from_payment="unpaid",
        to_payment="proof_submitted",
        data={"kind": "customer_claim"},
    )


async def customer_cancel(
    conn: AsyncConnection, ctx: ActorContext, scope: ChatScope, order_id: UUID, key: str | None
) -> None:
    """C6 "Batalkan pesanan": only before "Saya sudah bayar"; afterwards staff decide."""
    row = await _web_order(conn, scope, order_id, key, lock=True)
    if row["status"] == "cancelled":
        return  # idempotent: a retry after a lost connection
    if row["status"] != "pending_payment" or row["payment_status"] != "unpaid":
        raise ConflictError(
            "order_not_cancellable",
            "the order can no longer be cancelled here; ask the staff",
            {"status": row["status"], "payment_status": row["payment_status"]},
        )
    await orders.cancel(conn, ctx, order_id, CUSTOMER_CANCEL_REASON)


# Chat session (FR6.2) ---------------------------------------------------------------------------


def check_session(session: str | None) -> str:
    if not session or not SESSION_PATTERN.match(session):
        raise ValidationFailedError("X-Chat-Session is missing or invalid", {"field": "session"})
    return hash_key(session)


_EMPTY_CART: dict[str, Any] = {"lines": []}
# Serialized cart limit (JSON text). The column check (64 KB) leaves room, so a cart that
# passes here never trips the database constraint.
MAX_CART_BYTES = 16_000


def check_cart_size(cart: dict[str, Any]) -> None:
    size = len(json.dumps(cart, separators=(",", ":")).encode())
    if size > MAX_CART_BYTES:
        raise ValidationFailedError("the cart is too large", {"field": "cart"})


async def get_session(
    conn: AsyncConnection, ctx: ActorContext, scope: ChatScope, session: str
) -> dict[str, Any]:
    """Resume the chat. A cart idle for 2 hours comes back empty with `cart_expired` (C13)."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, step, cart, fulfillment, last_activity_at from app.chat_sessions"
        " where outlet_id = %s and table_id is not distinct from %s and session_key_hash = %s"
        " for update",
        (scope.outlet_id, scope.table_id, session),
    )
    row = await cur.fetchone()
    if row is None:
        return {
            "step": "main_menu",
            "cart": _EMPTY_CART,
            "fulfillment": None,
            "last_activity_at": None,
            "cart_expired": False,
        }
    expired = (
        bool(row["cart"].get("lines")) and row["last_activity_at"] < datetime.now(UTC) - CART_IDLE
    )
    if expired:
        await conn.execute(
            "update app.chat_sessions set cart = %s, step = 'main_menu', fulfillment = null"
            " where id = %s",
            (Jsonb(_EMPTY_CART), row["id"]),
        )
        row = {**row, "cart": _EMPTY_CART, "step": "main_menu", "fulfillment": None}
    return {
        "step": row["step"],
        "cart": row["cart"],
        "fulfillment": row["fulfillment"],
        "last_activity_at": row["last_activity_at"],
        "cart_expired": expired,
    }


async def purge_idle_sessions(conn: AsyncConnection, outlet_id: UUID, limit: int = 200) -> int:
    """Delete this outlet's sessions idle for more than 2 hours: their cart would be emptied
    and the step reset anyway, so nothing is lost. Runs when a session is saved (no poller
    yet), a bounded batch at a time."""
    cur = await conn.execute(
        "delete from app.chat_sessions where id in ("
        " select id from app.chat_sessions where outlet_id = %s and last_activity_at < %s"
        " order by last_activity_at limit %s for update skip locked)",
        (outlet_id, datetime.now(UTC) - CART_IDLE, limit),
    )
    return cur.rowcount


async def put_session(
    conn: AsyncConnection,
    ctx: ActorContext,
    scope: ChatScope,
    session: str,
    *,
    step: str,
    cart: dict[str, Any],
    fulfillment: str | None,
) -> dict[str, Any]:
    if scope.table_id is not None:
        fulfillment = None  # a table order is always dine-in
    await purge_idle_sessions(conn, scope.outlet_id)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        insert into app.chat_sessions (tenant_id, outlet_id, table_id, session_key_hash, step,
                                       cart, fulfillment)
        values (%s, %s, %s, %s, %s, %s, %s)
        on conflict (outlet_id, table_id, session_key_hash) do update
          set step = excluded.step, cart = excluded.cart, fulfillment = excluded.fulfillment,
              last_activity_at = now()
        returning step, cart, fulfillment, last_activity_at
        """,
        (
            ctx.tenant_id,
            scope.outlet_id,
            scope.table_id,
            session,
            step,
            Jsonb(cart),
            fulfillment,
        ),
    )
    row = await cur.fetchone()
    assert row is not None  # noqa: S101
    return {**row, "cart_expired": False}
