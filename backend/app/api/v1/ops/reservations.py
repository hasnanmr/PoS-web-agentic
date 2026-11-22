"""Reservations and tables for the day — wireframes S6 / M4 (T-062, T-063, T-064).

Owner and staff (assigned outlets only, enforced by RLS). Every change records the actor.
Contract: docs/architecture/screen-endpoint-map.md → S6 / M4.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status
from pydantic import AwareDatetime, BaseModel, Field

from app import db
from app.auth.deps import TenantUser
from app.core import occupancy, outlets
from app.core import reservations as core

router = APIRouter(prefix="/api/v1/ops", tags=["ops: reservations"])

Action = Literal["seat", "move", "cancel", "no_show", "complete"]
Status = Literal["booked", "seated", "completed", "cancelled", "no_show"]
Source = Literal["whatsapp", "phone", "in_person", "walk_in", "web_chat"]


class TableOccupancy(BaseModel):
    """The table is in use now (FR9.11): an open dine-in order or an open bill."""

    since: datetime
    bill_id: UUID | None
    open_orders: int
    allowed_actions: list[Literal["release"]]


class BoardTable(BaseModel):
    id: UUID
    name: str
    capacity: int
    area: str | None
    is_bookable: bool
    occupancy: TableOccupancy | None = Field(
        default=None, description="Only for today's board, while the table is in use"
    )


class BoardSettings(BaseModel):
    bookable_from: time
    bookable_until: time
    default_duration_minutes: int
    max_party_size: int
    booking_window_days: int
    hold_minutes: int


class ReservationRow(BaseModel):
    id: UUID
    table_id: UUID
    table_name: str
    guest_name: str | None = Field(description='Null for a walk-in ("Tanpa reservasi")')
    party_size: int
    starts_at: datetime
    ends_at: datetime
    status: Status
    source: Source
    hold_until: datetime | None = Field(description="Booked only: start + 15 min, then no-show")
    no_show_at: datetime | None
    table_occupied: bool = Field(
        default=False,
        description="A booked reservation starting today whose table is in use now (FR9.11)",
    )
    allowed_actions: list[Action]


class Board(BaseModel):
    date: date
    timezone: str
    settings: BoardSettings
    tables: list[BoardTable]
    reservations: list[ReservationRow]


class ReservationEvent(BaseModel):
    event: str
    from_status: Status | None
    to_status: Status | None
    from_table: str | None
    to_table: str | None
    reason: str | None
    actor_type: Literal["user", "system", "agent", "device"]
    actor_name: str | None
    created_at: datetime


class ReservationDetail(ReservationRow):
    phone_masked: str | None
    timezone: str
    events: list[ReservationEvent]


class BookingIn(BaseModel):
    guest_name: str = Field(min_length=1, max_length=60)
    guest_phone: str | None = Field(default=None, pattern=r"^\+?[0-9 -]{8,20}$")
    party_size: int = Field(ge=1, le=100)
    starts_at: AwareDatetime
    table_id: UUID | None = Field(default=None, description="Omit to assign the smallest free fit")
    source: Literal["phone", "in_person"]


class WalkInIn(BaseModel):
    table_id: UUID
    party_size: int = Field(ge=1, le=100)


class MoveIn(BaseModel):
    table_id: UUID


class ReleaseIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


@router.get("/outlets/{outlet_id}/reservations")
async def reservation_board(
    outlet_id: UUID,
    request: Request,
    user: TenantUser,
    day: Annotated[
        date | None, Query(alias="date", description="Outlet-local; default today")
    ] = None,
) -> Board:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        data = await core.board(conn, outlet_id, day)
    return Board(**data)


@router.post("/outlets/{outlet_id}/reservations", status_code=status.HTTP_201_CREATED)
async def create_booking(
    outlet_id: UUID, body: BookingIn, request: Request, user: TenantUser
) -> ReservationDetail:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        res_id = await core.create_booking(conn, ctx, outlet_id, **body.model_dump())
        data = await core.detail(conn, res_id)
    return ReservationDetail(**data)


@router.post("/outlets/{outlet_id}/walk-ins", status_code=status.HTTP_201_CREATED)
async def create_walk_in(
    outlet_id: UUID, body: WalkInIn, request: Request, user: TenantUser
) -> ReservationDetail:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        res_id = await core.create_walk_in(conn, ctx, outlet_id, **body.model_dump())
        data = await core.detail(conn, res_id)
    return ReservationDetail(**data)


@router.get("/reservations/{reservation_id}")
async def reservation_detail(
    reservation_id: UUID, request: Request, user: TenantUser
) -> ReservationDetail:
    async with db.transaction(_pool(request), user.actor()) as conn:
        data = await core.detail(conn, reservation_id)
    return ReservationDetail(**data)


async def _action(request: Request, user: TenantUser, reservation_id: UUID, fn: Any) -> Response:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await fn(conn, ctx, reservation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reservations/{reservation_id}/seat", status_code=status.HTTP_204_NO_CONTENT)
async def seat(reservation_id: UUID, request: Request, user: TenantUser) -> Response:
    """`hold_expired` after the 15-minute hold (the booking is already a no-show)."""
    return await _action(request, user, reservation_id, core.seat)


@router.post("/reservations/{reservation_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel(reservation_id: UUID, request: Request, user: TenantUser) -> Response:
    return await _action(request, user, reservation_id, core.cancel)


@router.post("/reservations/{reservation_id}/no-show", status_code=status.HTTP_204_NO_CONTENT)
async def no_show(reservation_id: UUID, request: Request, user: TenantUser) -> Response:
    """`too_early` before the booking time."""
    return await _action(request, user, reservation_id, core.mark_no_show)


@router.post("/reservations/{reservation_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete(reservation_id: UUID, request: Request, user: TenantUser) -> Response:
    """ "Selesai": the seated guests left and the table is free again (US-026)."""
    return await _action(request, user, reservation_id, core.complete)


@router.post("/reservations/{reservation_id}/move", status_code=status.HTTP_204_NO_CONTENT)
async def move(reservation_id: UUID, body: MoveIn, request: Request, user: TenantUser) -> Response:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await core.move(conn, ctx, reservation_id, body.table_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/tables/{table_id}/release-occupancy", status_code=status.HTTP_204_NO_CONTENT)
async def release_occupancy(
    table_id: UUID, request: Request, user: TenantUser, body: ReleaseIn | None = None
) -> Response:
    """ "Kosongkan meja" (FR9.11): the table is free for bookings again until a new order or
    bill uses it; orders and bills are unchanged. `not_occupied` when it is not in use."""
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await occupancy.release(conn, ctx, table_id, body.reason if body else None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
