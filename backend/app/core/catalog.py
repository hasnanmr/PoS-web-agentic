"""Menu items, add-ons, outlet prices, stock items, and recipes (T-016 to T-019, T-022).

Screens O5 (Menu, Add-on & Harga Outlet) and O6 (Resep & Bahan). Products, add-ons,
stock items, and recipes are tenant-level; prices, stock, and thresholds are per
outlet. Runs inside `app.db.transaction`, so RLS limits everything to the tenant.
Catalog sync to WhatsApp (T-051) is not part of the POS demo; saves report
`catalog_sync: "not_configured"` until it exists.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row

from app.core import stock as stock_core
from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, DomainError, NotFoundError, ValidationFailedError

ProductStatus = Literal["active", "sold_out", "inactive"]
MAX_OPTIONS = 10

PRODUCT_FIELDS = ("name", "category", "description", "is_owner_pick", "is_active")


# Products -------------------------------------------------------------------------------


async def list_products(
    conn: AsyncConnection,
    *,
    price_outlet_id: UUID | None,
    q: str | None = None,
    category: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select p.id, p.name, p.category, p.is_owner_pick, p.is_sample, p.is_active,
               p.photo_path is not null as has_photo, p.photo_path,
               (select count(*) from app.addon_groups g where g.product_id = p.id)
                 as addon_group_count,
               (select count(*) from app.recipe_items r where r.product_id = p.id)
                 as ingredient_count,
               op.price
        from app.products p
        left join app.outlet_prices op on op.product_id = p.id and op.outlet_id = %s
        order by p.is_owner_pick desc, coalesce(p.owner_pick_rank, 999),
                 p.category nulls last, p.name
        """,
        (price_outlet_id,),
    )
    rows = await cur.fetchall()
    recipes = await stock_core.load_recipes(conn)
    stock = await stock_core.on_hand(conn, price_outlet_id) if price_outlet_id else {}
    needle = (q or "").strip().lower()
    out = []
    for r in rows:
        if not r["is_active"]:
            r["status"] = "inactive"
        elif (
            price_outlet_id
            and stock_core.product_availability(recipes.products.get(r["id"], {}), stock).sold_out
        ):
            r["status"] = "sold_out"
        else:
            r["status"] = "active"
        if needle and needle not in r["name"].lower():
            continue
        if category and r["category"] != category:
            continue
        if status and status != "all" and r["status"] != status:
            continue
        out.append(r)
    return out


async def get_product(conn: AsyncConnection, product_id: UUID) -> dict[str, Any]:
    """O5 edit panel: fields, tags, prices per outlet, add-on groups with options."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, name, category, description, is_owner_pick, is_active, is_sample,"
        " photo_path is not null as has_photo, photo_path from app.products where id = %s",
        (product_id,),
    )
    product = await cur.fetchone()
    if product is None:
        raise NotFoundError("product")
    await cur.execute(
        "select tag from app.product_tags where product_id = %s order by tag", (product_id,)
    )
    product["tags"] = [r["tag"] for r in await cur.fetchall()]
    await cur.execute(
        """
        select o.id as outlet_id, o.name as outlet_name, op.price
        from app.outlets o
        left join app.outlet_prices op on op.outlet_id = o.id and op.product_id = %s
        where o.is_active order by o.created_at
        """,
        (product_id,),
    )
    product["prices"] = await cur.fetchall()
    product["addon_groups"] = await _addon_groups(conn, product_id)
    return product


async def _addon_groups(conn: AsyncConnection, product_id: UUID) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, name, selection::text as selection, is_required, max_select, sort_order"
        " from app.addon_groups where product_id = %s order by sort_order, created_at",
        (product_id,),
    )
    groups = await cur.fetchall()
    if not groups:
        return []
    await cur.execute(
        """
        select o.id, o.group_id, o.name, o.sort_order,
               coalesce(json_agg(json_build_object('outlet_id', op.outlet_id, 'price', op.price))
                        filter (where op.outlet_id is not null), '[]') as prices
        from app.addon_options o
        left join app.outlet_prices op on op.addon_option_id = o.id
        where o.group_id = any(%s) and o.is_active
        group by o.id order by o.sort_order, o.created_at
        """,
        ([g["id"] for g in groups],),
    )
    options = await cur.fetchall()
    recipes = await stock_core.load_recipes(conn)
    names = await _stock_item_names(conn)
    by_group: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for o in options:
        o["recipe"] = [
            {
                "stock_item_id": sid,
                "stock_item": names.get(sid, ("?", "pcs"))[0],
                "unit": names.get(sid, ("?", "pcs"))[1],
                "quantity": qty,
            }
            for sid, qty in recipes.options.get(o["id"], {}).items()
        ]
        by_group[o.pop("group_id")].append(o)
    for g in groups:
        g["options"] = by_group.get(g["id"], [])
    return groups


async def _stock_item_names(conn: AsyncConnection) -> dict[UUID, tuple[str, str]]:
    cur = await conn.execute("select id, name, unit::text from app.stock_items")
    return {r[0]: (r[1], r[2]) for r in await cur.fetchall()}


def _clean_tags(tags: list[str]) -> list[str]:
    cleaned = sorted({t.strip().lower() for t in tags if t.strip()})
    if any(len(t) > 40 for t in cleaned):
        raise ValidationFailedError("tags are at most 40 characters", {"field": "tags"})
    return cleaned


async def _set_tags(
    conn: AsyncConnection, ctx: ActorContext, product_id: UUID, tags: list[str]
) -> None:
    await conn.execute("delete from app.product_tags where product_id = %s", (product_id,))
    for tag in _clean_tags(tags):
        await conn.execute(
            "insert into app.product_tags (product_id, tenant_id, tag) values (%s, %s, %s)",
            (product_id, ctx.tenant_id, tag),
        )


class PhotoRequiredError(DomainError):
    """FR2.11 / US-005: every menu item needs a photo (Meta requires one for catalog items),
    so an item without a photo cannot be switched to active."""

    status_code = 422

    def __init__(self) -> None:
        super().__init__("photo_required", "add a photo before activating this item",
                         {"field": "photo"})  # fmt: skip


PHOTO_MAX_BYTES = 5 * 1024 * 1024
# File signatures, so a renamed file of another type is refused. WebP: "RIFF" ... "WEBP".
_PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def validate_photo(content_type: str, data: bytes) -> str:
    """The normalised content type of a menu photo (JPG, PNG, or WebP, max 5 MB)."""
    kind = (content_type or "").split(";")[0].strip().lower()
    if kind == "image/jpg":
        kind = "image/jpeg"
    ok = {
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": data[:4] == b"RIFF" and data[8:12] == b"WEBP",
    }.get(kind, False)
    if not ok:
        raise ValidationFailedError("only JPG, PNG, or WebP images", {"field": "photo"})
    if len(data) > PHOTO_MAX_BYTES:
        raise ValidationFailedError("the photo is larger than 5 MB", {"field": "photo"})
    return kind


def photo_object_path(tenant_id: UUID, product_id: UUID, content_type: str) -> str:
    """A new object name per upload, so a replaced photo never shows from a cache."""
    return f"{tenant_id}/{product_id}/{uuid4().hex}.{_PHOTO_TYPES[content_type]}"


async def set_photo(
    conn: AsyncConnection, ctx: ActorContext, product_id: UUID, path: str
) -> str | None:
    """Point the item at its newly uploaded photo; returns the previous object path (to remove
    after commit). Replacing a sample item's photo makes it the owner's own item."""
    cur = await conn.execute(
        "select photo_path from app.products where id = %s for update", (product_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("product")
    await conn.execute(
        "update app.products set photo_path = %s, is_sample = false where id = %s",
        (path, product_id),
    )
    await record_audit(
        conn,
        ctx,
        action="product.photo_updated",
        entity_type="product",
        entity_id=product_id,
        data={"replaced": row[0] is not None},
    )
    return row[0]


async def create_product(
    conn: AsyncConnection, ctx: ActorContext, fields: dict[str, Any], tags: list[str]
) -> UUID:
    """A new item has no photo yet, so it starts inactive (Nonaktif)."""
    if fields.get("is_active"):
        raise PhotoRequiredError
    product_id = uuid4()
    cols = ["id", "tenant_id", *fields]
    await conn.execute(
        f"insert into app.products ({', '.join(cols)})"  # noqa: S608 - whitelisted names
        f" values ({', '.join(['%s'] * len(cols))})",
        (product_id, ctx.tenant_id, *fields.values()),
    )
    await _set_tags(conn, ctx, product_id, tags)
    await record_audit(
        conn,
        ctx,
        action="product.created",
        entity_type="product",
        entity_id=product_id,
        data={"name": fields.get("name")},
    )
    return product_id


async def update_product(
    conn: AsyncConnection,
    ctx: ActorContext,
    product_id: UUID,
    fields: dict[str, Any],
    tags: list[str] | None,
) -> None:
    unknown = set(fields) - set(PRODUCT_FIELDS)
    if unknown:
        raise ValidationFailedError("fields cannot be changed", {"fields": sorted(unknown)})
    current = await get_product(conn, product_id)
    # Only switching an item on needs a photo; items that are already active without one
    # (the sample menu, FR2.12) can still be edited until the owner adds photos.
    if fields.get("is_active") and not current["is_active"] and not current["has_photo"]:
        raise PhotoRequiredError
    if fields:
        assignments = ", ".join(f"{f} = %s" for f in fields)
        await conn.execute(
            f"update app.products set {assignments}, is_sample = false where id = %s",  # noqa: S608
            (*fields.values(), product_id),
        )
    if tags is not None:
        await _set_tags(conn, ctx, product_id, tags)
    if not fields and tags is None:
        return
    await record_audit(
        conn,
        ctx,
        action="product.updated",
        entity_type="product",
        entity_id=product_id,
        data={"fields": sorted(fields), "tags": tags is not None},
    )


async def delete_product(
    conn: AsyncConnection, ctx: ActorContext, product_id: UUID
) -> tuple[str, str | None]:
    """Hard delete when never ordered; otherwise deactivate (orders keep their history).
    Returns the outcome and, for a hard delete, the photo object to remove after commit."""
    product = await get_product(conn, product_id)
    cur = await conn.execute(
        "select exists (select 1 from app.order_items where product_id = %s)", (product_id,)
    )
    used = (await cur.fetchone())[0]  # type: ignore[index]
    if used:
        await conn.execute("update app.products set is_active = false where id = %s", (product_id,))
        outcome = "deactivated"
    else:
        await conn.execute("delete from app.products where id = %s", (product_id,))
        outcome = "deleted"
    await record_audit(
        conn, ctx, action=f"product.{outcome}", entity_type="product", entity_id=product_id
    )
    return outcome, product["photo_path"] if outcome == "deleted" else None


@dataclass(frozen=True, slots=True)
class OutletPrice:
    outlet_id: UUID
    price: int | None  # None removes the price: not sold at that outlet


async def _upsert_price(
    conn: AsyncConnection,
    ctx: ActorContext,
    price: OutletPrice,
    *,
    product_id: UUID | None = None,
    option_id: UUID | None = None,
) -> None:
    column, target = ("product_id", product_id) if product_id else ("addon_option_id", option_id)
    if price.price is None:
        await conn.execute(
            f"delete from app.outlet_prices where outlet_id = %s and {column} = %s",  # noqa: S608
            (price.outlet_id, target),
        )
        return
    cur = await conn.execute(
        f"update app.outlet_prices set price = %s where outlet_id = %s and {column} = %s",  # noqa: S608
        (price.price, price.outlet_id, target),
    )
    if cur.rowcount == 0:
        try:
            async with conn.transaction():
                await conn.execute(
                    f"insert into app.outlet_prices (tenant_id, outlet_id, {column}, price)"  # noqa: S608
                    " values (%s, %s, %s, %s)",
                    (ctx.tenant_id, price.outlet_id, target, price.price),
                )
        except (errors.ForeignKeyViolation, errors.InsufficientPrivilege):
            # An outlet of another tenant fails the RLS check before the foreign key.
            raise ValidationFailedError("unknown outlet", {"field": "outlet_id"}) from None


async def set_product_prices(
    conn: AsyncConnection, ctx: ActorContext, product_id: UUID, prices: list[OutletPrice]
) -> None:
    await get_product(conn, product_id)
    for p in prices:
        await _upsert_price(conn, ctx, p, product_id=product_id)
    await record_audit(
        conn,
        ctx,
        action="product.prices_set",
        entity_type="product",
        entity_id=product_id,
        data={"prices": {str(p.outlet_id): p.price for p in prices}},
    )


# Add-on groups -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OptionInput:
    id: UUID | None
    name: str
    prices: list[OutletPrice]


async def save_addon_group(
    conn: AsyncConnection,
    ctx: ActorContext,
    *,
    product_id: UUID | None,
    group_id: UUID | None,
    name: str,
    selection: str,
    is_required: bool,
    options: list[OptionInput],
    max_select: int | None = None,
) -> UUID:
    """Create (product_id) or replace (group_id) a group with its options and prices.
    Options missing from the list are deactivated (orders may reference them)."""
    if not options:
        raise ValidationFailedError("a group needs at least one option", {"field": "options"})
    if len(options) > MAX_OPTIONS:
        raise ValidationFailedError(
            f"at most {MAX_OPTIONS} options per group", {"field": "options"}
        )
    # "maks N" only for groups with several choices, and fewer than the number of options
    # (a cap equal to the option count would mean no cap).
    if max_select is not None and (selection != "multiple" or not 2 <= max_select < len(options)):
        raise ValidationFailedError(
            "max_select needs a multiple-choice group and fewer than the number of options",
            {"field": "max_select"},
        )
    if group_id is None:
        assert product_id is not None  # noqa: S101
        await get_product(conn, product_id)
        group_id = uuid4()
        cur = await conn.execute(
            "select coalesce(max(sort_order), 0) + 1 from app.addon_groups where product_id = %s",
            (product_id,),
        )
        sort = (await cur.fetchone())[0]  # type: ignore[index]
        await conn.execute(
            "insert into app.addon_groups (id, tenant_id, product_id, name, selection, is_required,"
            " max_select, sort_order) values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                group_id,
                ctx.tenant_id,
                product_id,
                name.strip(),
                selection,
                is_required,
                max_select,
                sort,
            ),
        )
    else:
        cur = await conn.execute(
            "update app.addon_groups set name = %s, selection = %s, is_required = %s,"
            " max_select = %s where id = %s returning product_id",
            (name.strip(), selection, is_required, max_select, group_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise NotFoundError("add-on group")
        product_id = row[0]

    # Free slots first: the 10-option limit counts active options only.
    keep: list[UUID] = [o.id for o in options if o.id is not None]
    await conn.execute(
        "update app.addon_options set is_active = false where group_id = %s and not (id = any(%s))",
        (group_id, keep),
    )
    for index, opt in enumerate(options, start=1):
        if opt.id is None:
            option_id = uuid4()
            try:
                async with conn.transaction():
                    await conn.execute(
                        "insert into app.addon_options (id, tenant_id, group_id, name, sort_order)"
                        " values (%s, %s, %s, %s, %s)",
                        (option_id, ctx.tenant_id, group_id, opt.name.strip(), index),
                    )
            except errors.CheckViolation:
                raise ValidationFailedError(
                    f"at most {MAX_OPTIONS} options per group", {"field": "options"}
                ) from None
        else:
            option_id = opt.id
            cur = await conn.execute(
                "update app.addon_options set name = %s, sort_order = %s, is_active = true"
                " where id = %s and group_id = %s",
                (opt.name.strip(), index, option_id, group_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError("add-on option")
        for p in opt.prices:
            await _upsert_price(conn, ctx, p, option_id=option_id)
    await record_audit(
        conn,
        ctx,
        action="addon_group.saved",
        entity_type="addon_group",
        entity_id=group_id,
        data={"product_id": str(product_id), "options": len(options)},
    )
    return group_id


async def delete_addon_group(conn: AsyncConnection, ctx: ActorContext, group_id: UUID) -> None:
    cur = await conn.execute(
        "select exists (select 1 from app.order_item_addons a join app.addon_options o"
        " on o.id = a.addon_option_id where o.group_id = %s)",
        (group_id,),
    )
    if (await cur.fetchone())[0]:  # type: ignore[index]
        raise ConflictError("addon_group_in_use", "options of this group appear on orders")
    cur = await conn.execute("delete from app.addon_groups where id = %s", (group_id,))
    if cur.rowcount == 0:
        raise NotFoundError("add-on group")
    await record_audit(
        conn, ctx, action="addon_group.deleted", entity_type="addon_group", entity_id=group_id
    )


async def reorder_addon_groups(
    conn: AsyncConnection, ctx: ActorContext, product_id: UUID, group_ids: list[UUID]
) -> None:
    await get_product(conn, product_id)
    cur = await conn.execute("select id from app.addon_groups where product_id = %s", (product_id,))
    existing = {row[0] for row in await cur.fetchall()}
    if len(set(group_ids)) != len(group_ids) or set(group_ids) != existing:
        raise ValidationFailedError(
            "order must list every group of the product exactly once", {"field": "group_ids"}
        )
    for index, gid in enumerate(group_ids, start=1):
        await conn.execute(
            "update app.addon_groups set sort_order = %s where id = %s", (index, gid)
        )
    await record_audit(
        conn,
        ctx,
        action="addon_group.reordered",
        entity_type="product",
        entity_id=product_id,
        data={"groups": len(group_ids)},
    )


# Stock items & thresholds --------------------------------------------------------------------


async def list_stock_items(conn: AsyncConnection) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select si.id, si.name, si.unit::text as unit, si.display_unit,
               coalesce(json_agg(json_build_object('outlet_id', os.outlet_id,
                                                   'low_threshold', os.low_threshold))
                        filter (where os.outlet_id is not null), '[]') as thresholds
        from app.stock_items si
        left join app.outlet_stock os on os.stock_item_id = si.id
        where si.is_active
        group by si.id order by si.name
        """
    )
    return await cur.fetchall()


def _stock_item_check_error(exc: errors.CheckViolation) -> ValidationFailedError:
    constraint = getattr(exc.diag, "constraint_name", None) or ""
    if "name" in constraint:
        return ValidationFailedError("name must be 1-120 characters", {"field": "name"})
    return ValidationFailedError("display unit does not fit the unit", {"field": "display_unit"})


async def create_stock_item(
    conn: AsyncConnection, ctx: ActorContext, *, name: str, unit: str, display_unit: str | None
) -> UUID:
    item_id = uuid4()
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into app.stock_items (id, tenant_id, name, unit, display_unit)"
                " values (%s, %s, %s, %s, %s)",
                (item_id, ctx.tenant_id, name.strip(), unit, display_unit),
            )
    except errors.UniqueViolation:
        raise ConflictError(
            "stock_item_name_taken", "an ingredient with this name exists"
        ) from None
    except errors.CheckViolation as exc:
        raise _stock_item_check_error(exc) from None
    await record_audit(
        conn,
        ctx,
        action="stock_item.created",
        entity_type="stock_item",
        entity_id=item_id,
        data={"name": name.strip(), "unit": unit},
    )
    return item_id


async def _stock_item_usage(conn: AsyncConnection, item_id: UUID) -> dict[str, bool]:
    cur = await conn.execute(
        """
        select exists (select 1 from app.recipe_items where stock_item_id = %(i)s),
               exists (select 1 from app.stock_movements where stock_item_id = %(i)s),
               exists (select 1 from app.purchase_order_lines where stock_item_id = %(i)s)
        """,
        {"i": item_id},
    )
    row = await cur.fetchone() or (False, False, False)
    return {"recipe": row[0], "movements": row[1], "purchase_orders": row[2]}


async def update_stock_item(
    conn: AsyncConnection, ctx: ActorContext, item_id: UUID, fields: dict[str, Any]
) -> None:
    if not fields:
        return
    async with conn.transaction():
        cur = await conn.execute(
            "select unit::text from app.stock_items where id = %s and is_active for update",
            (item_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise NotFoundError("stock item")
        if "unit" in fields and fields["unit"] != row[0]:
            # A new base unit would silently change what recorded quantities mean (500 g → 500 pcs).
            if any((await _stock_item_usage(conn, item_id)).values()):
                raise ConflictError(
                    "stock_item_unit_locked",
                    "the base unit cannot change once the ingredient has stock, recipes or POs",
                )
            fields.setdefault("display_unit", None)
        assignments = ", ".join(f"{f} = %s" for f in fields)
        try:
            async with conn.transaction():
                await conn.execute(
                    f"update app.stock_items set {assignments} where id = %s",  # noqa: S608
                    (*fields.values(), item_id),
                )
        except errors.UniqueViolation:
            raise ConflictError(
                "stock_item_name_taken", "an ingredient with this name exists"
            ) from None
        except errors.CheckViolation as exc:
            raise _stock_item_check_error(exc) from None
    await record_audit(
        conn,
        ctx,
        action="stock_item.updated",
        entity_type="stock_item",
        entity_id=item_id,
        data={"fields": sorted(fields)},
    )


async def archive_stock_item(conn: AsyncConnection, ctx: ActorContext, item_id: UUID) -> None:
    """Delete = archive: hidden everywhere, history kept. Refused while a recipe still uses it."""
    async with conn.transaction():
        cur = await conn.execute(
            "select name from app.stock_items where id = %s and is_active for update", (item_id,)
        )
        row = await cur.fetchone()
        if row is None:
            raise NotFoundError("stock item")
        if (await _stock_item_usage(conn, item_id))["recipe"]:
            raise ConflictError(
                "stock_item_in_recipe",
                "this ingredient is still used in a recipe; remove it from the recipe first",
            )
        await conn.execute("update app.stock_items set is_active = false where id = %s", (item_id,))
    await record_audit(
        conn,
        ctx,
        action="stock_item.archived",
        entity_type="stock_item",
        entity_id=item_id,
        data={"name": row[0]},
    )


async def set_thresholds(
    conn: AsyncConnection, ctx: ActorContext, item_id: UUID, thresholds: dict[UUID, Decimal]
) -> None:
    try:
        for outlet_id, value in thresholds.items():
            await conn.execute(
                "select app.set_stock_threshold(%s, %s, %s)", (outlet_id, item_id, value)
            )
    except errors.NoDataFound:
        raise NotFoundError("stock item") from None
    except errors.InsufficientPrivilege:
        raise ValidationFailedError("unknown outlet", {"field": "outlet_id"}) from None
    await record_audit(
        conn,
        ctx,
        action="stock_item.thresholds_set",
        entity_type="stock_item",
        entity_id=item_id,
        data={"thresholds": {str(k): str(v) for k, v in thresholds.items()}},
    )


# Recipes ---------------------------------------------------------------------------------------


async def get_recipe(
    conn: AsyncConnection, *, product_id: UUID | None = None, option_id: UUID | None = None
) -> list[dict[str, Any]]:
    column, target = ("product_id", product_id) if product_id else ("addon_option_id", option_id)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        f"""
        select r.stock_item_id, si.name as stock_item, si.unit::text as unit, r.quantity
        from app.recipe_items r join app.stock_items si on si.id = r.stock_item_id
        where r.{column} = %s order by si.name
        """,  # noqa: S608 - column is one of two constants
        (target,),
    )
    return await cur.fetchall()


async def set_recipe(
    conn: AsyncConnection,
    ctx: ActorContext,
    lines: list[tuple[UUID, Decimal]],
    *,
    product_id: UUID | None = None,
    option_id: UUID | None = None,
) -> None:
    ids = [sid for sid, _ in lines]
    if len(set(ids)) != len(ids):
        raise ValidationFailedError("each ingredient may appear once", {"field": "stock_item_id"})
    if product_id is not None:
        await get_product(conn, product_id)
        if not lines:
            raise ValidationFailedError(
                "every menu item needs at least one ingredient", {"field": "lines"}
            )
        if any(q <= 0 for _, q in lines):
            raise ValidationFailedError("quantities must be positive", {"field": "quantity"})
        column, target, entity = "product_id", product_id, "product"
    else:
        cur = await conn.execute("select 1 from app.addon_options where id = %s", (option_id,))
        if await cur.fetchone() is None:
            raise NotFoundError("add-on option")
        if any(q == 0 for _, q in lines):
            raise ValidationFailedError("quantities must not be zero", {"field": "quantity"})
        column, target, entity = "addon_option_id", option_id, "addon_option"
    if ids:
        cur = await conn.execute(
            "select count(*) from app.stock_items where id = any(%s) and is_active", (ids,)
        )
        if (await cur.fetchone())[0] != len(ids):  # type: ignore[index]
            raise ValidationFailedError("unknown ingredient", {"field": "stock_item_id"})
    await conn.execute(f"delete from app.recipe_items where {column} = %s", (target,))  # noqa: S608
    try:
        for stock_item_id, quantity in lines:
            await conn.execute(
                f"insert into app.recipe_items (tenant_id, {column}, stock_item_id, quantity)"  # noqa: S608
                " values (%s, %s, %s, %s)",
                (ctx.tenant_id, target, stock_item_id, quantity),
            )
    except errors.ForeignKeyViolation:
        raise ValidationFailedError("unknown ingredient", {"field": "stock_item_id"}) from None
    await record_audit(
        conn,
        ctx,
        action=f"{entity}.recipe_set",
        entity_type=entity,
        entity_id=target,
        data={"lines": [[str(s), str(q)] for s, q in lines]},
    )


async def product_availability(conn: AsyncConnection, product_id: UUID) -> list[dict[str, Any]]:
    """O6 "Simulasi ketersediaan per outlet (1 porsi Regular)"."""
    await get_product(conn, product_id)
    recipes = await stock_core.load_recipes(conn)
    recipe = recipes.products.get(product_id, {})
    names = await _stock_item_names(conn)
    cur = await conn.execute("select id, name from app.outlets where is_active order by created_at")
    out = []
    for outlet_id, outlet_name in await cur.fetchall():
        stock = await stock_core.on_hand(conn, outlet_id)
        avail = stock_core.product_availability(recipe, stock)
        limiting = avail.limiting_stock_item_id
        out.append(
            {
                "outlet_id": outlet_id,
                "outlet_name": outlet_name,
                "portions_available": avail.portions,
                "sold_out": avail.sold_out,
                "limiting_stock_item": names[limiting][0] if avail.sold_out and limiting else None,
            }
        )
    return out


# Counter menu (S1) -----------------------------------------------------------------------------


async def counter_menu(
    conn: AsyncConnection,
    outlet_id: UUID,
    *,
    q: str | None = None,
    category: str | None = None,
    owner_picks: bool = False,
) -> list[dict[str, Any]]:
    """Active products priced at the outlet, with sold-out state and add-on availability."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select p.id as product_id, p.name, p.category, p.description, p.is_owner_pick, op.price,
               p.photo_path
        from app.products p
        join app.outlet_prices op on op.product_id = p.id and op.outlet_id = %s and op.is_available
        where p.is_active
        order by p.is_owner_pick desc, coalesce(p.owner_pick_rank, 999), p.category nulls last,
                 p.name
        """,
        (outlet_id,),
    )
    products = await cur.fetchall()
    recipes = await stock_core.load_recipes(conn)
    stock = await stock_core.on_hand(conn, outlet_id)
    await cur.execute(
        """
        select g.id, g.product_id, g.name, g.selection::text as selection, g.is_required,
               g.max_select, o.id as option_id, o.name as option_name, op.price
        from app.addon_groups g
        join app.addon_options o on o.group_id = g.id and o.is_active
        join app.outlet_prices op on op.addon_option_id = o.id and op.outlet_id = %s
        order by g.sort_order, g.created_at, o.sort_order, o.created_at
        """,
        (outlet_id,),
    )
    groups: dict[UUID, dict[UUID, dict[str, Any]]] = defaultdict(dict)
    for r in await cur.fetchall():
        product_groups = groups[r["product_id"]]
        group = product_groups.setdefault(
            r["id"],
            {
                "id": r["id"],
                "name": r["name"],
                "selection": r["selection"],
                "is_required": r["is_required"],
                "max_select": r["max_select"],
                "options": [],
            },
        )
        base = recipes.products.get(r["product_id"], {})
        group["options"].append(
            {
                "id": r["option_id"],
                "name": r["option_name"],
                "price": r["price"],
                "available": stock_core.option_available(
                    base, recipes.options.get(r["option_id"], {}), stock
                ),
            }
        )
    needle = (q or "").strip().lower()
    out = []
    for p in products:
        if needle and needle not in p["name"].lower():
            continue
        if category and p["category"] != category:
            continue
        if owner_picks and not p["is_owner_pick"]:
            continue
        sold_out = stock_core.product_availability(
            recipes.products.get(p["product_id"], {}), stock
        ).sold_out
        out.append(
            {
                **p,
                "sold_out": sold_out,
                "sold_out_reason": "Bahan tidak cukup" if sold_out else None,
                "addon_groups": list(groups.get(p["product_id"], {}).values()),
            }
        )
    return out


async def tables_with_bills(conn: AsyncConnection, outlet_id: UUID) -> list[dict[str, Any]]:
    """S1 table dropdown: "Meja 05 · Indoor — open bill aktif (Rp 64.000)"."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select t.id, t.name, t.area, b.id as bill_id,
               (select coalesce(sum(o.subtotal), 0) from app.orders o
                where o.bill_id = b.id and o.status <> 'cancelled') as bill_subtotal
        from app.tables t
        left join app.bills b on b.table_id = t.id and b.status = 'open'
        where t.outlet_id = %s and t.is_active order by t.name
        """,
        (outlet_id,),
    )
    return await cur.fetchall()
