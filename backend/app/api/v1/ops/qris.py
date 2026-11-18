"""PoC demo QRIS: the outlet's static QRIS image for S1/S5, and the S2 cross-check.

Contract: docs/architecture/screen-endpoint-map.md → O3 "QRIS statis", S1, S2, S5.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app import db
from app.api.v1.ops.orders import OrderDetail
from app.auth.deps import TenantUser
from app.core import qris

router = APIRouter(prefix="/api/v1/ops", tags=["ops: qris"])


class QrisCheckIn(BaseModel):
    merchant_account_checked: bool


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


@router.get(
    "/outlets/{outlet_id}/qris/image",
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}, 404: {}},
)
async def qris_image(outlet_id: UUID, request: Request, user: TenantUser) -> Response:
    """The outlet's static QRIS, shown to the customer at the counter and at bill close."""
    async with db.transaction(_pool(request), user.actor()) as conn:
        content_type, data = await qris.image(conn, outlet_id)
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "no-store"})


@router.post("/orders/{order_id}/qris-check")
async def qris_check(
    order_id: UUID, body: QrisCheckIn, request: Request, user: TenantUser
) -> OrderDetail:
    """S2 "Cek →": the QRIS payment was found in the receiving account."""
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        row = await qris.check_order(
            conn, ctx, order_id, merchant_account_checked=body.merchant_account_checked
        )
    return OrderDetail(**row)
