"""Customer web chat from a table QR — wireframe C8 on page 07 (T-134 rework, T-145).

Contract: docs/architecture/screen-endpoint-map.md → "Customer web chat (C1-C15)" and the Q0-Q5
section it replaces. No sign-in: the table token in the path is the only credential, plus the
per-order access key (`X-Order-Key`). Unknown or replaced tokens are `table_qr_invalid` (404,
C13 card 2). Orders are dine-in for this table, always paid first with the static QRIS. The
routes shared with the outlet link (menu, quote, chat session, status, payment) live in
`public_chat.py`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from app import db
from app.api.errors import ApiError
from app.api.v1 import public_chat as chat
from app.api.v1.public_chat import ChatOutlet, LineIn, PrivacyNotice, WebOrderCreated
from app.core import orders, web_chat
from app.core import table_qr as core

router = APIRouter(prefix="/api/v1/public/t", tags=["public: web chat from a table QR (C8)"])


async def _resolve(token: str, request: Request) -> core.TableRef:
    chat.limit_scope(request, f"t:{token}")
    async with chat.pool(request).connection() as conn, conn.transaction():
        ref = await core.resolve(conn, token)
    if ref is None:
        raise ApiError(404, "table_qr_invalid", "QR ini sudah tidak berlaku")
    return ref


async def current_scope(token: str, request: Request) -> web_chat.ChatScope:
    scope = (await _resolve(token, request)).scope
    await chat.expire_unpaid(request, scope)
    return scope


chat.register(router, "token", current_scope)


# C8 greeting -----------------------------------------------------------------------------------


class TableOut(BaseModel):
    name: str
    area: str | None


class TablePage(BaseModel):
    outlet: ChatOutlet
    table: TableOut
    web_ordering: bool = Field(description='False without a static QRIS: "Pesan di kasir"')
    agent_enabled: bool = Field(description="Free-text agent (C9/C14); off until T-086 ships")
    privacy_notice: PrivacyNotice


@router.get("/{token}")
async def table_page(token: str, request: Request) -> TablePage:
    """C8: the outlet and table, and whether ordering is possible here."""
    ref = await _resolve(token, request)
    scope = ref.scope
    async with db.transaction(chat.pool(request), scope.actor()) as conn:
        await web_chat.expire_unpaid(conn, scope.actor(), scope.outlet_id)
        info = await web_chat.outlet_info(conn, scope)
    return TablePage(
        outlet=ChatOutlet(**info),
        table=TableOut(name=ref.table_name, area=ref.area),
        web_ordering=scope.web_ordering,
        agent_enabled=False,
        privacy_notice=chat.privacy_notice(),
    )


# C8 Pesan & bayar --------------------------------------------------------------------------------


class TableOrderIn(chat.OrderTextFields):
    items: list[LineIn] = Field(min_length=1, max_length=50)
    customer_name: str | None = Field(default=None, max_length=40)
    privacy_notice_version: str | None = Field(
        default=None,
        max_length=40,
        description="The notice the chat showed before the name was sent (FR12.1)",
    )

    @field_validator("customer_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


@router.post("/{token}/orders", status_code=status.HTTP_201_CREATED)
async def place_order(
    token: str,
    body: TableOrderIn,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    order_key: str | None = Header(
        default=None,
        alias="X-Order-Key",
        description="Access key made by the page (32-128 URL-safe characters); recommended",
    ),
) -> WebOrderCreated:
    """C8 "Pesan & bayar": a pay-first dine-in order for this table (stock deducted)."""
    scope = await current_scope(token, request)
    ctx = scope.actor()

    async def build(conn: Any, key_hash: str) -> orders.WebOrder:
        customer_id = None
        if body.customer_name and body.privacy_notice_version is not None:
            customer_id = await web_chat.record_customer(
                conn,
                ctx,
                scope.outlet_id,
                name=body.customer_name,
                phone=None,
                notice_version=body.privacy_notice_version,
            )
        assert scope.table_id is not None  # noqa: S101
        return orders.WebOrder(
            table_id=scope.table_id,
            lines=chat.lines(body.items),
            access_key_hash=key_hash,
            note=body.note,
            customer_name=body.customer_name,
            expected_total=body.expected_total,
            customer_id=customer_id,
        )

    return await chat.create_order(
        request, response, scope, idempotency_key, order_key, body, build
    )
