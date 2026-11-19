"""Owner dashboard — O2 Dashboard + keramaian (T-071). Only the "Item terlaris" card so far.

Contract: docs/architecture/screen-endpoint-map.md → O2.
"""

from __future__ import annotations

from typing import Any
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


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


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
