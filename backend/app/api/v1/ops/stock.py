"""Stock for owner and staff — wireframe S7 / M5 "Stok & Pergerakan" (T-020, T-022, T-069).

Stock cannot be edited directly; it changes only through append-only movements.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, Field

from app import db
from app.auth.deps import TenantUser
from app.core import outlets, stock

router = APIRouter(prefix="/api/v1/ops", tags=["ops: stock"])

Unit = Literal["g", "ml", "pcs"]


class AffectedProduct(BaseModel):
    name: str
    kind: Literal["product", "addon"]
    sold_out: bool


class StockRow(BaseModel):
    stock_item_id: UUID
    name: str
    unit: Unit
    display_unit: str | None
    on_hand: Decimal
    low_threshold: Decimal
    status: Literal["ok", "low", "out"]
    affected_products: list[AffectedProduct]


class StockCounts(BaseModel):
    low: int
    out: int


class StockResponse(BaseModel):
    counts: StockCounts
    items: list[StockRow]


class MovementCreate(BaseModel):
    type: Literal["restock", "waste", "adjustment"]
    stock_item_id: UUID
    quantity: Decimal = Field(
        max_digits=14, decimal_places=3, description="Base unit; signed for adjustment"
    )
    note: str | None = Field(default=None, max_length=200)


class MovementRow(BaseModel):
    id: int
    at: datetime
    type: Literal["sale", "sale_reversal", "restock", "waste", "adjustment"]
    quantity: Decimal
    unit: Unit
    display_unit: str | None
    stock_item: str
    order_no: str | None
    note: str | None
    actor_type: str
    actor: str


class MovementPage(BaseModel):
    items: list[MovementRow]
    next_cursor: int | None


@router.get("/outlets/{outlet_id}/stock")
async def get_stock(
    outlet_id: UUID,
    request: Request,
    user: TenantUser,
    status_filter: Literal["all", "low", "out"] = Query("all", alias="status"),
    q: str | None = Query(default=None, max_length=60),
) -> StockResponse:
    async with db.transaction(request.app.state.db_pool, user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        view = await stock.stock_view(conn, outlet_id, status=status_filter, q=q)
    return StockResponse(**view)


@router.post("/outlets/{outlet_id}/stock-movements", status_code=status.HTTP_201_CREATED)
async def create_movement(
    outlet_id: UUID, body: MovementCreate, request: Request, user: TenantUser
) -> StockResponse:
    ctx = user.actor()
    async with db.transaction(request.app.state.db_pool, ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        await stock.record_movement(
            conn,
            ctx,
            outlet_id,
            type=body.type,
            stock_item_id=body.stock_item_id,
            quantity=body.quantity,
            note=(body.note or "").strip() or None,
        )
        view = await stock.stock_view(conn, outlet_id)
    return StockResponse(**view)


@router.get("/outlets/{outlet_id}/stock-movements")
async def list_movements(
    outlet_id: UUID,
    request: Request,
    user: TenantUser,
    stock_item_id: UUID | None = None,
    cursor: int | None = None,
    limit: int = Query(default=30, ge=1, le=100),
) -> MovementPage:
    async with db.transaction(request.app.state.db_pool, user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        items, next_cursor = await stock.movement_history(
            conn, outlet_id, stock_item_id=stock_item_id, cursor=cursor, limit=limit
        )
    return MovementPage(items=[MovementRow(**i) for i in items], next_cursor=next_cursor)
