"""Purchase orders for staff and owner — S10 (Purchase Order outlet), S11 (cross-check barang
datang), S12/O16 (Buka PO). Staff only for their assigned outlets (RLS); no payments or debt.

Contract: docs/architecture/screen-endpoint-map.md → O16 / S12, S10, S11.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Header, Query, Request, Response, status
from pydantic import BaseModel, Field, model_validator

from app import db
from app.api.errors import ApiError
from app.auth.deps import TenantUser
from app.auth.principal import Principal
from app.core import idempotency, outlets
from app.core import purchase_orders as po

router = APIRouter(prefix="/api/v1/ops", tags=["ops: purchase orders"])

IdempotencyKey = Header(default=None, alias="Idempotency-Key")


# Schemas (shared with the owner router) -------------------------------------------------------


class Ref(BaseModel):
    id: UUID
    name: str


class PoRow(BaseModel):
    id: UUID
    number: str = Field(examples=["PO-A-0012"])
    supplier: Ref
    outlet: Ref
    payment_term: Literal["pay_later", "pay_in_advance"]
    ordered_on: date
    due_date: date | None
    expected_date: date | None
    status: Literal["open", "difference_found", "closed", "cancelled"]
    goods_status: Literal["not_arrived", "partly_arrived", "arrived"]
    payment_status: Literal["unpaid", "partially_paid", "paid"]
    overdue: bool
    total: int
    created_at: datetime
    created_by: str | None
    amount_paid: int | None = Field(default=None, description="Owner only")
    amount_owed: int | None = Field(default=None, description="Owner only")


class PoPage(BaseModel):
    items: list[PoRow]
    next_cursor: str | None


class OutletCounts(BaseModel):
    active: int = Field(description="Terbuka: not closed, except Menunggu barang")
    waiting_goods: int = Field(description="Menunggu barang: pay in advance, paid, open")


class OutletPoPage(PoPage):
    counts: OutletCounts = Field(description="S10 header counts (whatever the status filter)")


class PoLine(BaseModel):
    id: UUID
    item: str
    stock_item_id: UUID | None
    quantity: Decimal
    unit: str
    unit_price: int
    subtotal: int
    received_quantity: Decimal
    remaining_quantity: Decimal
    check: Literal["match", "short"]


class Actor(BaseModel):
    name: str | None
    role: str | None


class PoEvent(BaseModel):
    at: datetime
    kind: Literal["opened", "received", "paid", "closed", "cancelled"]
    actor: Actor
    data: dict[str, Any]


PoAction = Literal["receive", "close", "close_with_note", "record_payment", "cancel"]


class PoDetail(PoRow):
    note: str | None
    close_note: str | None
    cancel_reason: str | None
    lines: list[PoLine]
    events: list[PoEvent]
    allowed_actions: list[PoAction]


class PoLineIn(BaseModel):
    stock_item_id: UUID | None = None
    item_name: str | None = Field(default=None, max_length=120)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit: str = Field(min_length=1, max_length=20, description="g/kg/ml/L/pcs for stock items")
    unit_price: int = Field(ge=0, le=po.MAX_AMOUNT, description="Rupiah per unit")

    @model_validator(mode="after")
    def _item(self) -> PoLineIn:
        if self.stock_item_id is None and not (self.item_name or "").strip():
            raise ValueError("choose a stock item or type the item name")
        return self


class PoCreate(BaseModel):
    supplier_id: UUID
    ordered_on: date
    payment_term: Literal["pay_later", "pay_in_advance"]
    due_date: date | None = Field(default=None, description="pay_later")
    expected_date: date | None = Field(default=None, description="pay_in_advance")
    lines: list[PoLineIn] = Field(min_length=1, max_length=po.MAX_LINES)
    note: str | None = Field(default=None, max_length=300)


class ReceiptLineIn(BaseModel):
    line_id: UUID
    quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)


class ReceiptIn(BaseModel):
    received_on: date
    note: str | None = Field(default=None, max_length=300)
    lines: list[ReceiptLineIn] = Field(min_length=1, max_length=po.MAX_LINES)


class SupplierOption(BaseModel):
    id: UUID
    name: str


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


def viewer(user: Principal) -> po.Viewer:
    return "owner" if user.is_owner else "staff"


async def idempotent(
    request: Request,
    response: Response,
    user: Principal,
    *,
    scope: str,
    key: str | None,
    body: dict[str, Any],
    work: Callable[[psycopg.AsyncConnection], Awaitable[BaseModel]],
    model: type[BaseModel],
) -> Any:
    """Run `work` once per Idempotency-Key; a replay returns the stored response (200)."""
    key = idempotency.check_key(key)
    fp = idempotency.fingerprint(scope, body)
    ctx = user.actor()
    try:
        async with db.transaction(_pool(request), ctx) as conn:
            cached = await idempotency.lookup(conn, ctx, scope, key, fp)
            if cached is not None:
                response.status_code = status.HTTP_200_OK
                response.headers["Idempotent-Replay"] = "true"
                return model(**cached)
            result = await work(conn)
            await idempotency.store(conn, ctx, scope, key, fp, result.model_dump(mode="json"))
    except psycopg.errors.UniqueViolation as exc:
        if "idempotency_keys" in str(exc):
            raise ApiError(409, "conflict", "the same request is already being processed") from None
        raise
    return result


# Endpoints -------------------------------------------------------------------------------------


@router.get("/suppliers")
async def supplier_options(request: Request, user: TenantUser) -> list[SupplierOption]:
    """S12/O16 supplier dropdown (active suppliers, read-only)."""
    async with db.transaction(_pool(request), user.actor()) as conn:
        rows = await po.list_suppliers(conn, active_only=True)
    return [SupplierOption(id=r["id"], name=r["name"]) for r in rows]


@router.get("/outlets/{outlet_id}/purchase-orders")
async def outlet_pos(
    outlet_id: UUID,
    request: Request,
    user: TenantUser,
    status_filter: Annotated[po.OutletFilter | None, Query(alias="status")] = None,
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> OutletPoPage:
    """S10 Daftar PO outlet: payment status read-only, no debt totals (also for the owner).
    Chips Terbuka (`active`) / Menunggu barang (`waiting_goods`) / Ditutup (`closed`), with the
    counts for the first two."""
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        page = await po.list_pos(
            conn, "staff", outlet_id=outlet_id, status=status_filter, cursor=cursor, limit=limit
        )
        counts = await po.outlet_counts(conn, outlet_id)
    return OutletPoPage(**page, counts=OutletCounts(**counts))


@router.post("/outlets/{outlet_id}/purchase-orders", status_code=status.HTTP_201_CREATED)
async def open_po(
    outlet_id: UUID,
    body: PoCreate,
    request: Request,
    response: Response,
    user: TenantUser,
    idempotency_key: str | None = IdempotencyKey,
) -> PoDetail:
    """S12 / O16 Buka PO: no approval, creator recorded, no ledger entry or stock change."""

    async def work(conn: psycopg.AsyncConnection) -> PoDetail:
        outlet = await outlets.require_outlet(conn, outlet_id)
        po_id = await po.open_po(
            conn,
            user.actor(),
            outlet,
            supplier_id=body.supplier_id,
            ordered_on=body.ordered_on,
            payment_term=body.payment_term,
            due_date=body.due_date,
            expected_date=body.expected_date,
            lines=[line.model_dump() for line in body.lines],
            note=body.note,
        )
        return PoDetail(**await po.detail(conn, po_id, viewer(user)))

    return await idempotent(
        request,
        response,
        user,
        scope=f"po.create:{outlet_id}",
        key=idempotency_key,
        body=body.model_dump(mode="json"),
        work=work,
        model=PoDetail,
    )


@router.get("/purchase-orders/{po_id}")
async def po_form(po_id: UUID, request: Request, user: TenantUser) -> PoDetail:
    """S11 form: lines with ordered / received / remaining quantity. Staff see no payments."""
    async with db.transaction(_pool(request), user.actor()) as conn:
        return PoDetail(**await po.detail(conn, po_id, "staff"))


@router.post("/purchase-orders/{po_id}/receipts", status_code=status.HTTP_201_CREATED)
async def receive_goods(
    po_id: UUID,
    body: ReceiptIn,
    request: Request,
    response: Response,
    user: TenantUser,
    idempotency_key: str | None = IdempotencyKey,
) -> PoDetail:
    """S11 Simpan penerimaan: per line match/short; ingredient lines restock in base units."""

    async def work(conn: psycopg.AsyncConnection) -> PoDetail:
        await po.receive(
            conn,
            user.actor(),
            po_id,
            received_on=body.received_on,
            note=body.note,
            lines=[line.model_dump() for line in body.lines],
        )
        return PoDetail(**await po.detail(conn, po_id, viewer(user)))

    return await idempotent(
        request,
        response,
        user,
        scope=f"po.receive:{po_id}",
        key=idempotency_key,
        body=body.model_dump(mode="json"),
        work=work,
        model=PoDetail,
    )


@router.post("/purchase-orders/{po_id}/close")
async def close_po(po_id: UUID, request: Request, user: TenantUser) -> PoDetail:
    """S11 Tutup PO: only when every line matches; pay-in-advance POs must be paid first.
    A PO with a difference is closed by the owner with a note (owner endpoint)."""
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await po.close(conn, ctx, po_id, note=None, viewer=viewer(user))
        return PoDetail(**await po.detail(conn, po_id, viewer(user)))
