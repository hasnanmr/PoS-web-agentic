"""Owner dashboard — O2 Dashboard tab Ringkasan + keramaian (T-071, T-123, T-124).

Contract: docs/architecture/screen-endpoint-map.md → O2.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app import db
from app.auth.deps import OwnerOnly
from app.core import dashboard, outlets

router = APIRouter(prefix="/api/v1/owner", tags=["owner: dashboard"])


class TopItem(BaseModel):
    product_id: UUID
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


class DrillSummary(BaseModel):
    orders: int
    revenue_excl_pb1: int = Field(description="Sum of order subtotals, excl. PB1 and delivery")
    cash_count: int
    qris_count: int


class DrillItem(BaseModel):
    product_id: UUID
    name: str
    quantity: int
    revenue: int = Field(description="Sum of the item's line totals incl. add-ons, excl. PB1")


class DrillOutlet(BaseModel):
    outlet_id: UUID
    name: str
    orders: int
    revenue_excl_pb1: int


class DrillOrder(BaseModel):
    id: UUID
    order_no: str
    outlet_id: UUID
    outlet: str
    timezone: str
    created_at: datetime
    channel: dashboard.OrderChannel
    type: Literal["dine_in", "takeaway", "delivery", "pickup"]
    table: str | None
    customer_name: str | None
    payment_method: dashboard.PaymentMethod | None
    item_summary: str
    revenue_excl_pb1: int = Field(description="Order subtotal, excl. PB1 and delivery fee")
    total: int


class DashboardOrders(BaseModel):
    period: dashboard.OrdersPeriod
    summary: DrillSummary
    item: DrillItem | None
    by_outlet: list[DrillOutlet]
    orders: list[DrillOrder]
    next_cursor: str | None


class Dashboard(BaseModel):
    period: dashboard.DashboardPeriod
    from_: date = Field(alias="from", description="First day used (first selected outlet)")
    to: date = Field(description="Last day used (first selected outlet)")
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

    model_config = {"populate_by_name": True}


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


@router.get("/dashboard")
async def summary(
    request: Request,
    user: OwnerOnly,
    outlet_id: UUID | None = None,
    period: dashboard.DashboardPeriod = "today",
    hours: dashboard.HoursFilter = "all",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> Dashboard:
    """O2 tab Ringkasan: KPI tiles, peta keramaian, keramaian outlet sekarang, order per jam,
    stok rendah & sold out, komposisi per kanal, and metode bayar. The busyness map, current
    crowd, and low stock ignore `period` and `hours`. `period=range` ("Rentang") needs `from`
    and `to` (at most 92 days, `to` not after today)."""
    async with db.transaction(_pool(request), user.actor()) as conn:
        if outlet_id:
            await outlets.require_outlet(conn, outlet_id)
        body = await dashboard.summary(
            conn,
            outlet_id=outlet_id,
            period=period,
            hours=hours,
            date_from=date_from,
            date_to=date_to,
        )
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


@router.get("/dashboard/orders")
async def drill_orders(
    request: Request,
    user: OwnerOnly,
    outlet_id: UUID | None = None,
    period: dashboard.OrdersPeriod = "today",
    hours: dashboard.HoursFilter = "all",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    product_id: UUID | None = None,
    method: dashboard.PaymentMethod | None = None,
    channel: dashboard.OrderChannel | None = None,
    q: Annotated[str | None, Query(max_length=40)] = None,
    cursor: str | None = None,
    limit: Annotated[
        int, Query(ge=1, le=dashboard.ORDERS_LIMIT_MAX)
    ] = dashboard.ORDERS_LIMIT_DEFAULT,
) -> DashboardOrders:
    """O2b drawer: the paid orders behind the Revenue / Order tile, an Order per jam bar
    (`hour`), or an Item terlaris row (`product_id`). `summary`, `by_outlet`, and `item` ignore
    the chip (`method`), Kanal (`channel`), and search (`q`); the list applies every filter."""
    async with db.transaction(_pool(request), user.actor()) as conn:
        if outlet_id:
            await outlets.require_outlet(conn, outlet_id)
        body = await dashboard.drill_orders(
            conn,
            outlet_id=outlet_id,
            period=period,
            hours=hours,
            date_from=date_from,
            date_to=date_to,
            hour=hour,
            product_id=product_id,
            method=method,
            channel=channel,
            q=q,
            cursor=cursor,
            limit=limit,
        )
    return DashboardOrders(**body)
