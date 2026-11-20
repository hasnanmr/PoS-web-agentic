"""Owner recommendations — wireframe O7 "Rekomendasi" (T-073).

Contract: docs/architecture/screen-endpoint-map.md → O7. Tags are edited on the product
(O5, `PATCH /owner/products/{id}`); O7 only lists them.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from app import db
from app.auth.deps import OwnerOnly
from app.core import outlets
from app.core import recommendations as core

router = APIRouter(prefix="/api/v1/owner", tags=["owner: recommendations"])

SkippedReason = Literal["sold_out", "duplicate", "unavailable"]


class PickRow(BaseModel):
    product_id: UUID
    name: str
    category: str | None
    is_active: bool
    tags: list[str]


class PicksBody(BaseModel):
    product_ids: list[UUID] = Field(
        max_length=core.MAX_PICKS, description="All picks, in the order shown to customers"
    )


class PreviewItem(BaseModel):
    product_id: UUID
    name: str
    position: int | None = Field(description="Place in the customer's list; null when skipped")
    skipped_reason: SkippedReason | None


class BestSellerItem(PreviewItem):
    units_30d: int


class RecommendationPreview(BaseModel):
    picks: list[PreviewItem]
    best_sellers: list[BestSellerItem]
    listed_count: int
    max_items: int = core.MAX_ITEMS


def _pool(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.db_pool


@router.get("/owner-picks")
async def get_owner_picks(request: Request, owner: OwnerOnly) -> list[PickRow]:
    async with db.transaction(_pool(request), owner.actor()) as conn:
        return [PickRow(**r) for r in await core.list_picks(conn)]


@router.put("/owner-picks", status_code=status.HTTP_204_NO_CONTENT)
async def put_owner_picks(body: PicksBody, request: Request, owner: OwnerOnly) -> Response:
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await core.set_picks(conn, ctx, body.product_ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tags")
async def get_tags(request: Request, owner: OwnerOnly) -> list[str]:
    async with db.transaction(_pool(request), owner.actor()) as conn:
        return await core.list_tags(conn)


@router.get("/outlets/{outlet_id}/recommendation-preview")
async def recommendation_preview(
    outlet_id: UUID, request: Request, owner: OwnerOnly
) -> RecommendationPreview:
    async with db.transaction(_pool(request), owner.actor()) as conn:
        await outlets.get_outlet(conn, outlet_id)  # 404 for an outlet outside the tenant
        return RecommendationPreview(**await core.recommendation_list(conn, outlet_id))
