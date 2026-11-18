"""Owner outlet settings — wireframe O3 "Bisnis & Outlet" (T-011, T-039 drawers).

Contract: docs/architecture/screen-endpoint-map.md → O3. QRIS upload (T-014) and
attendance tablets (T-121) are added by their own tasks.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from app import db
from app.auth.deps import OwnerOnly
from app.core import outlets as core

router = APIRouter(prefix="/api/v1/owner", tags=["owner: outlets"])

Timezone = Literal["Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura"]
Phone = Field(default=None, pattern=r"^\+?[0-9]{8,15}$")


class OutletSummary(BaseModel):
    id: UUID
    name: str
    timezone: str
    order_prefix: str
    is_active: bool


class OpeningHoursItem(BaseModel):
    weekday: int = Field(ge=1, le=7, description="ISO weekday, 1 = Monday")
    opens_at: time
    closes_at: time = Field(description="Not after opens_at means the outlet closes after midnight")


class OutletDetail(BaseModel):
    id: UUID
    name: str
    address: str | None
    timezone: str
    whatsapp_phone: str | None
    whatsapp_status: Literal["not_started", "pending_verification", "connected", "error"]
    catalog_synced_at: datetime | None
    order_prefix: str
    payment_mode: Literal["pay_first", "open_bill"]
    pb1_enabled: bool
    pb1_rate_bps: int | None
    delivery_fee: int
    unpaid_timeout_minutes: int
    attendance_grace_minutes: int
    is_active: bool
    opening_hours: list[OpeningHoursItem]


class OutletCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    timezone: Timezone = "Asia/Jakarta"
    address: str | None = Field(default=None, max_length=300)
    whatsapp_phone: str | None = Phone


class OutletPatch(BaseModel):
    """O3 "Simpan perubahan": only the fields sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    timezone: Timezone | None = None
    whatsapp_phone: str | None = Phone
    pb1_enabled: bool | None = None
    pb1_rate_bps: int | None = Field(default=None, ge=1, le=1000)
    payment_mode: Literal["pay_first", "open_bill"] | None = None
    delivery_fee: int | None = Field(default=None, ge=0, le=10_000_000)
    unpaid_timeout_minutes: int | None = Field(default=None, ge=1, le=1440)
    attendance_grace_minutes: int | None = Field(default=None, ge=0, le=720)


class Drawer(BaseModel):
    id: UUID
    name: str
    has_open_shift: bool


class DrawerName(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class Created(BaseModel):
    id: UUID


# Fields that may be cleared with an explicit null.
_NULLABLE = {"address", "whatsapp_phone", "pb1_rate_bps"}


@router.get("/outlets")
async def list_outlets(request: Request, owner: OwnerOnly) -> list[OutletSummary]:
    async with db.transaction(request.app.state.db_pool, owner.actor()) as conn:
        rows = await core.list_outlets(conn)
    return [OutletSummary(**r) for r in rows]


@router.post("/outlets", status_code=status.HTTP_201_CREATED)
async def create_outlet(body: OutletCreate, request: Request, owner: OwnerOnly) -> OutletDetail:
    async with db.transaction(request.app.state.db_pool, owner.actor()) as conn:
        outlet_id = await core.create_outlet(conn, owner.actor(), **body.model_dump())
        row = await core.get_outlet(conn, outlet_id)
    return OutletDetail(**row)


@router.get("/outlets/{outlet_id}")
async def get_outlet(outlet_id: UUID, request: Request, owner: OwnerOnly) -> OutletDetail:
    async with db.transaction(request.app.state.db_pool, owner.actor()) as conn:
        row = await core.get_outlet(conn, outlet_id)
    return OutletDetail(**row)


@router.patch("/outlets/{outlet_id}")
async def update_outlet(
    outlet_id: UUID, body: OutletPatch, request: Request, owner: OwnerOnly
) -> OutletDetail:
    changes = {
        k: v
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None or k in _NULLABLE
    }
    ctx = owner.actor()
    async with db.transaction(request.app.state.db_pool, ctx) as conn:
        await core.update_outlet(conn, ctx, outlet_id, changes)
        row = await core.get_outlet(conn, outlet_id)
    return OutletDetail(**row)


@router.put("/outlets/{outlet_id}/opening-hours")
async def set_opening_hours(
    outlet_id: UUID, body: list[OpeningHoursItem], request: Request, owner: OwnerOnly
) -> list[OpeningHoursItem]:
    ctx = owner.actor()
    hours = [core.OpeningHours(h.weekday, h.opens_at, h.closes_at) for h in body]
    async with db.transaction(request.app.state.db_pool, ctx) as conn:
        await core.set_opening_hours(conn, ctx, outlet_id, hours)
        row = await core.get_outlet(conn, outlet_id)
    return [OpeningHoursItem(**h) for h in row["opening_hours"]]


@router.get("/outlets/{outlet_id}/drawers")
async def list_drawers(outlet_id: UUID, request: Request, owner: OwnerOnly) -> list[Drawer]:
    async with db.transaction(request.app.state.db_pool, owner.actor()) as conn:
        rows = await core.list_drawers(conn, outlet_id)
    return [Drawer(**r) for r in rows]


@router.post("/outlets/{outlet_id}/drawers", status_code=status.HTTP_201_CREATED)
async def create_drawer(
    outlet_id: UUID, body: DrawerName, request: Request, owner: OwnerOnly
) -> Created:
    ctx = owner.actor()
    async with db.transaction(request.app.state.db_pool, ctx) as conn:
        drawer_id = await core.create_drawer(conn, ctx, outlet_id, body.name)
    return Created(id=drawer_id)


@router.patch("/drawers/{drawer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def rename_drawer(
    drawer_id: UUID, body: DrawerName, request: Request, owner: OwnerOnly
) -> Response:
    ctx = owner.actor()
    async with db.transaction(request.app.state.db_pool, ctx) as conn:
        await core.rename_drawer(conn, ctx, drawer_id, body.name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/drawers/{drawer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_drawer(drawer_id: UUID, request: Request, owner: OwnerOnly) -> Response:
    ctx = owner.actor()
    async with db.transaction(request.app.state.db_pool, ctx) as conn:
        await core.delete_drawer(conn, ctx, drawer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
