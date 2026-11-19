"""Owner dashboard — O2 Dashboard tab Ringkasan + keramaian (T-071, T-123, T-124).

Contract: docs/architecture/screen-endpoint-map.md → O2.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app import db
from app.auth.deps import OwnerOnly
from app.core import dashboard, outlets

router = APIRouter(prefix="/api/v1/owner", tags=["owner: dashboard"])


class TopItem(BaseModel):
    name: str
    quantity_sold: int
    revenue: int = Field(
        description="Sum of item line totals incl. add-ons, excl. PB1 and delivery fee"
    )


class TopItems(BaseModel):
    period: dashboard.TopItemsPeriod
    top_items: list[TopItem]


class Kpis(BaseModel):
    revenue_excl_pb1: int = Field(
        description="Menu revenue minus refunds, excl. PB1 and delivery fee"
    )
    change_pct: int | None = Field(
        description="Revenue vs the previous period (yesterday / same days last week / last "
        "month); null when the previous period had none"
    )
    orders: int
    cash_count: int
    qris_count: int
    pb1_collected: int
    delivery_fee: int
    delivery_orders: int


class BusynessCell(BaseModel):
    weekday: int = Field(ge=1, le=7, description="ISO weekday, 1 = Monday")
    hour: int = Field(ge=0, le=23)
    avg_orders: float


class Crowd(BaseModel):
    outlet_id: UUID
    name: str
    timezone: str
    occupied_tables: int
    total_tables: int
    active_orders: int
    level: dashboard.CrowdLevel


class HourCount(BaseModel):
    hour: int
    orders: int
    mark: Literal["busy", "quiet"] | None


class HourSummary(BaseModel):
    hours: list[int]
    orders: int
    share_pct: int


class LowStock(BaseModel):
    stock_item: str
    outlet_id: UUID
    outlet: str
    on_hand: Decimal
    low_threshold: Decimal
    unit: str
    display_unit: str | None
    status: Literal["low", "out"]


class ChannelShare(BaseModel):
    channel: Literal["whatsapp_online", "whatsapp_table", "counter"]
    orders: int
    share_pct: int


class MethodTotal(BaseModel):
    method: Literal["cash", "qris"]
    amount: int
    transactions: int


class Dashboard(BaseModel):
    period: dashboard.DashboardPeriod
    hours: dashboard.HoursFilter
    as_of: datetime
    kpis: Kpis
    busyness_map: list[BusynessCell]
    current_crowd: list[Crowd]
    orders_per_hour: list[HourCount]
    busy_summary: HourSummary
    quiet_summary: HourSummary
    low_stock: list[LowStock]
    channel_mix: list[ChannelShare]
    payment_methods: list[MethodTotal]


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


@router.get("/dashboard")
async def summary(
    request: Request,
    user: OwnerOnly,
    outlet_id: UUID | None = None,
    period: dashboard.DashboardPeriod = "today",
    hours: dashboard.HoursFilter = "all",
) -> Dashboard:
    """O2 tab Ringkasan: KPI tiles, peta keramaian, keramaian outlet sekarang, order per jam,
    stok rendah & sold out, komposisi per kanal, and metode bayar. The busyness map, current
    crowd, and low stock ignore `period` and `hours`."""
    async with db.transaction(_pool(request), user.actor()) as conn:
        if outlet_id:
            await outlets.require_outlet(conn, outlet_id)
        body = await dashboard.summary(conn, outlet_id=outlet_id, period=period, hours=hours)
    return Dashboard(**body)


@router.get("/dashboard/top-items")
async def top_items(
    request: Request,
    user: OwnerOnly,
    outlet_id: UUID | None = None,
    period: dashboard.TopItemsPeriod = "day",
) -> TopItems:
    """O2 "Item terlaris": top 5 by quantity sold for today, this month, or this year."""
    async with db.transaction(_pool(request), user.actor()) as conn:
        if outlet_id:
            await outlets.require_outlet(conn, outlet_id)
        rows = await dashboard.top_items(conn, outlet_id=outlet_id, period=period)
    return TopItems(period=period, top_items=[TopItem(**r) for r in rows])
