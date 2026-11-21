"""Customer web chat from the outlet link — wireframes C1-C7 on page 07 (T-141, T-050, T-053).

Contract: docs/architecture/screen-endpoint-map.md → "Customer web chat (C1-C15)". The outlet
link `/o/<slug>` takes online orders (pickup or delivery, name + phone, address for delivery),
always paid first with the outlet's static QRIS (FR2.3, FR2.6). No sign-in: the slug is the only
credential, plus the per-order access key (`X-Order-Key`). An unknown or old slug is
`outlet_link_invalid` (404, C13 card 1) with no outlet data. The routes shared with the table QR
live in `public_chat.py`; reservations (C10-C12) follow in Wave 6 (T-060, T-061).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Header, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from app import db
from app.api.errors import ApiError
from app.api.v1 import public_chat as chat
from app.api.v1.public_chat import ChatOutlet, LineIn, PrivacyNotice, WebOrderCreated
from app.core import orders, web_chat
from app.core.errors import ValidationFailedError

router = APIRouter(prefix="/api/v1/public/o", tags=["public: web chat from the outlet link (C1)"])


async def _resolve(slug: str, request: Request) -> web_chat.ChatScope:
    chat.limit_scope(request, f"o:{slug.lower()}")
    async with chat.pool(request).connection() as conn, conn.transaction():
        scope = await web_chat.resolve_slug(conn, slug)
    if scope is None:
        raise ApiError(404, "outlet_link_invalid", "link outlet ini sudah tidak berlaku")
    return scope


async def current_scope(slug: str, request: Request) -> web_chat.ChatScope:
    scope = await _resolve(slug, request)
    await chat.expire_unpaid(request, scope)
    return scope


chat.register(router, "slug", current_scope)


# C1 greeting ---------------------------------------------------------------------------------


class OutletPage(BaseModel):
    outlet: ChatOutlet
    reservations_enabled: bool = Field(description="Shows Reservasi and Reservasi Saya (FR2.0)")
    web_ordering: bool = Field(description='False without a static QRIS: "Pesan di kasir"')
    delivery_fee: int = Field(description="Flat fee for delivery orders, outside the PB1 base")
    agent_enabled: bool = Field(description="Free-text agent (C9/C14/C15); off until T-086 ships")
    privacy_notice: PrivacyNotice


@router.get("/{slug}")
async def outlet_page(slug: str, request: Request) -> OutletPage:
    """C1: greeting and what the main menu offers at this outlet."""
    scope = await _resolve(slug, request)
    async with db.transaction(chat.pool(request), scope.actor()) as conn:
        await web_chat.expire_unpaid(conn, scope.actor(), scope.outlet_id)
        info = await web_chat.outlet_info(conn, scope)
    return OutletPage(
        outlet=ChatOutlet(**info),
        reservations_enabled=scope.reservations_enabled,
        web_ordering=scope.web_ordering,
        delivery_fee=scope.delivery_fee,
        agent_enabled=False,
        privacy_notice=chat.privacy_notice(),
    )


# C4 + C5 Pesan & bayar ----------------------------------------------------------------------------


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    phone: str = Field(min_length=8, max_length=20)
    address: str | None = Field(default=None, max_length=300)

    @field_validator("name", "address")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


class OnlineOrderIn(chat.OrderTextFields):
    items: list[LineIn] = Field(min_length=1, max_length=50)
    fulfillment: Literal["pickup", "delivery"]
    customer: CustomerIn
    privacy_notice_version: str = Field(
        max_length=40, description="The notice the chat showed before the details were sent"
    )


@router.post("/{slug}/orders", status_code=status.HTTP_201_CREATED)
async def place_order(
    slug: str,
    body: OnlineOrderIn,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> WebOrderCreated:
    """C4/C5 "Pesan & bayar": a pay-first `web_online` order, pickup or delivery."""
    scope = await current_scope(slug, request)
    ctx = scope.actor()
    if not body.customer.name:
        raise ValidationFailedError("name is required", {"field": "name"})
    if body.fulfillment == "delivery" and not body.customer.address:
        raise ValidationFailedError("address is required for delivery", {"field": "address"})
    phone = web_chat.clean_phone(body.customer.phone)

    async def build(conn: Any, key_hash: str) -> orders.WebOrder:
        customer_id = await web_chat.record_customer(
            conn,
            ctx,
            scope.outlet_id,
            name=body.customer.name,
            phone=phone,
            notice_version=body.privacy_notice_version,
        )
        return orders.WebOrder(
            table_id=None,
            lines=chat.lines(body.items),
            access_key_hash=key_hash,
            note=body.note,
            customer_name=body.customer.name,
            expected_total=body.expected_total,
            fulfillment=body.fulfillment,
            delivery_address=body.customer.address if body.fulfillment == "delivery" else None,
            customer_id=customer_id,
        )

    return await chat.create_order(request, response, scope, idempotency_key, body, build)
