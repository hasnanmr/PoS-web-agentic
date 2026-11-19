"""Owner purchase orders — O15 (PO list, detail, Catat pembayaran, Batalkan, Tutup dengan
catatan, Daftar supplier). Payments, cancellation, close-with-note, suppliers and debt are
owner-only (FR1.5). Opening a PO (O16) and the goods check (S11) use the /ops endpoints.

Contract: docs/architecture/screen-endpoint-map.md → O15.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Query, Request, Response, status
from pydantic import BaseModel, Field

from app import db
from app.api.v1.ops.purchase_orders import IdempotencyKey, PoDetail, PoPage, idempotent
from app.auth.deps import OwnerOnly
from app.core import outlets
from app.core import purchase_orders as po

router = APIRouter(prefix="/api/v1/owner", tags=["owner: purchase orders"])


class Supplier(BaseModel):
    id: UUID
    name: str
    phone: str | None
    note: str | None
    is_active: bool


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=300)


class SupplierPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=300)
    is_active: bool | None = None


class PaymentIn(BaseModel):
    paid_on: date
    amount: int = Field(gt=0, le=po.MAX_AMOUNT)
    method: Literal["cash", "transfer"]
    drawer_id: UUID | None = Field(
        default=None, description="Cash taken from this drawer's open shift"
    )


class CancelIn(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


class CloseIn(BaseModel):
    note: str = Field(min_length=1, max_length=300)


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


# Suppliers ------------------------------------------------------------------------------------


@router.get("/suppliers")
async def list_suppliers(request: Request, user: OwnerOnly) -> list[Supplier]:
    async with db.transaction(_pool(request), user.actor()) as conn:
        return [Supplier(**r) for r in await po.list_suppliers(conn, active_only=False)]


@router.post("/suppliers", status_code=status.HTTP_201_CREATED)
async def create_supplier(body: SupplierIn, request: Request, user: OwnerOnly) -> Supplier:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        return Supplier(
            **await po.create_supplier(conn, ctx, name=body.name, phone=body.phone, note=body.note)
        )


@router.patch("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: UUID, body: SupplierPatch, request: Request, user: OwnerOnly
) -> Supplier:
    changes = body.model_dump(exclude_unset=True)
    if changes.get("is_active") is None:
        changes.pop("is_active", None)
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        return Supplier(**await po.update_supplier(conn, ctx, supplier_id, changes))


# Purchase orders -------------------------------------------------------------------------------


@router.get("/purchase-orders")
async def list_pos(
    request: Request,
    user: OwnerOnly,
    outlet_id: UUID | None = None,
    status_filter: Annotated[po.ListFilter | None, Query(alias="status")] = None,
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> PoPage:
    """O15 list with the chips Semua / Terbuka / Ada selisih / Menunggu bayar / Overdue /
    Ditutup. Menunggu bayar and Overdue come as one page, most urgent due date first."""
    async with db.transaction(_pool(request), user.actor()) as conn:
        if outlet_id:
            await outlets.require_outlet(conn, outlet_id)
        page = await po.list_pos(
            conn, "owner", outlet_id=outlet_id, status=status_filter, cursor=cursor, limit=limit
        )
    return PoPage(**page)


@router.get("/purchase-orders/{po_id}")
async def po_detail(po_id: UUID, request: Request, user: OwnerOnly) -> PoDetail:
    async with db.transaction(_pool(request), user.actor()) as conn:
        return PoDetail(**await po.detail(conn, po_id, "owner"))


@router.post("/purchase-orders/{po_id}/payments", status_code=status.HTTP_201_CREATED)
async def record_payment(
    po_id: UUID,
    body: PaymentIn,
    request: Request,
    response: Response,
    user: OwnerOnly,
    idempotency_key: str | None = IdempotencyKey,
) -> PoDetail:
    """Catat pembayaran: one `expense` ledger entry on `paid_on`; never above what is owed."""

    async def work(conn: psycopg.AsyncConnection) -> PoDetail:
        await po.record_payment(
            conn,
            user.actor(),
            po_id,
            paid_on=body.paid_on,
            amount=body.amount,
            method=body.method,
            drawer_id=body.drawer_id,
        )
        return PoDetail(**await po.detail(conn, po_id, "owner"))

    return await idempotent(
        request,
        response,
        user,
        scope=f"po.payment:{po_id}",
        key=idempotency_key,
        body=body.model_dump(mode="json"),
        work=work,
        model=PoDetail,
    )


@router.post("/purchase-orders/{po_id}/cancel")
async def cancel_po(po_id: UUID, body: CancelIn, request: Request, user: OwnerOnly) -> PoDetail:
    """Batalkan PO: reason required; refused once paid or any goods were received."""
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await po.cancel(conn, ctx, po_id, body.reason)
        return PoDetail(**await po.detail(conn, po_id, "owner"))


@router.post("/purchase-orders/{po_id}/close")
async def close_with_note(
    po_id: UUID, body: CloseIn, request: Request, user: OwnerOnly
) -> PoDetail:
    """Tutup dengan catatan: only for a PO with a difference. Pay later then owes
    received x unit price."""
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await po.close(conn, ctx, po_id, note=body.note, viewer="owner")
        return PoDetail(**await po.detail(conn, po_id, "owner"))
