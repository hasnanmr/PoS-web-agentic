"""Customer table web page — wireframes Q0-Q5 (T-134, issue #44).

Contract: docs/architecture/screen-endpoint-map.md → "Customer table web page (Q0-Q5)". No sign-in:
the table token in the path is the only credential, plus the per-order access key
(`X-Order-Key`) for anything about one order. Unknown or replaced tokens are `table_qr_invalid`
(404, page Q0). Web orders are always paid first with the outlet's static QRIS.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from app import db
from app.api.errors import ApiError
from app.api.photos import attach_photo_urls
from app.api.v1.ops.orders import LineIn, MenuItem, QuoteLine, QuoteResponse
from app.core import catalog, idempotency, orders, qris
from app.core import table_qr as core
from app.core.pricing import LineInput, quote

router = APIRouter(prefix="/api/v1/public/t", tags=["public: table web page (Q0-Q5)"])

OrderKey = Header(default=None, alias="X-Order-Key")


def _pool(request: Request) -> Any:
    pool = request.app.state.db_pool
    if pool is None:
        raise ApiError(503, "database_not_configured", "database is not configured")
    return pool


# Rate limit: per token and per client address, per API process (like the tablet pairing limit).
_WINDOW_SECONDS = 60
_LIMIT_PER_CLIENT = 120
_LIMIT_PER_TOKEN = 300
_hits: dict[str, deque[float]] = {}


def _client(request: Request) -> str:
    forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
    if forwarded[-1]:
        return forwarded[-1]
    return request.client.host if request.client else "?"


def _rate_limit(key: str, limit: int) -> None:
    now = time.monotonic()
    hits = _hits.setdefault(key, deque())
    while hits and hits[0] < now - _WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= limit:
        raise ApiError(429, "too_many_requests", "too many requests; wait a moment")
    hits.append(now)
    if len(_hits) > 10_000:  # keep memory bounded
        for k in [k for k, v in _hits.items() if not v or v[-1] < now - _WINDOW_SECONDS]:
            del _hits[k]


async def current_table(token: str, request: Request) -> core.TableRef:
    _rate_limit(f"ip:{_client(request)}", _LIMIT_PER_CLIENT)
    _rate_limit(f"token:{token}", _LIMIT_PER_TOKEN)
    async with _pool(request).connection() as conn, conn.transaction():
        ref = await core.resolve(conn, token)
    if ref is None:
        raise ApiError(404, "table_qr_invalid", "QR ini sudah tidak berlaku")
    # Unpaid web orders past the outlet's limit are cancelled before anything is read (FR10.4).
    async with db.transaction(_pool(request), ref.actor()) as conn:
        await core.expire_unpaid(conn, ref.actor(), ref.outlet_id)
    return ref


Table = Annotated[core.TableRef, Depends(current_table)]


# Schemas ----------------------------------------------------------------------------------


class OutletOut(BaseModel):
    name: str
    timezone: str


class TableOut(BaseModel):
    name: str
    area: str | None


class TablePage(BaseModel):
    outlet: OutletOut
    table: TableOut
    target: Literal["web_whatsapp", "web", "whatsapp"] = Field(
        description="Effective: web while WhatsApp isn't connected"
    )
    web_ordering: bool = Field(description="False without a static QRIS: menu only")
    whatsapp_url: str | None


class WebQuoteIn(BaseModel):
    items: list[LineIn] = Field(min_length=1, max_length=50)


class WebOrderIn(BaseModel):
    items: list[LineIn] = Field(min_length=1, max_length=50)
    note: str | None = Field(default=None, max_length=200)
    customer_name: str | None = Field(default=None, max_length=40)
    expected_total: int | None = Field(
        default=None, ge=0, description="Total the page showed; `price_changed` if it differs"
    )

    @field_validator("note", "customer_name")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


class WebOrderCreated(BaseModel):
    order_id: UUID
    access_key: str = Field(description="Keep on the phone; send as `X-Order-Key`")
    order_no: str
    status: str
    payment_status: str
    subtotal: int
    pb1_amount: int
    total: int
    pay_by: datetime


class StatusItem(BaseModel):
    name: str
    quantity: int
    addons: list[str]
    line_total: int


class StatusEvent(BaseModel):
    status: str
    at: datetime


class WebOrderStatus(BaseModel):
    id: UUID
    order_no: str
    created_at: datetime
    customer_name: str | None
    note: str | None
    status: str
    payment_status: str
    claimed_at: datetime | None
    pay_by: datetime
    items: list[StatusItem]
    subtotal: int
    pb1_amount: int
    total: int
    reject_reason: str | None
    cancel_reason: str | None
    events: list[StatusEvent]
    timezone: str


# Q1 · Q2 ----------------------------------------------------------------------------------


@router.get("/{token}")
async def table_page(table: Table) -> TablePage:
    """Q1: the outlet and table, where the QR leads, and the WhatsApp link when allowed."""
    return TablePage(
        outlet=OutletOut(name=table.outlet_name, timezone=table.timezone),
        table=TableOut(name=table.table_name, area=table.area),
        target=table.effective_target,
        web_ordering=table.web_ordering,
        whatsapp_url=table.whatsapp_url,
    )


@router.get("/{token}/menu")
async def menu(table: Table, request: Request) -> list[MenuItem]:
    """Q2/Q2a: the outlet's active menu with prices, add-ons and sold-out state."""
    async with db.transaction(_pool(request), table.actor()) as conn:
        rows = await catalog.counter_menu(conn, table.outlet_id)
    await attach_photo_urls(request, rows)
    return [MenuItem(**r) for r in rows]


# Q3 · Q4 · Q5 -----------------------------------------------------------------------------


@router.post("/{token}/quote")
async def web_quote(body: WebQuoteIn, table: Table, request: Request) -> QuoteResponse:
    """Q3 totals before ordering (subtotal, PB1, total), priced by the server like S1."""
    async with db.transaction(_pool(request), table.actor()) as conn:
        priced = await quote(
            conn,
            table.outlet_id,
            [
                LineInput(i.product_id, i.quantity, tuple(i.addon_option_ids), i.note)
                for i in body.items
            ],
        )
    return QuoteResponse(
        lines=[
            QuoteLine(
                product_id=line.product_id,
                name=line.name,
                unit_price=line.unit_price,
                quantity=line.quantity,
                line_total=line.line_total,
                addons=[{"id": a.option_id, "name": a.name, "price": a.price} for a in line.addons],
            )
            for line in priced.lines
        ],
        subtotal=priced.quote.subtotal,
        pb1_rate_bps=priced.quote.pb1_rate_bps,
        pb1_amount=priced.quote.pb1_amount,
        total=priced.quote.total,
    )


@router.post("/{token}/orders", status_code=status.HTTP_201_CREATED)
async def place_order(
    body: WebOrderIn,
    table: Table,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> WebOrderCreated:
    """Q3 "Pesan & bayar": a pay-first dine-in order for this table (stock deducted)."""
    key = idempotency.check_key(idempotency_key)
    if key is None:
        raise ApiError(422, "validation_failed", "Idempotency-Key is required")
    scope = f"web_order.create:{table.table_id}"
    fp = idempotency.fingerprint(str(table.table_id), body.model_dump(mode="json"))
    ctx = table.actor()
    access_key = core.new_access_key()
    draft = orders.WebOrder(
        table_id=table.table_id,
        lines=[
            LineInput(i.product_id, i.quantity, tuple(i.addon_option_ids), i.note)
            for i in body.items
        ],
        access_key_hash=core.hash_key(access_key),
        note=body.note,
        customer_name=body.customer_name,
        expected_total=body.expected_total,
    )
    try:
        async with db.transaction(_pool(request), ctx) as conn:
            cached = await idempotency.lookup(conn, ctx, scope, key, fp)
            if cached is not None:
                response.status_code = status.HTTP_200_OK
                response.headers["Idempotent-Replay"] = "true"
                return WebOrderCreated(**cached)
            created = await core.place_order(conn, ctx, table, draft)
            out = WebOrderCreated(
                order_id=created["id"],
                access_key=access_key,
                order_no=created["order_no"],
                status=created["status"],
                payment_status=created["payment_status"],
                subtotal=created["subtotal"],
                pb1_amount=created["pb1_amount"],
                total=created["total"],
                pay_by=created["pay_by"],
            )
            await idempotency.store(conn, ctx, scope, key, fp, out.model_dump(mode="json"))
    except psycopg.errors.UniqueViolation as exc:
        if "idempotency_keys" in str(exc):
            raise ApiError(409, "conflict", "the same request is already being processed") from None
        raise
    return out


@router.get("/{token}/orders/{order_id}")
async def order_status(
    order_id: UUID, table: Table, request: Request, order_key: str | None = OrderKey
) -> WebOrderStatus:
    """Q5 (and Q4 on reload): only with the order's access key."""
    async with db.transaction(_pool(request), table.actor()) as conn:
        row = await core.order_status(conn, table, order_id, order_key)
    return WebOrderStatus(**row)


@router.get("/{token}/orders/{order_id}/qris")
async def order_qris(
    order_id: UUID, table: Table, request: Request, order_key: str | None = OrderKey
) -> Response:
    """Q4: the outlet's static QRIS image (same as O3 / the S1 popup)."""
    async with db.transaction(_pool(request), table.actor()) as conn:
        await core.order_status(conn, table, order_id, order_key)
        content_type, data = await qris.image(conn, table.outlet_id)
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "no-store"})


@router.post("/{token}/orders/{order_id}/payment-claim")
async def payment_claim(
    order_id: UUID, table: Table, request: Request, order_key: str | None = OrderKey
) -> WebOrderStatus:
    """Q4 "Saya sudah bayar": staff check the merchant account and confirm in S2/S4."""
    ctx = table.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await core.claim_payment(conn, ctx, table, order_id, order_key)
        row = await core.order_status(conn, table, order_id, order_key)
    return WebOrderStatus(**row)


@router.post("/{token}/orders/{order_id}/cancel")
async def cancel(
    order_id: UUID, table: Table, request: Request, order_key: str | None = OrderKey
) -> WebOrderStatus:
    """Q4 "Batalkan pesanan": only before "Saya sudah bayar"; stock returns."""
    ctx = table.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await core.customer_cancel(conn, ctx, table, order_id, order_key)
        row = await core.order_status(conn, table, order_id, order_key)
    return WebOrderStatus(**row)
