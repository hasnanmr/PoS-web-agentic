"""Owner tables and reservation rules — wireframe O8 "Meja & Aturan Reservasi" (T-057).

Contract: docs/architecture/screen-endpoint-map.md → O8. The table QR download belongs to
T-054 (WhatsApp, pilot) and is not served yet.
"""

from __future__ import annotations

from datetime import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from app import db
from app.auth.deps import OwnerOnly
from app.core import outlets
from app.core import tables as core

router = APIRouter(prefix="/api/v1/owner", tags=["owner: tables & reservation rules"])


class TableOut(BaseModel):
    id: UUID
    name: str
    capacity: int
    area: str | None
    is_bookable: bool


class TableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    capacity: int = Field(ge=1, le=100)
    area: str | None = Field(default=None, max_length=60)
    is_bookable: bool = True


class TablePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=30)
    capacity: int | None = Field(default=None, ge=1, le=100)
    area: str | None = Field(default=None, max_length=60)
    is_bookable: bool | None = None


class ReservationSettingsIn(BaseModel):
    is_enabled: bool = Field(description='"Reservasi WhatsApp" toggle; staff bookings always work')
    bookable_from: time
    bookable_until: time = Field(description="Last booking start time (outlet-local)")
    default_duration_minutes: int = Field(ge=15, le=600)
    booking_window_days: int = Field(ge=0, le=365)
    max_party_size: int = Field(ge=1, le=100)
    reminder_offset_minutes: int = Field(ge=0, le=2880)
    cancellation_cutoff_minutes: int = Field(ge=0, le=2880)


class ReservationSettingsOut(ReservationSettingsIn):
    hold_minutes: int = Field(description="No-show hold, fixed at 15 (read-only)")


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


@router.get("/outlets/{outlet_id}/tables")
async def list_tables(outlet_id: UUID, request: Request, user: OwnerOnly) -> list[TableOut]:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        rows = await core.list_tables(conn, outlet_id)
    return [TableOut(**r) for r in rows]


@router.post("/outlets/{outlet_id}/tables", status_code=status.HTTP_201_CREATED)
async def create_table(
    outlet_id: UUID, body: TableCreate, request: Request, user: OwnerOnly
) -> TableOut:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        row = await core.create_table(conn, ctx, outlet_id, **body.model_dump())
    return TableOut(**row)


@router.patch("/tables/{table_id}")
async def update_table(
    table_id: UUID, body: TablePatch, request: Request, user: OwnerOnly
) -> TableOut:
    ctx = user.actor()
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "capacity", "is_bookable"):
        if field in changes and changes[field] is None:
            changes.pop(field)
    async with db.transaction(_pool(request), ctx) as conn:
        row = await core.update_table(conn, ctx, table_id, changes)
    return TableOut(**row)


@router.delete("/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(table_id: UUID, request: Request, user: OwnerOnly) -> Response:
    """Deactivate the table. `table_in_use` while it has an open bill or an upcoming booking."""
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await core.delete_table(conn, ctx, table_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/outlets/{outlet_id}/reservation-settings")
async def get_settings(
    outlet_id: UUID, request: Request, user: OwnerOnly
) -> ReservationSettingsOut:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        row = await core.get_settings(conn, outlet_id)
    return ReservationSettingsOut(**row)


@router.put("/outlets/{outlet_id}/reservation-settings")
async def put_settings(
    outlet_id: UUID, body: ReservationSettingsIn, request: Request, user: OwnerOnly
) -> ReservationSettingsOut:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        row = await core.put_settings(conn, ctx, outlet_id, body.model_dump())
    return ReservationSettingsOut(**row)
