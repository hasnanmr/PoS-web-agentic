"""Order quote: prices, add-ons, PB1, totals (T-027). One function for every channel.

The server is the only source of prices and PB1 (S1 note). Lines are validated against
the outlet's prices and the product's add-on rules: required groups need a choice,
single-choice groups take at most one option, and every product and option must be
active and priced at the outlet.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.errors import DomainError, ValidationFailedError
from app.core.tax import Pb1Setting, Quote, line_total, quote_totals

MAX_QUANTITY = 999


@dataclass(frozen=True, slots=True)
class LineInput:
    product_id: UUID
    quantity: int
    addon_option_ids: tuple[UUID, ...] = ()
    note: str | None = None


@dataclass(frozen=True, slots=True)
class PricedAddon:
    option_id: UUID
    name: str
    price: int


@dataclass(frozen=True, slots=True)
class PricedLine:
    product_id: UUID
    name: str
    unit_price: int
    quantity: int
    addons: tuple[PricedAddon, ...]
    line_total: int
    note: str | None = None


@dataclass(frozen=True, slots=True)
class PricedOrder:
    lines: tuple[PricedLine, ...]
    quote: Quote
    extra: dict[str, Any] = field(default_factory=dict)


class InvalidLineError(DomainError):
    status_code = 422

    def __init__(self, code: str, message: str, product_id: UUID, **details: Any) -> None:
        super().__init__(code, message, {"product_id": str(product_id), **details})


async def outlet_pb1(conn: AsyncConnection, outlet_id: UUID) -> Pb1Setting:
    cur = await conn.execute(
        "select pb1_enabled, pb1_rate_bps from app.outlets where id = %s", (outlet_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise ValidationFailedError("unknown outlet", {"field": "outlet_id"})
    return Pb1Setting(enabled=row[0], rate_bps=row[1])


async def price_lines(
    conn: AsyncConnection, outlet_id: UUID, lines: list[LineInput]
) -> tuple[PricedLine, ...]:
    if not lines:
        raise ValidationFailedError("the cart is empty", {"field": "items"})
    product_ids = list({line.product_id for line in lines})
    option_ids = list({o for line in lines for o in line.addon_option_ids})
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select p.id, p.name, p.is_active, op.price
        from app.products p
        left join app.outlet_prices op on op.product_id = p.id and op.outlet_id = %s
        where p.id = any(%s)
        """,
        (outlet_id, product_ids),
    )
    products = {r["id"]: r for r in await cur.fetchall()}
    await cur.execute(
        """
        select g.id, g.product_id, g.name, g.selection::text as selection, g.is_required
        from app.addon_groups g where g.product_id = any(%s)
        """,
        (product_ids,),
    )
    groups = await cur.fetchall()
    groups_by_product: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for g in groups:
        groups_by_product[g["product_id"]].append(g)
    await cur.execute(
        """
        select o.id, o.group_id, o.name, o.is_active, op.price
        from app.addon_options o
        left join app.outlet_prices op on op.addon_option_id = o.id and op.outlet_id = %s
        where o.id = any(%s)
        """,
        (outlet_id, option_ids),
    )
    options = {r["id"]: r for r in await cur.fetchall()}

    priced: list[PricedLine] = []
    for line in lines:
        product = products.get(line.product_id)
        if product is None or not product["is_active"]:
            raise InvalidLineError("item_unavailable", "item is not on the menu", line.product_id)
        if product["price"] is None:
            raise InvalidLineError(
                "item_unavailable",
                f"{product['name']} has no price at this outlet",
                line.product_id,
                name=product["name"],
            )
        if not 1 <= line.quantity <= MAX_QUANTITY:
            raise ValidationFailedError("quantity must be 1 to 999", {"field": "quantity"})
        product_groups = {g["id"]: g for g in groups_by_product.get(line.product_id, [])}
        chosen_by_group: dict[UUID, list[UUID]] = defaultdict(list)
        addons: list[PricedAddon] = []
        if len(set(line.addon_option_ids)) != len(line.addon_option_ids):
            raise InvalidLineError(
                "addon_invalid", "the same add-on was chosen twice", line.product_id
            )
        for option_id in line.addon_option_ids:
            option = options.get(option_id)
            if (
                option is None
                or option["group_id"] not in product_groups
                or not option["is_active"]
            ):
                raise InvalidLineError(
                    "addon_invalid",
                    "add-on does not belong to this item",
                    line.product_id,
                    addon_option_id=str(option_id),
                )
            if option["price"] is None:
                raise InvalidLineError(
                    "addon_invalid",
                    f"{option['name']} has no price at this outlet",
                    line.product_id,
                    addon_option_id=str(option_id),
                )
            chosen_by_group[option["group_id"]].append(option_id)
            addons.append(PricedAddon(option_id, option["name"], option["price"]))
        for gid, group in product_groups.items():
            chosen = chosen_by_group.get(gid, [])
            if group["is_required"] and not chosen:
                raise InvalidLineError(
                    "addon_required",
                    f"choose {group['name']}",
                    line.product_id,
                    group=group["name"],
                )
            if group["selection"] == "single" and len(chosen) > 1:
                raise InvalidLineError(
                    "addon_invalid",
                    f"choose one {group['name']}",
                    line.product_id,
                    group=group["name"],
                )
        priced.append(
            PricedLine(
                product_id=line.product_id,
                name=product["name"],
                unit_price=product["price"],
                quantity=line.quantity,
                addons=tuple(addons),
                line_total=line_total(product["price"], [a.price for a in addons], line.quantity),
                note=line.note,
            )
        )
    return tuple(priced)


async def quote(
    conn: AsyncConnection, outlet_id: UUID, lines: list[LineInput], *, delivery_fee: int = 0
) -> PricedOrder:
    priced = await price_lines(conn, outlet_id, lines)
    setting = await outlet_pb1(conn, outlet_id)
    totals = quote_totals(sum(p.line_total for p in priced), setting, delivery_fee)
    return PricedOrder(lines=priced, quote=totals)
