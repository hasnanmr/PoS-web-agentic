"""Owner catalog — wireframes O5 (Menu, Add-on & Harga Outlet) and O6 (Resep & Bahan).

T-016 to T-019, T-022. Contract: docs/architecture/screen-endpoint-map.md → O5, O6.
Photo upload (Supabase Storage) and WhatsApp catalog sync (T-051) come later.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status
from pydantic import BaseModel, Field, StringConstraints

from app import db
from app.auth.deps import OwnerOnly
from app.core import catalog as core

router = APIRouter(prefix="/api/v1/owner", tags=["owner: catalog"])

Quantity = Decimal
# Names are trimmed before validation: the DB requires 1-120 chars after trim.
Name120 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Name60 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Unit = Literal["g", "ml", "pcs"]
DisplayUnit = Literal["g", "kg", "ml", "L", "pcs"]
CATALOG_SYNC = "not_configured"  # WhatsApp catalog sync (T-051) is not part of the POS demo


class ProductRow(BaseModel):
    id: UUID
    name: str
    category: str | None
    is_owner_pick: bool
    is_sample: bool
    has_photo: bool
    addon_group_count: int
    ingredient_count: int
    price: int | None
    status: Literal["active", "sold_out", "inactive"]


class OutletPriceItem(BaseModel):
    outlet_id: UUID
    price: int | None = Field(default=None, ge=0, le=100_000_000)


class OutletPriceRow(BaseModel):
    outlet_id: UUID
    outlet_name: str
    price: int | None


class RecipeLine(BaseModel):
    stock_item_id: UUID
    quantity: Quantity = Field(max_digits=14, decimal_places=3)


class RecipeLineRow(RecipeLine):
    stock_item: str
    unit: Unit


class OptionPrice(BaseModel):
    outlet_id: UUID
    price: int


class AddonOptionRow(BaseModel):
    id: UUID
    name: str
    sort_order: int
    prices: list[OptionPrice]
    recipe: list[RecipeLineRow]


class AddonGroupRow(BaseModel):
    id: UUID
    name: str
    selection: Literal["single", "multiple"]
    is_required: bool
    sort_order: int
    options: list[AddonOptionRow]


class ProductDetail(BaseModel):
    id: UUID
    name: str
    category: str | None
    description: str | None
    is_owner_pick: bool
    is_active: bool
    is_sample: bool
    has_photo: bool
    tags: list[str]
    prices: list[OutletPriceRow]
    addon_groups: list[AddonGroupRow]
    catalog_sync: str = CATALOG_SYNC


class ProductCreate(BaseModel):
    name: Name120
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=500)
    is_owner_pick: bool = False
    is_active: bool = True
    tags: list[str] = Field(default_factory=list, max_length=20)


class ProductPatch(BaseModel):
    name: Name120 | None = None
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=500)
    is_owner_pick: bool | None = None
    is_active: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=20)


class AddonOptionInput(BaseModel):
    id: UUID | None = None
    name: Name60
    prices: list[OutletPriceItem] = Field(default_factory=list)


class AddonGroupInput(BaseModel):
    name: Name60
    selection: Literal["single", "multiple"] = "single"
    is_required: bool = False
    options: list[AddonOptionInput] = Field(min_length=1, max_length=10)


class StockItemRow(BaseModel):
    id: UUID
    name: str
    unit: Unit
    display_unit: DisplayUnit | None
    thresholds: list[dict[str, UUID | Decimal]]


class StockItemCreate(BaseModel):
    name: Name120
    unit: Unit
    display_unit: DisplayUnit | None = None


class StockItemPatch(BaseModel):
    name: Name120 | None = None
    display_unit: DisplayUnit | None = None


class ThresholdItem(BaseModel):
    outlet_id: UUID
    low_threshold: Quantity = Field(ge=0, max_digits=14, decimal_places=3)


class Availability(BaseModel):
    outlet_id: UUID
    outlet_name: str
    portions_available: int
    sold_out: bool
    limiting_stock_item: str | None


class Created(BaseModel):
    id: UUID
    catalog_sync: str = CATALOG_SYNC


def _pool(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.db_pool


def _prices(items: list[OutletPriceItem]) -> list[core.OutletPrice]:
    return [core.OutletPrice(p.outlet_id, p.price) for p in items]


# Products (O5) -----------------------------------------------------------------------------


@router.get("/products")
async def list_products(
    request: Request,
    owner: OwnerOnly,
    price_outlet_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=60),
    category: str | None = None,
    status_filter: Literal["all", "active", "sold_out", "inactive"] = Query("all", alias="status"),
) -> list[ProductRow]:
    async with db.transaction(_pool(request), owner.actor()) as conn:
        rows = await core.list_products(
            conn, price_outlet_id=price_outlet_id, q=q, category=category, status=status_filter
        )
    return [ProductRow(**r) for r in rows]


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(body: ProductCreate, request: Request, owner: OwnerOnly) -> ProductDetail:
    ctx = owner.actor()
    fields = body.model_dump(exclude={"tags"})
    async with db.transaction(_pool(request), ctx) as conn:
        product_id = await core.create_product(conn, ctx, fields, body.tags)
        row = await core.get_product(conn, product_id)
    return ProductDetail(**row)


@router.get("/products/{product_id}")
async def get_product(product_id: UUID, request: Request, owner: OwnerOnly) -> ProductDetail:
    async with db.transaction(_pool(request), owner.actor()) as conn:
        row = await core.get_product(conn, product_id)
    return ProductDetail(**row)


@router.patch("/products/{product_id}")
async def update_product(
    product_id: UUID, body: ProductPatch, request: Request, owner: OwnerOnly
) -> ProductDetail:
    ctx = owner.actor()
    sent = body.model_dump(exclude_unset=True)
    tags = sent.pop("tags", None)
    fields = {k: v for k, v in sent.items() if v is not None or k in ("category", "description")}
    async with db.transaction(_pool(request), ctx) as conn:
        await core.update_product(conn, ctx, product_id, fields, tags)
        row = await core.get_product(conn, product_id)
    return ProductDetail(**row)


@router.delete("/products/{product_id}")
async def delete_product(product_id: UUID, request: Request, owner: OwnerOnly) -> dict[str, str]:
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        outcome = await core.delete_product(conn, ctx, product_id)
    return {"result": outcome}


@router.put("/products/{product_id}/prices")
async def set_prices(
    product_id: UUID, body: list[OutletPriceItem], request: Request, owner: OwnerOnly
) -> list[OutletPriceRow]:
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await core.set_product_prices(conn, ctx, product_id, _prices(body))
        row = await core.get_product(conn, product_id)
    return [OutletPriceRow(**p) for p in row["prices"]]


# Add-on groups (O5) ------------------------------------------------------------------------


async def _save_group(
    request: Request,
    owner: OwnerOnly,
    body: AddonGroupInput,
    *,
    product_id: UUID | None,
    group_id: UUID | None,
) -> ProductDetail:
    ctx = owner.actor()
    options = [core.OptionInput(o.id, o.name, _prices(o.prices)) for o in body.options]
    async with db.transaction(_pool(request), ctx) as conn:
        gid = await core.save_addon_group(
            conn,
            ctx,
            product_id=product_id,
            group_id=group_id,
            name=body.name,
            selection=body.selection,
            is_required=body.is_required,
            options=options,
        )
        cur = await conn.execute("select product_id from app.addon_groups where id = %s", (gid,))
        pid = (await cur.fetchone())[0]  # type: ignore[index]
        row = await core.get_product(conn, pid)
    return ProductDetail(**row)


@router.post("/products/{product_id}/addon-groups", status_code=status.HTTP_201_CREATED)
async def create_addon_group(
    product_id: UUID, body: AddonGroupInput, request: Request, owner: OwnerOnly
) -> ProductDetail:
    return await _save_group(request, owner, body, product_id=product_id, group_id=None)


@router.patch("/addon-groups/{group_id}")
async def update_addon_group(
    group_id: UUID, body: AddonGroupInput, request: Request, owner: OwnerOnly
) -> ProductDetail:
    return await _save_group(request, owner, body, product_id=None, group_id=group_id)


@router.delete("/addon-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_addon_group(group_id: UUID, request: Request, owner: OwnerOnly) -> Response:
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await core.delete_addon_group(conn, ctx, group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/products/{product_id}/addon-groups/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_addon_groups(
    product_id: UUID, body: list[UUID], request: Request, owner: OwnerOnly
) -> Response:
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await core.reorder_addon_groups(conn, ctx, product_id, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Recipes (O6) ------------------------------------------------------------------------------


@router.get("/products/{product_id}/recipe")
async def get_product_recipe(
    product_id: UUID, request: Request, owner: OwnerOnly
) -> list[RecipeLineRow]:
    async with db.transaction(_pool(request), owner.actor()) as conn:
        await core.get_product(conn, product_id)
        rows = await core.get_recipe(conn, product_id=product_id)
    return [RecipeLineRow(**r) for r in rows]


@router.put("/products/{product_id}/recipe")
async def set_product_recipe(
    product_id: UUID, body: list[RecipeLine], request: Request, owner: OwnerOnly
) -> list[RecipeLineRow]:
    ctx = owner.actor()
    lines = [(line.stock_item_id, line.quantity) for line in body]
    async with db.transaction(_pool(request), ctx) as conn:
        await core.set_recipe(conn, ctx, lines, product_id=product_id)
        rows = await core.get_recipe(conn, product_id=product_id)
    return [RecipeLineRow(**r) for r in rows]


@router.get("/addon-options/{option_id}/recipe")
async def get_option_recipe(
    option_id: UUID, request: Request, owner: OwnerOnly
) -> list[RecipeLineRow]:
    async with db.transaction(_pool(request), owner.actor()) as conn:
        rows = await core.get_recipe(conn, option_id=option_id)
    return [RecipeLineRow(**r) for r in rows]


@router.put("/addon-options/{option_id}/recipe")
async def set_option_recipe(
    option_id: UUID, body: list[RecipeLine], request: Request, owner: OwnerOnly
) -> list[RecipeLineRow]:
    ctx = owner.actor()
    lines = [(line.stock_item_id, line.quantity) for line in body]
    async with db.transaction(_pool(request), ctx) as conn:
        await core.set_recipe(conn, ctx, lines, option_id=option_id)
        rows = await core.get_recipe(conn, option_id=option_id)
    return [RecipeLineRow(**r) for r in rows]


@router.get("/products/{product_id}/availability")
async def product_availability(
    product_id: UUID, request: Request, owner: OwnerOnly
) -> list[Availability]:
    async with db.transaction(_pool(request), owner.actor()) as conn:
        rows = await core.product_availability(conn, product_id)
    return [Availability(**r) for r in rows]


# Stock items (O6 "Daftar bahan", "Threshold per outlet") ----------------------------------


@router.get("/stock-items")
async def list_stock_items(request: Request, owner: OwnerOnly) -> list[StockItemRow]:
    async with db.transaction(_pool(request), owner.actor()) as conn:
        rows = await core.list_stock_items(conn)
    return [StockItemRow(**r) for r in rows]


@router.post("/stock-items", status_code=status.HTTP_201_CREATED)
async def create_stock_item(body: StockItemCreate, request: Request, owner: OwnerOnly) -> Created:
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        item_id = await core.create_stock_item(conn, ctx, **body.model_dump())
    return Created(id=item_id)


@router.patch("/stock-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_stock_item(
    item_id: UUID, body: StockItemPatch, request: Request, owner: OwnerOnly
) -> Response:
    ctx = owner.actor()
    fields = body.model_dump(exclude_unset=True)
    if fields.get("name") is None:
        fields.pop("name", None)
    async with db.transaction(_pool(request), ctx) as conn:
        await core.update_stock_item(conn, ctx, item_id, fields)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/stock-items/{item_id}/thresholds", status_code=status.HTTP_204_NO_CONTENT)
async def set_thresholds(
    item_id: UUID, body: list[ThresholdItem], request: Request, owner: OwnerOnly
) -> Response:
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await core.set_thresholds(conn, ctx, item_id, {t.outlet_id: t.low_threshold for t in body})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
