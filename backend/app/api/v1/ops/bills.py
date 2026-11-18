"""Open bills (S5 / M3) and cashier shifts (S8 open, S1 header) for owner and staff.

T-033, T-039. Closing a shift with the blind count (T-040) is added in Wave 4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Header, Request, status
from pydantic import BaseModel, Field

from app import db
from app.api.errors import ApiError
from app.auth.deps import TenantUser
from app.core import bills, idempotency, outlets, shifts
from app.core.payments import PaymentInput

router = APIRouter(prefix="/api/v1/ops", tags=["ops: bills & shifts"])


class BillCard(BaseModel):
    id: UUID
    table_id: UUID | None
    table_name: str | None
    table_area: str | None
    guest_name: str | None
    running_total: int
    order_count: int
    opened_at: datetime


class BillList(BaseModel):
    payment_mode: Literal["pay_first", "open_bill"]
    bills: list[BillCard]


class BillOpen(BaseModel):
    table_id: UUID | None = None
    guest_name: str | None = Field(default=None, max_length=60)


class BillItem(BaseModel):
    name: str
    quantity: int
    addons: str


class BillOrder(BaseModel):
    id: UUID
    order_no: str
    channel: str
    created_at: datetime
    status: str
    line_total: int
    items: list[BillItem]


class BillDetail(BaseModel):
    id: UUID
    table_name: str | None
    table_area: str | None
    guest_name: str | None
    status: str
    opened_at: datetime
    orders: list[BillOrder]
    subtotal: int
    pb1_rate_bps: int | None
    pb1_amount: int
    total: int


class BillClose(BaseModel):
    method: Literal["cash", "qris"]
    cash_received: int | None = Field(default=None, ge=0, le=1_000_000_000)
    drawer_id: UUID | None = None


class BillClosed(BaseModel):
    bill_id: UUID
    total: int
    method: str
    change_due: int | None
    orders_completed: int


class ShiftRow(BaseModel):
    id: UUID
    drawer_id: UUID
    drawer_name: str
    drawer_number: int
    opened_at: datetime
    starting_cash: int
    opened_by_name: str | None


class DrawerShift(BaseModel):
    id: UUID
    opened_at: datetime
    starting_cash: int
    opened_by: str | None
    cash_in: int
    cash_in_count: int
    cash_refunds: int


class DrawerCard(BaseModel):
    drawer: dict[str, Any]
    shift: DrawerShift | None


class ShiftOpen(BaseModel):
    starting_cash: int = Field(ge=0, le=1_000_000_000)


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


@router.get("/outlets/{outlet_id}/bills")
async def list_bills(outlet_id: UUID, request: Request, user: TenantUser) -> BillList:
    async with db.transaction(_pool(request), user.actor()) as conn:
        outlet = await outlets.require_outlet(conn, outlet_id)
        rows = await bills.list_open(conn, outlet_id)
    return BillList(payment_mode=outlet["payment_mode"], bills=[BillCard(**r) for r in rows])


@router.post("/outlets/{outlet_id}/bills", status_code=status.HTTP_201_CREATED)
async def open_bill(
    outlet_id: UUID, body: BillOpen, request: Request, user: TenantUser
) -> BillDetail:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        bill_id = await bills.open_bill(
            conn, ctx, outlet_id, table_id=body.table_id, guest_name=body.guest_name
        )
        row = await bills.detail(conn, bill_id)
    return BillDetail(**row)


@router.get("/bills/{bill_id}")
async def bill_detail(bill_id: UUID, request: Request, user: TenantUser) -> BillDetail:
    async with db.transaction(_pool(request), user.actor()) as conn:
        row = await bills.detail(conn, bill_id)
    return BillDetail(**row)


@router.post("/bills/{bill_id}/close")
async def close_bill(
    bill_id: UUID,
    body: BillClose,
    request: Request,
    user: TenantUser,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> BillClosed:
    key = idempotency.check_key(idempotency_key)
    ctx = user.actor()
    try:
        async with db.transaction(_pool(request), ctx) as conn:
            cached = await idempotency.lookup(conn, ctx, f"bill.close:{bill_id}", key)
            if cached is not None:
                return BillClosed(**cached)
            result = BillClosed(
                **await bills.close(
                    conn,
                    ctx,
                    bill_id,
                    PaymentInput(body.method, body.cash_received, body.drawer_id),
                )
            )
            await idempotency.store(
                conn, ctx, f"bill.close:{bill_id}", key, result.model_dump(mode="json")
            )
    except psycopg.errors.UniqueViolation as exc:
        if "idempotency_keys" in str(exc):
            raise ApiError(409, "conflict", "the same request is already being processed") from None
        raise
    return result


@router.get("/outlets/{outlet_id}/shifts/current")
async def current_shifts(outlet_id: UUID, request: Request, user: TenantUser) -> list[ShiftRow]:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        rows = await shifts.open_shifts(conn, outlet_id)
    return [ShiftRow(**{k: v for k, v in r.items() if k != "opened_by"}) for r in rows]


@router.get("/outlets/{outlet_id}/drawers")
async def drawers(outlet_id: UUID, request: Request, user: TenantUser) -> list[DrawerCard]:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        rows = await shifts.drawers_with_shift(conn, outlet_id)
    return [DrawerCard(**r) for r in rows]


@router.post("/drawers/{drawer_id}/shifts", status_code=status.HTTP_201_CREATED)
async def open_shift(
    drawer_id: UUID, body: ShiftOpen, request: Request, user: TenantUser
) -> dict[str, UUID]:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        shift_id = await shifts.open_shift(conn, ctx, drawer_id, body.starting_cash)
    return {"id": shift_id}
