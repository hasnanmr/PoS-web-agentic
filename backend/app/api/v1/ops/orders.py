"""Orders for owner and staff — S1/M2 Counter, S2/M1 Order Board, S3 Detail & Reversal.

T-026 to T-032, T-038, T-067, T-068. Contract: docs/architecture/screen-endpoint-map.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Header, Query, Request, Response, status
from pydantic import BaseModel, Field

from app import db
from app.api.errors import ApiError
from app.api.photos import attach_photo_urls
from app.auth.deps import TenantUser
from app.core import catalog, idempotency, orders, outlets, web_chat
from app.core.actor import ActorContext
from app.core.orders import CounterOrder
from app.core.payments import PaymentInput
from app.core.pricing import LineInput, outlet_pb1, quote
from app.core.tax import quote_totals

router = APIRouter(prefix="/api/v1/ops", tags=["ops: orders"])

IdempotencyKey = Header(default=None, alias="Idempotency-Key")


# Schemas -------------------------------------------------------------------------------


class MenuOption(BaseModel):
    id: UUID
    name: str
    price: int
    available: bool


class MenuGroup(BaseModel):
    id: UUID
    name: str
    selection: Literal["single", "multiple"]
    is_required: bool
    options: list[MenuOption]


class MenuItem(BaseModel):
    product_id: UUID
    name: str
    category: str | None
    description: str | None = Field(default=None, description="C2 menu card (web chat)")
    is_owner_pick: bool
    price: int
    photo_url: str | None
    sold_out: bool
    sold_out_reason: str | None
    addon_groups: list[MenuGroup]


class OpenBillRef(BaseModel):
    id: UUID
    total: int


class TableRow(BaseModel):
    id: UUID
    name: str
    area: str | None
    open_bill: OpenBillRef | None


class LineIn(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=999)
    addon_option_ids: list[UUID] = Field(default_factory=list, max_length=30)
    note: str | None = Field(default=None, max_length=200)


class QuoteRequest(BaseModel):
    type: Literal["dine_in", "takeaway"] = "takeaway"
    items: list[LineIn] = Field(min_length=1, max_length=100)


class QuoteLine(BaseModel):
    product_id: UUID
    name: str
    unit_price: int
    quantity: int
    addons: list[dict[str, Any]]
    line_total: int


class QuoteResponse(BaseModel):
    lines: list[QuoteLine]
    subtotal: int
    pb1_rate_bps: int | None
    pb1_amount: int
    total: int


class PaymentIn(BaseModel):
    method: Literal["cash", "qris"] | None = None
    cash_received: int | None = Field(default=None, ge=0, le=1_000_000_000)
    drawer_id: UUID | None = None
    to_open_bill: bool = False


class OrderCreate(BaseModel):
    type: Literal["dine_in", "takeaway"]
    table_id: UUID | None = None
    items: list[LineIn] = Field(min_length=1, max_length=100)
    payment: PaymentIn


class OrderCreated(BaseModel):
    id: UUID
    order_no: str
    status: str
    payment_status: str
    subtotal: int
    pb1_amount: int
    total: int
    change_due: int | None
    bill_id: UUID | None


class OrderCard(BaseModel):
    id: UUID
    order_no: str
    channel: str
    type: str
    payment_mode: str
    status: str
    payment_status: str
    payment_method: str | None
    payment_id: UUID | None
    qris_checked: bool | None = Field(
        description="QRIS payments only: found in the receiving account (S2 Cek →); else null"
    )
    table: str | None
    customer_name: str | None
    note: str | None = Field(description='Web orders: "Catatan untuk dapur"')
    proof_id: UUID | None = Field(description="Pending payment proof to review in S4")
    payment_claimed_at: datetime | None = Field(
        description='Web orders: "Pelanggan bilang sudah bayar · 12:44" (no screenshot)'
    )
    item_summary: str
    total: int
    bill_id: UUID | None
    created_at: datetime
    auto_cancel_at: datetime | None
    allowed_actions: list[str]


class Board(BaseModel):
    awaiting_payment: list[OrderCard]
    confirmed: list[OrderCard]
    preparing: list[OrderCard]
    ready: list[OrderCard]
    done_today: list[OrderCard]


class OrderItemOut(BaseModel):
    id: UUID
    product_id: UUID
    name: str
    unit_price: int
    quantity: int
    line_total: int
    note: str | None
    addons: list[dict[str, Any]]


class OrderEventOut(BaseModel):
    at: datetime
    kind: str
    from_: str | None = Field(alias="from")
    to: str | None
    from_payment: str | None
    to_payment: str | None
    reason: str | None
    data: dict[str, Any]
    actor: dict[str, Any]

    model_config = {"populate_by_name": True}


class OrderDetail(OrderCard):
    items: list[OrderItemOut]
    subtotal: int
    pb1_rate_bps: int | None
    pb1_amount: int
    delivery_fee: int
    timezone: str
    events: list[OrderEventOut]
    refund: dict[str, Any] | None = None


class TransitionIn(BaseModel):
    to_status: Literal["confirmed", "preparing", "ready", "out_for_delivery", "served", "completed"]


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class ReversalIn(BaseModel):
    reason: str = Field(max_length=300)
    ingredients: Literal["waste", "return"] | None = None


def _lines(items: list[LineIn]) -> list[LineInput]:
    return [LineInput(i.product_id, i.quantity, tuple(i.addon_option_ids), i.note) for i in items]


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


# Counter (S1) ----------------------------------------------------------------------------


@router.get("/outlets/{outlet_id}/menu")
async def counter_menu(
    outlet_id: UUID,
    request: Request,
    user: TenantUser,
    q: str | None = Query(default=None, max_length=60),
    category: str | None = None,
    owner_picks: bool = False,
) -> list[MenuItem]:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        rows = await catalog.counter_menu(
            conn, outlet_id, q=q, category=category, owner_picks=owner_picks
        )
    await attach_photo_urls(request, rows)
    return [MenuItem(**r) for r in rows]


@router.get("/outlets/{outlet_id}/tables")
async def tables(outlet_id: UUID, request: Request, user: TenantUser) -> list[TableRow]:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        rows = await catalog.tables_with_bills(conn, outlet_id)
        setting = await outlet_pb1(conn, outlet_id)
    return [
        TableRow(
            id=r["id"],
            name=r["name"],
            area=r["area"],
            open_bill=OpenBillRef(
                id=r["bill_id"], total=quote_totals(int(r["bill_subtotal"]), setting).total
            )
            if r["bill_id"]
            else None,
        )
        for r in rows
    ]


@router.post("/outlets/{outlet_id}/quotes")
async def create_quote(
    outlet_id: UUID, body: QuoteRequest, request: Request, user: TenantUser
) -> QuoteResponse:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        priced = await quote(conn, outlet_id, _lines(body.items))
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


@router.post("/outlets/{outlet_id}/orders", status_code=status.HTTP_201_CREATED)
async def create_order(
    outlet_id: UUID,
    body: OrderCreate,
    request: Request,
    response: Response,
    user: TenantUser,
    idempotency_key: str | None = IdempotencyKey,
) -> OrderCreated:
    key = idempotency.check_key(idempotency_key)
    scope = f"order.create:{outlet_id}"
    fp = idempotency.fingerprint(str(outlet_id), body.model_dump(mode="json"))
    ctx = user.actor()
    pay = body.payment
    draft = CounterOrder(
        type=body.type,
        lines=_lines(body.items),
        table_id=body.table_id,
        payment=PaymentInput(pay.method, pay.cash_received, pay.drawer_id) if pay.method else None,
        to_open_bill=pay.to_open_bill,
    )
    try:
        async with db.transaction(_pool(request), ctx) as conn:
            cached = await idempotency.lookup(conn, ctx, scope, key, fp)
            if cached is not None:
                response.status_code = status.HTTP_200_OK  # a replay, not a new order
                response.headers["Idempotent-Replay"] = "true"
                return OrderCreated(**cached)
            await outlets.require_outlet(conn, outlet_id)
            created = OrderCreated(**await orders.create_counter_order(conn, ctx, outlet_id, draft))
            await idempotency.store(conn, ctx, scope, key, fp, created.model_dump(mode="json"))
    except psycopg.errors.UniqueViolation as exc:
        if "idempotency_keys" in str(exc):
            raise ApiError(409, "conflict", "the same request is already being processed") from None
        raise
    return created


# Board and detail (S2, S3) -----------------------------------------------------------------


@router.get("/outlets/{outlet_id}/orders/board")
async def order_board(
    outlet_id: UUID,
    request: Request,
    user: TenantUser,
    channel: Literal["counter", "whatsapp_online", "whatsapp_table", "web_table", "web_online"]
    | None = None,
    type: Literal["dine_in", "takeaway", "delivery", "pickup"] | None = None,
    q: str | None = Query(default=None, max_length=60),
) -> Board:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
    # Unpaid web orders past the outlet's limit are cancelled by the system first (FR10.4; no
    # poller yet), so the board never shows an order the customer can no longer pay.
    system = ActorContext.for_system(user.tenant_id)
    async with db.transaction(_pool(request), system) as conn:
        await web_chat.expire_unpaid(conn, system, outlet_id)
    async with db.transaction(_pool(request), user.actor()) as conn:
        columns = await orders.board(conn, outlet_id, channel=channel, type=type, q=q)
    return Board(**columns)


@router.get("/orders/{order_id}")
async def order_detail(order_id: UUID, request: Request, user: TenantUser) -> OrderDetail:
    async with db.transaction(_pool(request), user.actor()) as conn:
        row = await orders.detail(conn, order_id)
    return OrderDetail(**row)


@router.post("/orders/{order_id}/transitions")
async def order_transition(
    order_id: UUID, body: TransitionIn, request: Request, user: TenantUser
) -> OrderDetail:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        row = await orders.transition(conn, ctx, order_id, body.to_status)
    return OrderDetail(**row)


@router.post("/orders/{order_id}/cancel")
async def order_cancel(
    order_id: UUID, body: CancelIn, request: Request, user: TenantUser
) -> OrderDetail:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        row = await orders.cancel(conn, ctx, order_id, body.reason)
    return OrderDetail(**row)


@router.post("/orders/{order_id}/reversal")
async def order_reversal(
    order_id: UUID, body: ReversalIn, request: Request, user: TenantUser
) -> OrderDetail:
    if not body.reason.strip():
        raise ApiError(422, "reason_required", "a reason is required for a reversal")
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        row = await orders.reverse(conn, ctx, order_id, body.reason, body.ingredients)
    return OrderDetail(**row)
