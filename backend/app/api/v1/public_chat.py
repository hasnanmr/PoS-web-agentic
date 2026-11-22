"""Customer web chat endpoints shared by both scopes — page 07 (C1-C9, T-049, T-055, T-036).

Contract: docs/architecture/screen-endpoint-map.md → "Customer web chat (C1-C15)". The outlet
link (`/public/o/{slug}`, `public_outlet.py`) and the table QR (`/public/t/{token}`,
`public_table.py`) each resolve their scope in a dependency and register the same routes here:
menu, quote, chat session, Pesanan Saya, order status, QRIS, Saya sudah bayar, cancel,
recommendation cards, and the agent (C9 AI, C14, C15). No sign-in: the slug or token is the only
credential, plus the per-order access key (`X-Order-Key`). Error codes are for the page only; it
shows friendly copy (C13).
"""

from __future__ import annotations

import time
from collections import OrderedDict, deque
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app import db
from app.api.errors import ApiError
from app.api.photos import attach_photo_urls
from app.api.v1.ops.orders import LineIn, MenuItem, QuoteLine
from app.core import catalog, idempotency, qris, recommendations, web_chat
from app.core.agent import gateway
from app.core.pricing import LineInput, PricedOrder, quote

OrderKey = Header(default=None, alias="X-Order-Key")
ChatSession = Header(default=None, alias="X-Chat-Session")


def pool(request: Request) -> Any:
    p = request.app.state.db_pool
    if p is None:
        raise ApiError(503, "database_not_configured", "database is not configured")
    return p


# Rate limits per API process (like the tablet pairing limit), per minute:
# - per chat session (`X-Chat-Session`, one per phone): the main budget. Status polls every 5 s
#   (C7, 12/min) plus taps fit easily;
# - per client address: high, because a cafe's customers often share one Wi-Fi address;
# - per scope (outlet link or table): only requests WITHOUT a chat session count, so a busy
#   outlet's polling customers never use up each other's budget.
_WINDOW_SECONDS = 60
_LIMIT_PER_SESSION = 120
_LIMIT_PER_CLIENT = 1200
_LIMIT_PER_SCOPE = 300
_MAX_KEYS = 10_000  # hard cap: the least recently used key is dropped first
_hits: OrderedDict[str, deque[float]] = OrderedDict()
# Agent messages per chat session per minute: each one costs model calls.
_AGENT_PER_SESSION = 10


def client_address(request: Request) -> str:
    forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
    if forwarded[-1]:
        return forwarded[-1]
    return request.client.host if request.client else "?"


def rate_limit(key: str, limit: int) -> None:
    now = time.monotonic()
    hits = _hits.get(key)
    if hits is None:
        hits = _hits[key] = deque()
        while len(_hits) > _MAX_KEYS:  # O(1) per dropped key, never a scan of every key
            _hits.popitem(last=False)
    else:
        _hits.move_to_end(key)
    while hits and hits[0] < now - _WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= limit:
        raise ApiError(429, "too_many_requests", "too many requests; wait a moment")
    hits.append(now)


def limit_scope(request: Request, scope_key: str) -> None:
    rate_limit(f"ip:{client_address(request)}", _LIMIT_PER_CLIENT)
    session = request.headers.get("x-chat-session")
    if session:
        rate_limit(f"session:{scope_key}:{session}", _LIMIT_PER_SESSION)
    else:
        rate_limit(f"scope:{scope_key}", _LIMIT_PER_SCOPE)


async def expire_unpaid(request: Request, scope: web_chat.ChatScope) -> None:
    """Unpaid orders past the outlet's limit are cancelled before anything is read (FR10.4)."""
    async with db.transaction(pool(request), scope.actor()) as conn:
        await web_chat.expire_unpaid(conn, scope.actor(), scope.outlet_id)


def lines(items: list[LineIn]) -> list[LineInput]:
    return [LineInput(i.product_id, i.quantity, tuple(i.addon_option_ids), i.note) for i in items]


# Schemas ----------------------------------------------------------------------------------


class OpeningHours(BaseModel):
    weekday: int = Field(description="ISO weekday, 1 = Monday")
    opens_at: str
    closes_at: str


class ChatOutlet(BaseModel):
    name: str
    short_name: str = Field(description="Initials for the chat avatar (C1)")
    timezone: str
    opening_hours: list[OpeningHours]
    is_open_now: bool | None = Field(description="None when no opening hours are set")


class PrivacyNotice(BaseModel):
    version: str = Field(description="Send back as `privacy_notice_version` with personal data")
    url: str


def privacy_notice() -> PrivacyNotice:
    # The full notice is a static page of the web chat build (T-106 publishes the legal text).
    return PrivacyNotice(version=web_chat.PRIVACY_NOTICE_VERSION, url="/privasi")


class ChatQuoteIn(BaseModel):
    items: list[LineIn] = Field(min_length=1, max_length=50)
    fulfillment: Literal["pickup", "delivery"] | None = Field(
        default=None, description="Outlet link only; a table order is always dine-in"
    )


class ChatQuote(BaseModel):
    lines: list[QuoteLine]
    subtotal: int
    pb1_rate_bps: int | None
    pb1_amount: int
    delivery_fee: int
    total: int


def quote_out(priced: PricedOrder) -> ChatQuote:
    return ChatQuote(
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
        delivery_fee=priced.quote.delivery_fee,
        total=priced.quote.total,
    )


class CartLine(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=99)
    addon_option_ids: list[UUID] = Field(default_factory=list, max_length=30)
    note: str | None = Field(default=None, max_length=200)


class Cart(BaseModel):
    lines: list[CartLine] = Field(default_factory=list, max_length=50)


class ChatSessionIn(BaseModel):
    step: str = Field(pattern=r"^[a-z0-9_.:-]{1,60}$", examples=["menu", "addons:<product_id>"])
    cart: Cart = Field(default_factory=Cart)
    fulfillment: Literal["pickup", "delivery"] | None = None


class ChatSessionOut(BaseModel):
    step: str
    cart: Cart
    fulfillment: Literal["pickup", "delivery"] | None
    last_activity_at: datetime | None
    cart_expired: bool = Field(description="True once after a 2-hour idle cart was emptied (C13)")


class OrderRef(BaseModel):
    order_id: UUID
    key: str = Field(min_length=8, max_length=200)


class OrdersStatusIn(BaseModel):
    orders: list[OrderRef] = Field(max_length=20)


class OrderOverview(BaseModel):
    order_id: UUID
    order_no: str
    fulfillment: Literal["dine_in", "takeaway", "pickup", "delivery"]
    status: str
    payment_status: str
    total: int
    created_at: datetime


class WebOrderCreated(BaseModel):
    order_id: UUID
    access_key: str = Field(description="Keep on the phone; send as `X-Order-Key`")
    order_no: str
    status: str
    payment_status: str
    subtotal: int
    pb1_amount: int
    delivery_fee: int = 0
    total: int
    pay_by: datetime


class StatusItem(BaseModel):
    name: str
    quantity: int
    addons: list[str]
    note: str | None = Field(description='Per-item "Catatan untuk dapur"')
    line_total: int


class StatusEvent(BaseModel):
    status: str
    at: datetime


class WebOrderStatus(BaseModel):
    id: UUID
    order_no: str
    created_at: datetime
    fulfillment: Literal["dine_in", "takeaway", "pickup", "delivery"]
    customer_name: str | None
    delivery_address: str | None = Field(description="Cleared once the order is finished")
    note: str | None
    status: str
    payment_status: str
    claimed_at: datetime | None
    pay_by: datetime
    items: list[StatusItem]
    subtotal: int
    pb1_amount: int
    delivery_fee: int
    total: int
    reject_reason: str | None
    cancel_reason: str | None
    events: list[StatusEvent]
    timezone: str


class RecommendationCard(BaseModel):
    product_id: UUID
    name: str
    description: str | None
    price: int
    photo_url: str | None
    badge: Literal["owner_pick", "best_seller"]


def _blank_to_none(v: str | None) -> str | None:
    return (v or "").strip() or None


class OrderTextFields(BaseModel):
    note: str | None = Field(default=None, max_length=200)
    expected_total: int | None = Field(
        default=None, ge=0, description="Total the page showed; `price_changed` if it differs"
    )

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


async def create_order(
    request: Request,
    response: Response,
    scope: web_chat.ChatScope,
    idempotency_key: str | None,
    client_key: str | None,
    body: BaseModel,
    build: Callable[[Any, str], Any],
) -> WebOrderCreated:
    """Shared "Pesan & bayar": idempotent per scope (FR6.4); `build(conn, key_hash)` returns
    the `orders.WebOrder` inside the transaction (so customer rows roll back with it).

    The access key is never stored in plaintext, not even in the idempotency cache (FR2.15):
    - the web chat creates the key itself and sends it as `X-Order-Key`; only its hash is
      stored, it is part of the request fingerprint, so a replay must carry the same key,
      and the response echoes it;
    - without `X-Order-Key` (the old Q3 page) the server makes one; a replay then gets a new
      key and the earlier one stops working, because the cache cannot return it."""
    key = idempotency.check_key(idempotency_key)
    if key is None:
        raise ApiError(422, "validation_failed", "Idempotency-Key is required")
    client_key = web_chat.check_client_key(client_key)
    scope_name = f"web_order.create:{scope.outlet_id}:{scope.table_id or 'online'}"
    fp = idempotency.fingerprint(
        str(scope.outlet_id),
        body.model_dump(mode="json"),
        web_chat.hash_key(client_key) if client_key else None,
    )
    ctx = scope.actor()
    access_key = client_key or web_chat.new_access_key()
    try:
        async with db.transaction(pool(request), ctx) as conn:
            cached = await idempotency.lookup(conn, ctx, scope_name, key, fp)
            if cached is not None:
                response.status_code = status.HTTP_200_OK
                response.headers["Idempotent-Replay"] = "true"
                if client_key is None:
                    await web_chat.replace_order_key(
                        conn, scope, UUID(cached["order_id"]), web_chat.hash_key(access_key)
                    )
                return WebOrderCreated(**{**cached, "access_key": access_key})
            draft = await build(conn, web_chat.hash_key(access_key))
            created = await web_chat.place_order(conn, ctx, scope, draft)
            out = WebOrderCreated(
                order_id=created["id"],
                access_key=access_key,
                order_no=created["order_no"],
                status=created["status"],
                payment_status=created["payment_status"],
                subtotal=created["subtotal"],
                pb1_amount=created["pb1_amount"],
                delivery_fee=created["delivery_fee"],
                total=created["total"],
                pay_by=created["pay_by"],
            )
            cache = {**out.model_dump(mode="json"), "access_key": ""}  # never the key itself
            await idempotency.store(conn, ctx, scope_name, key, fp, cache)
    except psycopg.errors.UniqueViolation as exc:
        if "idempotency_keys" in str(exc):
            raise ApiError(409, "conflict", "the same request is already being processed") from None
        raise
    return out


class AgentMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    context: Literal["recommend", "order", "book", "auto"] = Field(
        default="auto", description="Where the customer typed: C9, C14, C15, or the main menu"
    )


def agent_enabled(request: Request) -> bool:
    """C1/C8 `agent_enabled`: the text box talks to the agent only when a model is set up."""
    return request.app.state.agent_model is not None


# Shared routes ------------------------------------------------------------------------------


def register(router: APIRouter, param: str, current: Callable[..., Any]) -> None:
    """Add the routes both scopes share. `param` is the path parameter (`token` or `slug`) that
    the `current` dependency reads to resolve the scope."""
    Scope = Depends(current)  # noqa: N806
    base = f"/{{{param}}}"

    @router.get(f"{base}/menu")
    async def menu(request: Request, scope: web_chat.ChatScope = Scope) -> list[MenuItem]:
        """C2/C3: the outlet's active menu with prices, add-ons, and sold-out state."""
        async with db.transaction(pool(request), scope.actor()) as conn:
            rows = await catalog.counter_menu(conn, scope.outlet_id)
        await attach_photo_urls(request, rows)
        return [MenuItem(**r) for r in rows]

    @router.post(f"{base}/quote")
    async def chat_quote(
        body: ChatQuoteIn, request: Request, scope: web_chat.ChatScope = Scope
    ) -> ChatQuote:
        """C4 totals (subtotal, PB1, delivery fee, total), priced by the server."""
        fee = scope.delivery_fee if scope.table_id is None and body.fulfillment == "delivery" else 0
        async with db.transaction(pool(request), scope.actor()) as conn:
            priced = await quote(conn, scope.outlet_id, lines(body.items), delivery_fee=fee)
        return quote_out(priced)

    @router.get(f"{base}/chat-session")
    async def get_chat_session(
        request: Request,
        scope: web_chat.ChatScope = Scope,
        session: str | None = ChatSession,
    ) -> ChatSessionOut:
        """C1/C8 resume: step and cart of this phone's chat; empty after 2 idle hours."""
        key = web_chat.check_session(session)
        async with db.transaction(pool(request), scope.actor()) as conn:
            row = await web_chat.get_session(conn, scope.actor(), scope, key)
        return ChatSessionOut(**row)

    @router.put(f"{base}/chat-session")
    async def put_chat_session(
        body: ChatSessionIn,
        request: Request,
        scope: web_chat.ChatScope = Scope,
        session: str | None = ChatSession,
    ) -> ChatSessionOut:
        """Save step + cart (no personal data: name, phone, and address stay on the phone)."""
        key = web_chat.check_session(session)
        cart = body.cart.model_dump(mode="json")
        web_chat.check_cart_size(cart)
        async with db.transaction(pool(request), scope.actor()) as conn:
            row = await web_chat.put_session(
                conn,
                scope.actor(),
                scope,
                key,
                step=body.step,
                cart=cart,
                fulfillment=body.fulfillment,
            )
        return ChatSessionOut(**row)

    @router.post(f"{base}/orders/status")
    async def orders_status(
        body: OrdersStatusIn, request: Request, scope: web_chat.ChatScope = Scope
    ) -> list[OrderOverview]:
        """C1 "Pesanan Saya": the orders whose keys this phone kept, while still readable."""
        async with db.transaction(pool(request), scope.actor()) as conn:
            rows = await web_chat.orders_overview(
                conn, scope, [(r.order_id, r.key) for r in body.orders]
            )
        return [OrderOverview(**r) for r in rows]

    @router.get(f"{base}/orders/{{order_id}}")
    async def order_status(
        order_id: UUID,
        request: Request,
        scope: web_chat.ChatScope = Scope,
        order_key: str | None = OrderKey,
    ) -> WebOrderStatus:
        """C7 (and C6 on reload): only with the order's access key; polled every 5 seconds."""
        async with db.transaction(pool(request), scope.actor()) as conn:
            row = await web_chat.order_status(conn, scope, order_id, order_key)
        return WebOrderStatus(**row)

    @router.get(f"{base}/orders/{{order_id}}/qris")
    async def order_qris(
        order_id: UUID,
        request: Request,
        scope: web_chat.ChatScope = Scope,
        order_key: str | None = OrderKey,
    ) -> Response:
        """C6: the outlet's static QRIS image (same as O3 / the S1 popup)."""
        async with db.transaction(pool(request), scope.actor()) as conn:
            await web_chat.order_status(conn, scope, order_id, order_key)
            content_type, data = await qris.image(conn, scope.outlet_id)
        return Response(
            content=data, media_type=content_type, headers={"Cache-Control": "no-store"}
        )

    @router.post(f"{base}/orders/{{order_id}}/payment-claim")
    async def payment_claim(
        order_id: UUID,
        request: Request,
        scope: web_chat.ChatScope = Scope,
        order_key: str | None = OrderKey,
    ) -> WebOrderStatus:
        """C6 "Saya sudah bayar": staff check the merchant account and confirm in S2/S4.
        Repeating it returns the same result (FR6.4)."""
        ctx = scope.actor()
        async with db.transaction(pool(request), ctx) as conn:
            await web_chat.claim_payment(conn, ctx, scope, order_id, order_key)
            row = await web_chat.order_status(conn, scope, order_id, order_key)
        return WebOrderStatus(**row)

    @router.post(f"{base}/orders/{{order_id}}/cancel")
    async def cancel(
        order_id: UUID,
        request: Request,
        scope: web_chat.ChatScope = Scope,
        order_key: str | None = OrderKey,
    ) -> WebOrderStatus:
        """C6 "Batalkan pesanan": only before "Saya sudah bayar"; stock returns."""
        ctx = scope.actor()
        async with db.transaction(pool(request), ctx) as conn:
            await web_chat.customer_cancel(conn, ctx, scope, order_id, order_key)
            row = await web_chat.order_status(conn, scope, order_id, order_key)
        return WebOrderStatus(**row)

    @router.get(f"{base}/recommendations")
    async def recommendation_cards(
        request: Request, scope: web_chat.ChatScope = Scope
    ) -> list[RecommendationCard]:
        """C9 cards: owner's picks first, then 30-day best sellers; no sold-out items, ≤ 30."""
        async with db.transaction(pool(request), scope.actor()) as conn:
            menu_rows = await catalog.counter_menu(conn, scope.outlet_id)
            listing = await recommendations.recommendation_list(conn, scope.outlet_id, menu_rows)
        menu = {m["product_id"]: m for m in menu_rows}
        rows: list[dict[str, Any]] = []
        for badge, entries in (
            ("owner_pick", listing["picks"]),
            ("best_seller", listing["best_sellers"]),
        ):
            for e in entries:
                item = menu.get(e["product_id"])
                if e["position"] is None or item is None:
                    continue
                rows.append({**item, "badge": badge, "position": e["position"]})
        rows.sort(key=lambda r: r["position"])
        await attach_photo_urls(request, rows)
        return [
            RecommendationCard(
                product_id=r["product_id"],
                name=r["name"],
                description=r.get("description"),
                price=r["price"],
                photo_url=r["photo_url"],
                badge=r["badge"],
            )
            for r in rows
        ]

    @router.post(
        f"{base}/agent/messages",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {}}}},
    )
    async def agent_message(
        body: AgentMessageIn,
        request: Request,
        scope: web_chat.ChatScope = Scope,
        session: str | None = ChatSession,
    ) -> StreamingResponse:
        """C9 AI / C14 / C15: one free-text message to the agent, answered as server-sent
        events — `delta` ({text}) while the reply is written, then one `final` ({reply_text,
        cards, quick_replies, order_draft, booking_draft, out_of_scope}) or one `error`
        ({code, fallback: buttons|cards}). Read-only, outlet-scoped tools, ≤ 4 data-tool calls
        and 30 s (FR6.6). Drafts create nothing: Pesan & bayar / Konfirmasi booking go through
        the button-flow endpoints."""
        key = web_chat.check_session(session)
        make_model = request.app.state.agent_model
        if make_model is None:
            raise ApiError(503, "agent_unavailable", "the chat assistant is not available")
        rate_limit(f"agent:{key}", _AGENT_PER_SESSION)
        context = body.context
        if context == "book" and not (scope.table_id is None and scope.reservations_enabled):
            context = "auto"
        db_pool = pool(request)

        async def events() -> Any:
            async for event in gateway.run_turn(
                pool=db_pool,
                make_model=make_model,
                scope=scope,
                session=key,
                text=body.text.strip(),
                context=context,
            ):
                if event.event == "final" and event.data["cards"]:
                    await attach_photo_urls(request, event.data["cards"])
                yield event.sse()

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
