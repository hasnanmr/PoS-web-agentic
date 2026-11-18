"""S4 · Review Pembayaran QRIS (T-037) for owner and staff.

Contract: docs/architecture/screen-endpoint-map.md → S4. Screenshots arrive from WhatsApp
(T-036); this router only reviews them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app import db
from app.api.errors import ApiError
from app.auth.deps import TenantUser
from app.core import outlets, proofs

router = APIRouter(prefix="/api/v1/ops", tags=["ops: payment proofs"])


class ProofQueueItem(BaseModel):
    proof_id: UUID
    order_id: UUID
    order_no: str
    channel: str
    order_type: str
    table: str | None
    total: int
    received_at: datetime
    timezone: str


class ProofDetail(BaseModel):
    proof_id: UUID
    status: Literal["pending", "accepted", "rejected"]
    image_url: str | None
    order_id: UUID
    order_no: str
    channel: str
    order_type: str
    table: str | None
    total: int
    order_status: str
    payment_status: str
    customer_phone_masked: str | None
    received_at: datetime
    timezone: str
    timer_stopped: bool
    reviewed_by: str | None
    reviewed_at: datetime | None
    rejection_reason: str | None


class AcceptIn(BaseModel):
    merchant_account_checked: bool


class RejectIn(BaseModel):
    reason: str = Field(max_length=300)


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


@router.get("/outlets/{outlet_id}/payment-proofs")
async def proof_queue(
    outlet_id: UUID,
    request: Request,
    user: TenantUser,
    status: Literal["pending"] = "pending",
) -> list[ProofQueueItem]:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        rows = await proofs.pending_queue(conn, outlet_id)
    return [ProofQueueItem(**r) for r in rows]


@router.get("/payment-proofs/{proof_id}")
async def proof_detail(proof_id: UUID, request: Request, user: TenantUser) -> ProofDetail:
    async with db.transaction(_pool(request), user.actor()) as conn:
        row = await proofs.detail(conn, proof_id)
    return ProofDetail(**row)


@router.post("/payment-proofs/{proof_id}/accept")
async def accept_proof(
    proof_id: UUID, body: AcceptIn, request: Request, user: TenantUser
) -> ProofDetail:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        row = await proofs.accept(
            conn, ctx, proof_id, merchant_account_checked=body.merchant_account_checked
        )
    return ProofDetail(**row)


@router.post("/payment-proofs/{proof_id}/reject")
async def reject_proof(
    proof_id: UUID, body: RejectIn, request: Request, user: TenantUser
) -> ProofDetail:
    if not body.reason.strip():
        raise ApiError(422, "reason_required", "a reason is required to reject a proof")
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        row = await proofs.reject(conn, ctx, proof_id, body.reason)
    return ProofDetail(**row)
