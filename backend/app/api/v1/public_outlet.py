"""Customer web chat from the outlet link — wireframes C1-C7 on page 07 (T-141, T-050, T-053).

Contract: docs/architecture/screen-endpoint-map.md → "Customer web chat (C1-C15)". The outlet
link `/o/<slug>` takes online orders (pickup or delivery, name + phone, address for delivery),
always paid first with the outlet's static QRIS (FR2.3, FR2.6). No sign-in: the slug is the only
credential, plus the per-order access key (`X-Order-Key`). An unknown or old slug is
`outlet_link_invalid` (404, C13 card 1) with no outlet data. The routes shared with the table QR
live in `public_chat.py`; reservations (C10-C12, T-060, T-061) are at the end of this file.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Header, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from app import db
from app.api.errors import ApiError
from app.api.v1 import public_chat as chat
from app.api.v1.public_chat import ChatOutlet, LineIn, PrivacyNotice, WebOrderCreated
from app.core import idempotency, orders, web_booking, web_chat
from app.core.errors import NotFoundError, ValidationFailedError

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
    order_key: str | None = Header(
        default=None,
        alias="X-Order-Key",
        description="Access key made by the page (32-128 URL-safe characters); required",
    ),
) -> WebOrderCreated:
    """C4/C5 "Pesan & bayar": a pay-first `web_online` order, pickup or delivery. The page
    makes the access key and sends it as `X-Order-Key`; only its hash is stored."""
    scope = await current_scope(slug, request)
    ctx = scope.actor()
    if not order_key:
        raise ValidationFailedError("X-Order-Key is required", {"field": "access_key"})
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

    return await chat.create_order(
        request, response, scope, idempotency_key, order_key, body, build
    )


# C10-C12 reservations (T-060, T-061) -------------------------------------------------------------

BookingKey = Header(default=None, alias="X-Booking-Key")


class TimeSlot(BaseModel):
    start_at: datetime
    label: str = Field(description='Outlet-local "19:00"')


class Availability(BaseModel):
    date: date
    timezone: str
    max_party_size: int
    last_date: date = Field(description="Last date inside the booking window")
    times: list[TimeSlot]


class BookingIn(BaseModel):
    party_size: int = Field(ge=1, le=100)
    start_at: datetime
    customer: CustomerIn
    privacy_notice_version: str = Field(max_length=40)
    source: Literal["buttons", "agent"] = "buttons"


class Booking(BaseModel):
    reservation_id: UUID
    booking_code: str
    start_at: datetime
    label: str
    timezone: str
    party_size: int
    status: str
    guest_name: str | None = Field(description="Cleared once the booking is finished")
    hold_until: datetime | None
    change_until: datetime = Field(description="Cancel/reschedule allowed until (cutoff)")
    reminder_at: datetime | None = Field(
        default=None, description='C11 "Pengingat di kalender HP": the .ics alert time'
    )
    can_change: bool
    outlet_name: str


class BookingCreated(Booking):
    access_key: str = Field(description="Keep on the phone; send as `X-Booking-Key`")


class BookingRef(BaseModel):
    id: UUID
    key: str = Field(min_length=8, max_length=200)


class BookingsStatusIn(BaseModel):
    reservations: list[BookingRef] = Field(max_length=10)


class LookupIn(BaseModel):
    booking_code: str = Field(min_length=6, max_length=6)
    phone: str = Field(min_length=8, max_length=20)


class LookupOut(BaseModel):
    reservation_id: UUID
    access_key: str


class RescheduleIn(BaseModel):
    start_at: datetime


@router.get("/{slug}/availability")
async def availability(
    slug: str,
    request: Request,
    party_size: int = Query(ge=1, le=100),
    date: date = Query(),  # noqa: B008 - FastAPI query parameter
) -> Availability:
    """C10: free start times for the party on an outlet-local date (AC9.1, AC9.3)."""
    scope = await _resolve(slug, request)
    async with db.transaction(chat.pool(request), scope.actor()) as conn:
        out = await web_booking.availability(conn, scope, party_size, date)
    return Availability(**out)


async def _idempotent(
    request: Request,
    response: Response,
    scope: web_chat.ChatScope,
    operation: str,
    idempotency_key: str | None,
    access_key: str | None,
    body: dict[str, Any],
    work: Any,
    replay: Any,
    model: type[BaseModel],
) -> Any:
    """Idempotent booking write (FR6.4). The cache holds only the reservation id: no access
    key and no name (FR2.15, FR12.2). A replay rebuilds the answer from the reservation row
    through `replay(conn, reservation_id)`, which checks the booking key again, and the key's
    hash is part of the fingerprint, so a replay without the same key gets nothing."""
    key = idempotency.check_key(idempotency_key)
    if key is None:
        raise ApiError(422, "validation_failed", "Idempotency-Key is required")
    name = f"{operation}:{scope.outlet_id}"
    fp = idempotency.fingerprint(
        str(scope.outlet_id), body, web_chat.hash_key(access_key) if access_key else None
    )
    ctx = scope.actor()
    try:
        async with db.transaction(chat.pool(request), ctx) as conn:
            cached = await idempotency.lookup(conn, ctx, name, key, fp)
            if cached is not None:
                response.status_code = status.HTTP_200_OK
                response.headers["Idempotent-Replay"] = "true"
                return model(**await replay(conn, UUID(cached["reservation_id"])))
            out = model(**await work(conn, ctx))
            reservation_id = str(out.reservation_id)  # type: ignore[attr-defined]
            await idempotency.store(conn, ctx, name, key, fp, {"reservation_id": reservation_id})
    except psycopg.errors.UniqueViolation as exc:
        if "idempotency_keys" in str(exc):
            raise ApiError(409, "conflict", "the same request is already being processed") from None
        raise
    return out


@router.post("/{slug}/reservations", status_code=status.HTTP_201_CREATED)
async def create_booking(
    slug: str,
    body: BookingIn,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    booking_key: str | None = Header(
        default=None,
        alias="X-Booking-Key",
        description="Access key made by the page (32-128 URL-safe characters); required",
    ),
) -> BookingCreated:
    """C10 "Konfirmasi booking": smallest free table, booking code, 2 upcoming per phone. The
    page makes the access key and sends it as `X-Booking-Key`; only its hash is stored, also
    not in the idempotency cache, and a replay must carry the same key."""
    scope = await _resolve(slug, request)
    access_key = web_chat.check_client_key(booking_key)
    if access_key is None:
        raise ValidationFailedError("X-Booking-Key is required", {"field": "access_key"})
    name = web_booking.validate_name(body.customer.name or "")
    phone = web_chat.clean_phone(body.customer.phone)

    async def work(conn: Any, ctx: Any) -> dict[str, Any]:
        row = await web_booking.create(
            conn,
            ctx,
            scope,
            party_size=body.party_size,
            start_at=body.start_at,
            name=name,
            phone=phone,
            notice_version=body.privacy_notice_version,
            access_key_hash=web_chat.hash_key(access_key),
        )
        return {**row, "access_key": access_key}

    async def replay(conn: Any, reservation_id: UUID) -> dict[str, Any]:
        row = await web_booking.read(conn, scope, reservation_id, access_key)
        return {**row, "access_key": access_key}

    return await _idempotent(
        request,
        response,
        scope,
        "web_booking.create",
        idempotency_key,
        access_key,
        body.model_dump(mode="json"),
        work,
        replay,
        BookingCreated,
    )


@router.post("/{slug}/reservations/status")
async def bookings_status(slug: str, body: BookingsStatusIn, request: Request) -> list[Booking]:
    """C12 "Reservasi Saya": upcoming bookings whose keys this phone kept."""
    scope = await _resolve(slug, request)
    async with db.transaction(chat.pool(request), scope.actor()) as conn:
        rows = await web_booking.overview(conn, scope, [(r.id, r.key) for r in body.reservations])
    return [Booking(**r) for r in rows]


# Wrong code/phone pairs per client address: after this many misses in the window, refuse.
_LOOKUP_MISSES = 5
_LOOKUP_WINDOW = 600.0
_misses: dict[str, deque[float]] = {}


def _lookup_guard(request: Request, *, miss: bool = False) -> None:
    """Refuse after too many misses from one client address. Entries are made only on a miss
    and dropped once stale, so memory stays bounded (like `public_chat.rate_limit`)."""
    now = time.monotonic()
    key = chat.client_address(request)
    hits = _misses.get(key)
    if hits is not None:
        while hits and hits[0] < now - _LOOKUP_WINDOW:
            hits.popleft()
        if not hits:
            del _misses[key]
            hits = None
    if miss:
        _misses.setdefault(key, deque()).append(now)
        if len(_misses) > 10_000:
            for k in [k for k, v in _misses.items() if not v or v[-1] < now - _LOOKUP_WINDOW]:
                del _misses[k]
    elif hits is not None and len(hits) >= _LOOKUP_MISSES:
        raise ApiError(429, "too_many_requests", "too many wrong attempts; wait a moment")


@router.post("/{slug}/reservations/lookup")
async def lookup_booking(slug: str, body: LookupIn, request: Request) -> LookupOut:
    """C12 "Cari dengan kode + HP": same answer for a wrong code or a wrong phone (AC9.12)."""
    scope = await _resolve(slug, request)
    _lookup_guard(request)
    try:
        phone = web_chat.clean_phone(body.phone)
    except ValidationFailedError:
        _lookup_guard(request, miss=True)
        raise ApiError(404, "booking_not_found", "booking not found") from None
    access_key = web_chat.new_access_key()
    ctx = scope.actor()
    try:
        async with db.transaction(chat.pool(request), ctx) as conn:
            res_id = await web_booking.lookup(
                conn, ctx, scope, body.booking_code, phone, web_chat.hash_key(access_key)
            )
    except NotFoundError:
        _lookup_guard(request, miss=True)
        raise ApiError(404, "booking_not_found", "booking not found") from None
    return LookupOut(reservation_id=res_id, access_key=access_key)


@router.get("/{slug}/reservations/{reservation_id}")
async def read_booking(
    slug: str, reservation_id: UUID, request: Request, booking_key: str | None = BookingKey
) -> Booking:
    """C11/C12: the booking, only with a key this phone holds."""
    scope = await _resolve(slug, request)
    async with db.transaction(chat.pool(request), scope.actor()) as conn:
        row = await web_booking.read(conn, scope, reservation_id, booking_key)
    return Booking(**row)


@router.post("/{slug}/reservations/{reservation_id}/cancel")
async def cancel_booking(
    slug: str,
    reservation_id: UUID,
    request: Request,
    booking_key: str | None = BookingKey,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="Accepted like every write (FR6.4); cancel is idempotent by itself",
    ),
) -> Booking:
    """C12 "Batalkan": until the cutoff; frees the table. Repeating it returns the same
    cancelled booking, with or without the same Idempotency-Key."""
    idempotency.check_key(idempotency_key)
    scope = await _resolve(slug, request)
    ctx = scope.actor()
    async with db.transaction(chat.pool(request), ctx) as conn:
        row = await web_booking.cancel(conn, ctx, scope, reservation_id, booking_key)
    return Booking(**row)


@router.post("/{slug}/reservations/{reservation_id}/reschedule")
async def reschedule_booking(
    slug: str,
    reservation_id: UUID,
    body: RescheduleIn,
    request: Request,
    response: Response,
    booking_key: str | None = BookingKey,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Booking:
    """C12 "Jadwal ulang": a free time, until the cutoff (AC9.6)."""
    scope = await _resolve(slug, request)

    async def work(conn: Any, ctx: Any) -> dict[str, Any]:
        return await web_booking.reschedule(
            conn, ctx, scope, reservation_id, booking_key, body.start_at
        )

    async def replay(conn: Any, res_id: UUID) -> dict[str, Any]:
        return await web_booking.read(conn, scope, res_id, booking_key)

    return await _idempotent(
        request,
        response,
        scope,
        f"web_booking.reschedule:{reservation_id}",
        idempotency_key,
        booking_key,
        body.model_dump(mode="json"),
        work,
        replay,
        Booking,
    )


@router.get("/{slug}/reservations/{reservation_id}/calendar.ics")
async def booking_calendar(
    slug: str, reservation_id: UUID, request: Request, key: str = Query(min_length=8)
) -> Response:
    """C11 "Tambah ke kalender": the key is in the query so the phone can open it as a link."""
    scope = await _resolve(slug, request)
    async with db.transaction(chat.pool(request), scope.actor()) as conn:
        text = await web_booking.calendar(conn, scope, reservation_id, key)
    return Response(
        content=text,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="reservasi.ics"',
            "Cache-Control": "no-store",
        },
    )
