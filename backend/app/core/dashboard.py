"""Owner dashboard queries — O2 Dashboard + keramaian (T-071).

Only the "Item terlaris" card is built so far. Contract: docs/architecture/screen-endpoint-map.md
→ O2.

Periods are outlet-local (glossary §3): "today" at a WIB outlet and at a WITA outlet are each
outlet's own calendar day, month, or year, so an all-outlets figure sums those periods.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

TopItemsPeriod = Literal["day", "month", "year"]
TOP_ITEMS_LIMIT = 5

# Paid orders only: unpaid and proof-submitted orders are not sales yet, a cancelled order
# never counts, and a reversed paid order becomes `refunded` (glossary §5), so it drops out.
# Add-on variants are grouped under their menu item; `line_total` already includes add-ons
# and excludes PB1 and the delivery fee.
_TOP_ITEMS_SQL = """
select p.name, sum(oi.quantity)::int as quantity_sold, sum(oi.line_total)::bigint as revenue
from app.order_items oi
join app.orders o on o.id = oi.order_id and o.outlet_id = oi.outlet_id
join app.outlets ol on ol.id = o.outlet_id
join app.products p on p.id = oi.product_id
where o.payment_status = 'paid'
  and o.status <> 'cancelled'
  and (%(outlet_id)s::uuid is null or o.outlet_id = %(outlet_id)s::uuid)
  and o.created_at >= (
    date_trunc(%(unit)s, now() at time zone ol.timezone) at time zone ol.timezone
  )
group by oi.product_id, p.name
order by quantity_sold desc, revenue desc, p.name
limit %(limit)s
"""


async def top_items(
    conn: AsyncConnection, *, outlet_id: UUID | None, period: TopItemsPeriod
) -> list[dict[str, Any]]:
    """Top 5 menu items by quantity sold since the start of the outlet-local day, month, or
    year; ties go to the higher revenue. RLS limits the rows to the caller's tenant."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        _TOP_ITEMS_SQL, {"outlet_id": outlet_id, "unit": period, "limit": TOP_ITEMS_LIMIT}
    )
    return await cur.fetchall()
