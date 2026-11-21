"""Rekomendasi — owner's picks, tags, and the per-outlet menu preview (O7, T-073).

`recommendation_list` is the one function behind both the O7 preview and (later) the
WhatsApp Rekomendasi flow (W9), so the owner sees exactly what a customer will get:
owner's picks first (in the owner's order), then the outlet's best sellers of the last
30 days, sold-out items left out, no item twice, at most 30 items (FR8.1, FR8.2).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core import catalog
from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ValidationFailedError

MAX_ITEMS = 30  # one WhatsApp product message
BEST_SELLER_DAYS = 30
MAX_PICKS = 30

# Paid orders only (same rule as the dashboard's "Item terlaris"): unpaid orders are not
# sales yet and a cancelled or reversed order never counts.
_BEST_SELLERS_SQL = """
select oi.product_id, sum(oi.quantity)::int as units
from app.order_items oi
join app.orders o on o.id = oi.order_id and o.outlet_id = oi.outlet_id
where oi.outlet_id = %s
  and o.payment_status = 'paid'
  and o.status <> 'cancelled'
  and o.created_at >= now() - make_interval(days => %s)
group by oi.product_id
order by units desc, oi.product_id
"""


async def list_picks(conn: AsyncConnection) -> list[dict[str, Any]]:
    """Owner's picks in the owner's order, with tags (tenant-wide, FR8.1)."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select p.id as product_id, p.name, p.category, p.is_active,
               coalesce(array_agg(t.tag order by t.tag) filter (where t.tag is not null),
                        '{}') as tags
        from app.products p
        left join app.product_tags t on t.product_id = p.id
        where p.is_owner_pick
        group by p.id
        order by p.owner_pick_rank nulls last, p.name
        """
    )
    return await cur.fetchall()


async def set_picks(conn: AsyncConnection, ctx: ActorContext, product_ids: list[UUID]) -> None:
    """Replace the whole list: the given products become picks in this order, every other
    product stops being one. Drag-to-reorder, ✕ and "+ Tambah owner's pick" all save this."""
    if len(set(product_ids)) != len(product_ids):
        raise ValidationFailedError("a product can be a pick only once", {"field": "product_ids"})
    if len(product_ids) > MAX_PICKS:
        raise ValidationFailedError(
            f"at most {MAX_PICKS} owner's picks", {"field": "product_ids", "max": MAX_PICKS}
        )
    if product_ids:
        cur = await conn.execute(
            "select count(*) from app.products where id = any(%s)", (list(product_ids),)
        )
        row = await cur.fetchone()
        if row is None or row[0] != len(product_ids):
            raise ValidationFailedError("unknown product", {"field": "product_ids"})
    before = [p["product_id"] for p in await list_picks(conn)]
    await conn.execute(
        """
        update app.products p
        set is_owner_pick = r.rank is not null, owner_pick_rank = r.rank, updated_at = now()
        from (
          select p2.id, x.rank
          from app.products p2
          left join unnest(%s::uuid[]) with ordinality as x(id, rank) on x.id = p2.id
        ) r
        where p.id = r.id
          and (p.is_owner_pick, p.owner_pick_rank) is distinct from (r.rank is not null, r.rank)
        """,
        (list(product_ids),),
    )
    if before != product_ids:
        await record_audit(
            conn,
            ctx,
            action="owner_picks.updated",
            entity_type="owner_picks",
            data={"count": len(product_ids)},
        )


async def list_tags(conn: AsyncConnection) -> list[str]:
    cur = await conn.execute("select distinct tag from app.product_tags order by tag")
    return [r[0] for r in await cur.fetchall()]


async def recommendation_list(
    conn: AsyncConnection, outlet_id: UUID, menu_rows: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """What the Rekomendasi menu of this outlet shows, and what was left out and why.

    Each entry is `{product_id, name, position, skipped_reason}`; `position` is the place in
    the customer's list (1-based, picks and best sellers continue the same count) and is
    None for a skipped entry. `menu_rows` is the outlet's `counter_menu`, when the caller has
    already loaded it. Items the outlet does not offer at all (inactive, no price
    here) are not shown, except a pick, which the owner chose on purpose: it is listed as
    skipped `unavailable`.
    """
    if menu_rows is None:
        menu_rows = await catalog.counter_menu(conn, outlet_id)
    menu = {m["product_id"]: m for m in menu_rows}
    picks = await list_picks(conn)

    listed: set[UUID] = set()
    out_picks: list[dict[str, Any]] = []
    out_sellers: list[dict[str, Any]] = []

    def take(product_id: UUID, name: str) -> dict[str, Any]:
        item = menu.get(product_id)
        entry: dict[str, Any] = {
            "product_id": product_id,
            "name": name,
            "position": None,
            "skipped_reason": None,
        }
        if item is None:
            entry["skipped_reason"] = "unavailable"
        elif item["sold_out"]:
            entry["skipped_reason"] = "sold_out"
        elif product_id in listed:
            entry["skipped_reason"] = "duplicate"
        else:
            listed.add(product_id)
            entry["position"] = len(listed)
        return entry

    for p in picks:
        out_picks.append(take(p["product_id"], p["name"]))

    cur = await conn.execute(_BEST_SELLERS_SQL, (outlet_id, BEST_SELLER_DAYS))
    for product_id, units in await cur.fetchall():
        item = menu.get(product_id)
        if item is None:
            continue  # not offered at this outlet (inactive or no price): nothing to show
        if len(listed) >= MAX_ITEMS:
            break  # the list is full (at most MAX_PICKS picks, so picks alone never overflow)
        out_sellers.append({**take(product_id, item["name"]), "units_30d": units})
    return {"picks": out_picks, "best_sellers": out_sellers, "listed_count": len(listed)}
