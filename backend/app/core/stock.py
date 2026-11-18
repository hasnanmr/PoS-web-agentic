"""Stock levels, movements, and menu availability (T-020, T-021, T-022) — S7, O6, S1.

Stock lives in base units (g, ml, pcs) per outlet in `app.outlet_stock.on_hand`, which
only the movement trigger changes; movements are append-only. A product is sold out at
an outlet when any recipe ingredient is below one portion; an add-on option is
unavailable when one portion with that option cannot be made (FR4.7, AC4.7).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row

from app.core.actor import ActorContext
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.units import NegativeQuantityError, portions_available, recipe_with_addons

ZERO = Decimal("0.000")
StockStatus = Literal["ok", "low", "out"]
ManualMovement = Literal["restock", "waste", "adjustment"]


@dataclass(slots=True)
class Recipes:
    products: dict[UUID, dict[UUID, Decimal]] = field(default_factory=lambda: defaultdict(dict))
    options: dict[UUID, dict[UUID, Decimal]] = field(default_factory=lambda: defaultdict(dict))


@dataclass(frozen=True, slots=True)
class ProductAvailability:
    portions: int
    sold_out: bool
    limiting_stock_item_id: UUID | None  # None also when the product has no recipe


async def load_recipes(conn: AsyncConnection) -> Recipes:
    recipes = Recipes()
    cur = await conn.execute(
        "select product_id, addon_option_id, stock_item_id, quantity from app.recipe_items"
    )
    for product_id, option_id, stock_item_id, qty in await cur.fetchall():
        if product_id is not None:
            recipes.products[product_id][stock_item_id] = qty
        else:
            recipes.options[option_id][stock_item_id] = qty
    return recipes


async def on_hand(conn: AsyncConnection, outlet_id: UUID) -> dict[UUID, Decimal]:
    cur = await conn.execute(
        "select stock_item_id, on_hand from app.outlet_stock where outlet_id = %s", (outlet_id,)
    )
    return {r[0]: r[1] for r in await cur.fetchall()}


def product_availability(
    recipe: dict[UUID, Decimal], stock: dict[UUID, Decimal]
) -> ProductAvailability:
    if not recipe:
        # Every product needs at least one ingredient (O6 note); without one it cannot be sold.
        return ProductAvailability(0, True, None)
    portions = portions_available(stock, recipe)
    limiting = min(recipe, key=lambda k: stock.get(k, ZERO) / recipe[k])
    return ProductAvailability(portions, portions < 1, limiting)


def option_available(
    base: dict[UUID, Decimal], delta: dict[UUID, Decimal], stock: dict[UUID, Decimal]
) -> bool:
    if not delta:
        return True
    try:
        combined = recipe_with_addons(base, [delta])
    except NegativeQuantityError:
        return False
    if not combined:
        return True
    return portions_available(stock, combined) >= 1


def stock_status(qty: Decimal, threshold: Decimal) -> StockStatus:
    if qty <= 0:
        return "out"
    if threshold > 0 and qty <= threshold:
        return "low"
    return "ok"


async def stock_view(
    conn: AsyncConnection, outlet_id: UUID, *, status: str = "all", q: str | None = None
) -> dict[str, Any]:
    """S7 table: every active stock item with level, threshold, status, affected menu."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select si.id as stock_item_id, si.name, si.unit::text as unit, si.display_unit,
               coalesce(os.on_hand, 0) as on_hand, coalesce(os.low_threshold, 0) as low_threshold
        from app.stock_items si
        left join app.outlet_stock os on os.stock_item_id = si.id and os.outlet_id = %s
        where si.is_active
        order by si.name
        """,
        (outlet_id,),
    )
    items = await cur.fetchall()
    recipes = await load_recipes(conn)
    stock = {i["stock_item_id"]: i["on_hand"] for i in items}
    await cur.execute(
        """
        select p.id, p.name from app.products p where p.is_active
        """
    )
    products = {r["id"]: r["name"] for r in await cur.fetchall()}
    await cur.execute(
        """
        select o.id, o.name, g.product_id from app.addon_options o
        join app.addon_groups g on g.id = o.group_id where o.is_active
        """
    )
    options = {r["id"]: (r["name"], r["product_id"]) for r in await cur.fetchall()}

    counts = {"low": 0, "out": 0}
    rows = []
    needle = (q or "").strip().lower()
    for item in items:
        item["status"] = stock_status(item["on_hand"], item["low_threshold"])
        if item["status"] in counts:
            counts[item["status"]] += 1
        affected: list[dict[str, Any]] = []
        if item["status"] != "ok":
            sid = item["stock_item_id"]
            for pid, recipe in recipes.products.items():
                if sid in recipe and pid in products:
                    sold_out = product_availability(recipe, stock).sold_out
                    affected.append(
                        {"name": products[pid], "kind": "product", "sold_out": sold_out}
                    )
            for oid, delta in recipes.options.items():
                if delta.get(sid, ZERO) > 0 and oid in options:
                    name, pid = options[oid]
                    available = option_available(recipes.products.get(pid, {}), delta, stock)
                    affected.append({"name": name, "kind": "addon", "sold_out": not available})
        item["affected_products"] = affected
        if status in ("low", "out") and item["status"] != status:
            continue
        if needle and needle not in item["name"].lower():
            continue
        rows.append(item)
    return {"counts": counts, "items": rows}


async def record_movement(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    *,
    type: ManualMovement,
    stock_item_id: UUID,
    quantity: Decimal,
    note: str | None = None,
) -> int:
    """Staff/owner movement from S7. Restock and waste take a positive amount; adjustment is
    signed. Stock can never go below zero (the DB check rejects it)."""
    if quantity == 0:
        raise ValidationFailedError("quantity must not be zero", {"field": "quantity"})
    if type in ("restock", "waste") and quantity < 0:
        raise ValidationFailedError("enter a positive amount", {"field": "quantity"})
    signed = -quantity if type == "waste" else quantity
    cur = await conn.execute(
        "select 1 from app.stock_items where id = %s and is_active", (stock_item_id,)
    )
    if await cur.fetchone() is None:
        raise NotFoundError("stock item")
    try:
        async with conn.transaction():
            cur = await conn.execute(
                """
                insert into app.stock_movements
                  (tenant_id, outlet_id, stock_item_id, type, quantity, note, actor_type, actor_id)
                values (%s, %s, %s, %s, %s, %s, %s, %s) returning id
                """,
                (
                    ctx.tenant_id,
                    outlet_id,
                    stock_item_id,
                    type,
                    signed,
                    note,
                    ctx.actor_type.value,
                    ctx.actor_id,
                ),
            )
            row = await cur.fetchone()
    except errors.CheckViolation:
        raise ConflictError(
            "insufficient_stock",
            "stock cannot go below zero",
            {"stock_item_id": str(stock_item_id)},
        ) from None
    assert row is not None  # noqa: S101
    return int(row[0])


async def movement_history(
    conn: AsyncConnection,
    outlet_id: UUID,
    *,
    stock_item_id: UUID | None = None,
    cursor: int | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int | None]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select m.id, m.created_at as at, m.type::text as type, m.quantity, si.unit::text as unit,
               si.display_unit, si.name as stock_item, o.order_no, ou.order_prefix, m.note,
               m.actor_type::text as actor_type, u.display_name as actor_name
        from app.stock_movements m
        join app.stock_items si on si.id = m.stock_item_id
        join app.outlets ou on ou.id = m.outlet_id
        left join app.orders o on o.id = m.order_id
        left join app.users u on u.id = m.actor_id
        where m.outlet_id = %s
          and (%s::uuid is null or m.stock_item_id = %s)
          and (%s::bigint is null or m.id < %s)
        order by m.id desc
        limit %s
        """,
        (outlet_id, stock_item_id, stock_item_id, cursor, cursor, limit + 1),
    )
    rows = await cur.fetchall()
    next_cursor = rows[limit - 1]["id"] if len(rows) > limit else None
    out = []
    for r in rows[:limit]:
        prefix = r.pop("order_prefix")
        order_no = r.pop("order_no")
        r["order_no"] = f"#{prefix}-{order_no}" if order_no is not None else None
        r["actor"] = r.pop("actor_name") or r["actor_type"]
        out.append(r)
    return out, next_cursor
