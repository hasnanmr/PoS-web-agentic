"""Owner dashboard queries — O2 Dashboard tab Ringkasan + keramaian (T-071, T-123).

Contract: docs/architecture/screen-endpoint-map.md → O2.

Periods are outlet-local (glossary §3): "today" at a WIB outlet and at a WITA outlet are each
outlet's own calendar day, week, month, or year, so an all-outlets figure sums those periods.

What counts:
- Money (revenue, PB1, delivery fee, payment-method amounts) comes from the ledger, like O9,
  by outlet-local ``business_date``; refunds of reversed orders are subtracted.
- Order counts (orders, cash/QRIS split, delivery orders, channel mix, orders per hour, the
  busyness map) count paid orders (``payment_status = paid``, not cancelled), like "Item
  terlaris", by the outlet-local time the order was created.
- Busy and quiet hours (T-123): an hour of the day is busy when its orders are at least 130%
  of the average per opening hour in the period, quiet when at most 60%. The header filter
  ``hours=busy|quiet`` keeps only those hours (orders by creation hour, money by the hour the
  ledger entry was posted).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.reports import change_pct, previous_period
from app.core.stock import stock_status

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


# --- O2 tab Ringkasan: GET /owner/dashboard ------------------------------------------------

DashboardPeriod = Literal["today", "week", "month"]
HoursFilter = Literal["all", "busy", "quiet"]
CrowdLevel = Literal["ramai", "normal", "sepi"]

# T-123 thresholds. The wireframe calls them placeholders (WIREFRAME-TRACEABILITY open points);
# change them here only.
BUSY_PCT = 130  # an hour is busy at >= 130% of the average orders per opening hour
QUIET_PCT = 60  # and quiet at <= 60%
CROWD_RAMAI_PCT = 75  # current crowd: tables occupied >= 75% → Ramai
CROWD_SEPI_PCT = 30  # <= 30% → Sepi; in between → Normal
MAP_WEEKS = 4  # busyness map: average over the last 4 complete weeks
# Orders still in progress that make an outlet crowded now. Older ones are left out so an order
# nobody closed does not keep an outlet "Ramai" for days.
ACTIVE_STATUSES = ("confirmed", "preparing", "ready", "out_for_delivery")
ACTIVE_WINDOW = timedelta(hours=12)


def period_range(today: date, period: DashboardPeriod) -> tuple[date, date]:
    """Today, this week (from Monday), or this month, up to and including today."""
    if period == "week":
        return today - timedelta(days=today.weekday()), today
    if period == "month":
        return today.replace(day=1), today
    return today, today


def previous_range(today: date, period: DashboardPeriod) -> tuple[date, date]:
    """What the revenue tile compares with: yesterday, the same days of last week, or the
    same days of last month ("▲ 8% vs kemarin")."""
    if period == "week":
        start, end = period_range(today, period)
        return start - timedelta(days=7), end - timedelta(days=7)
    if period == "month":
        return previous_period(*period_range(today, period))
    return today - timedelta(days=1), today - timedelta(days=1)


def open_hours(rows: Iterable[Mapping[str, Any]]) -> dict[int, set[int]]:
    """ISO weekday → local hours (0..23) the outlet is open for at least part of the hour.
    An outlet that closes after midnight (``closes_at <= opens_at``) has the hours after
    midnight on the next weekday."""
    out: dict[int, set[int]] = defaultdict(set)
    for r in rows:
        opens = r["opens_at"].hour * 60 + r["opens_at"].minute
        closes = r["closes_at"].hour * 60 + r["closes_at"].minute
        day = int(r["weekday"])
        if closes > opens:
            out[day].update(h for h in range(24) if h * 60 < closes and (h + 1) * 60 > opens)
        else:
            out[day].update(h for h in range(24) if (h + 1) * 60 > opens)
            out[day % 7 + 1].update(h for h in range(24) if h * 60 < closes)
    return out


def mark_hours(counts: Mapping[int, int], hours: Iterable[int]) -> list[dict[str, Any]]:
    """Orders per hour with busy/quiet marks against the average over the shown hours."""
    shown = sorted(set(hours))
    total = sum(counts.get(h, 0) for h in shown)
    out = []
    for h in shown:
        n = counts.get(h, 0)
        mark = None
        if total:
            # n >= BUSY_PCT% of (total / len(shown)), in integers.
            if n * 100 * len(shown) >= BUSY_PCT * total:
                mark = "busy"
            elif n * 100 * len(shown) <= QUIET_PCT * total:
                mark = "quiet"
        out.append({"hour": h, "orders": n, "mark": mark})
    return out


def hour_summary(series: list[dict[str, Any]], mark: str) -> dict[str, Any]:
    total = sum(s["orders"] for s in series)
    picked = [s for s in series if s["mark"] == mark]
    orders = sum(s["orders"] for s in picked)
    return {
        "hours": [s["hour"] for s in picked],
        "orders": orders,
        "share_pct": round(orders * 100 / total) if total else 0,
    }


def crowd_level(occupied: int, total_tables: int, active: int, usual: float) -> CrowdLevel:
    """Ramai / Normal / Sepi now. With tables: by the share of tables occupied. Without tables
    (takeaway-only outlet): active orders against the usual orders for this weekday and hour
    (the busyness-map average), with the busy/quiet thresholds."""
    if total_tables:
        pct = occupied * 100 / total_tables
        if pct >= CROWD_RAMAI_PCT:
            return "ramai"
        return "sepi" if pct <= CROWD_SEPI_PCT else "normal"
    if usual <= 0:
        return "normal" if active else "sepi"
    if active * 100 >= BUSY_PCT * usual:
        return "ramai"
    return "sepi" if active * 100 <= QUIET_PCT * usual else "normal"


_RANGES = (
    "unnest(%(ids)s::uuid[], %(froms)s::date[], %(tos)s::date[]) as r(outlet_id, d_from, d_to)"
)
_PAID = "o.payment_status = 'paid' and o.status <> 'cancelled'"
_LOCAL_DATE = "(o.created_at at time zone ol.timezone)::date"
_LOCAL_HOUR = "extract(hour from o.created_at at time zone ol.timezone)::int"
_LEDGER_HOUR = "extract(hour from l.created_at at time zone ol.timezone)::int"
_PAYMENT_HOUR = "extract(hour from p.confirmed_at at time zone ol.timezone)::int"


def _range_params(outlets: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return {
        "ids": [o["id"] for o in outlets],
        "froms": [o[key][0] for o in outlets],
        "tos": [o[key][1] for o in outlets],
    }


async def _load_outlets(conn: AsyncConnection, outlet_id: UUID | None) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, name, timezone from app.outlets"
        " where is_active and (%(o)s::uuid is null or id = %(o)s) order by created_at",
        {"o": outlet_id},
    )
    outlets = await cur.fetchall()
    await cur.execute(
        "select outlet_id, weekday, opens_at, closes_at from app.outlet_opening_hours"
        " where outlet_id = any(%s)",
        ([o["id"] for o in outlets],),
    )
    hours: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for r in await cur.fetchall():
        hours[r["outlet_id"]].append(r)
    for o in outlets:
        o["open"] = open_hours(hours[o["id"]])
    return outlets


def _hours_in(outlets: list[dict[str, Any]], key: str) -> set[int]:
    """Every hour any selected outlet is open on any day of its range."""
    out: set[int] = set()
    for o in outlets:
        day, end = o[key]
        while day <= end:
            out |= o["open"].get(day.isoweekday(), set())
            day += timedelta(days=1)
    return out


async def _orders_per_hour(
    conn: AsyncConnection, outlets: list[dict[str, Any]], key: str
) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        f"""
        select {_LOCAL_HOUR} as hour, count(*)::int as orders
        from app.orders o
        join app.outlets ol on ol.id = o.outlet_id
        join {_RANGES} on r.outlet_id = o.outlet_id
        where {_PAID} and {_LOCAL_DATE} between r.d_from and r.d_to
        group by 1
        """,  # noqa: S608 - constant SQL fragments only
        _range_params(outlets, key),
    )
    counts = {r["hour"]: r["orders"] for r in await cur.fetchall()}
    hours = _hours_in(outlets, key)
    if not hours:  # no opening hours set: show the hours that had orders
        hours = set(counts)
    return mark_hours(counts, hours)


async def _figures(
    conn: AsyncConnection, outlets: list[dict[str, Any]], key: str, hours: list[int] | None
) -> dict[str, Any]:
    """KPI sums, channel mix, and payment methods for one range and hour filter."""
    params = {**_range_params(outlets, key), "hours": hours}
    hour_filter = "(%(hours)s::int[] is null or {expr} = any(%(hours)s::int[]))"
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        f"""
        select coalesce(rv.type, l.type)::text as category, l.payment_method::text as method,
               sum(l.amount)::bigint as amount, sum(l.pb1_portion)::bigint as pb1_portion
        from app.ledger_entries l
        join app.outlets ol on ol.id = l.outlet_id
        join {_RANGES} on r.outlet_id = l.outlet_id
        left join app.ledger_entries rv on rv.id = l.reverses_entry_id
        where l.business_date between r.d_from and r.d_to
          and {hour_filter.format(expr=_LEDGER_HOUR)}
        group by 1, 2
        """,  # noqa: S608 - constant SQL fragments only
        params,
    )
    k: dict[str, int] = defaultdict(int)
    method_amount: dict[str, int] = defaultdict(int)
    for r in await cur.fetchall():
        amount, method = int(r["amount"]), r["method"]
        if r["category"] in ("revenue", "pb1", "delivery_fee"):
            k[r["category"]] += amount
        elif r["category"] == "refund":
            # A refund row is revenue + PB1 given back (negative); pb1_portion is the PB1 part.
            k["pb1"] -= int(r["pb1_portion"])
            k["revenue"] += amount + int(r["pb1_portion"])
        else:
            continue
        if method in ("cash", "qris"):
            method_amount[method] += amount
    await cur.execute(
        f"""
        select o.channel::text as channel, o.type::text as type,
               coalesce(p.method, bp.method)::text as method, count(*)::int as orders
        from app.orders o
        join app.outlets ol on ol.id = o.outlet_id
        join {_RANGES} on r.outlet_id = o.outlet_id
        left join app.payments p on p.order_id = o.id
        left join app.payments bp on bp.bill_id = o.bill_id
        where {_PAID} and {_LOCAL_DATE} between r.d_from and r.d_to
          and {hour_filter.format(expr=_LOCAL_HOUR)}
        group by 1, 2, 3
        """,  # noqa: S608 - constant SQL fragments only
        params,
    )
    channels: dict[str, int] = defaultdict(int)
    for r in await cur.fetchall():
        n = r["orders"]
        k["orders"] += n
        channels[r["channel"]] += n
        if r["method"] in ("cash", "qris"):
            k[f"{r['method']}_count"] += n
        if r["type"] == "delivery":
            k["delivery_orders"] += n
    await cur.execute(
        f"""
        select p.method::text as method, count(*)::int as transactions
        from app.payments p
        join app.outlets ol on ol.id = p.outlet_id
        join {_RANGES} on r.outlet_id = p.outlet_id
        where p.method in ('cash', 'qris')
          and (p.confirmed_at at time zone ol.timezone)::date between r.d_from and r.d_to
          and {hour_filter.format(expr=_PAYMENT_HOUR)}
        group by 1
        """,  # noqa: S608 - constant SQL fragments only
        params,
    )
    transactions = {r["method"]: r["transactions"] for r in await cur.fetchall()}
    total = k["orders"]
    return {
        "kpis": k,
        "channel_mix": [
            {
                "channel": c,
                "orders": channels[c],
                "share_pct": round(channels[c] * 100 / total) if total else 0,
            }
            for c in ("whatsapp_online", "whatsapp_table", "counter")
        ],
        "payment_methods": [
            {"method": m, "amount": method_amount[m], "transactions": transactions.get(m, 0)}
            for m in ("cash", "qris")
        ],
    }


async def _busyness_map(
    conn: AsyncConnection, outlets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Average paid orders per weekday and local hour over the last 4 complete weeks, in
    opening hours (summed across the selected outlets)."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        f"""
        select extract(isodow from o.created_at at time zone ol.timezone)::int as weekday,
               {_LOCAL_HOUR} as hour, count(*)::int as orders
        from app.orders o
        join app.outlets ol on ol.id = o.outlet_id
        join {_RANGES} on r.outlet_id = o.outlet_id
        where {_PAID} and {_LOCAL_DATE} between r.d_from and r.d_to
        group by 1, 2
        """,  # noqa: S608 - constant SQL fragments only
        _range_params(outlets, "map_range"),
    )
    counts = {(r["weekday"], r["hour"]): r["orders"] for r in await cur.fetchall()}
    cells: set[tuple[int, int]] = set()
    for o in outlets:
        for day, hours in o["open"].items():
            cells |= {(day, h) for h in hours}
    if not cells:
        cells = set(counts)
    return [
        {"weekday": d, "hour": h, "avg_orders": round(counts.get((d, h), 0) / MAP_WEEKS, 1)}
        for d, h in sorted(cells)
    ]


async def _current_crowd(
    conn: AsyncConnection, outlets: list[dict[str, Any]], now: datetime
) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select ol.id as outlet_id,
          (select count(*) from app.tables t where t.outlet_id = ol.id and t.is_active)::int
            as total_tables,
          (select count(distinct t.id) from app.tables t
           where t.outlet_id = ol.id and t.is_active and (
             exists (select 1 from app.reservations rs
                     where rs.table_id = t.id and rs.status = 'seated')
             or exists (select 1 from app.bills b where b.table_id = t.id and b.status = 'open')
             or exists (select 1 from app.orders o where o.table_id = t.id
                        and o.status = any(%(active)s::app.order_status[])
                        and o.created_at > %(since)s)))::int as occupied_tables,
          (select count(*) from app.orders o where o.outlet_id = ol.id
             and o.status = any(%(active)s::app.order_status[])
             and o.created_at > %(since)s)::int as active_orders
        from app.outlets ol where ol.id = any(%(ids)s)
        """,
        {
            "ids": [o["id"] for o in outlets],
            "active": list(ACTIVE_STATUSES),
            "since": now - ACTIVE_WINDOW,
        },
    )
    live = {r["outlet_id"]: r for r in await cur.fetchall()}
    # The usual orders for this weekday and hour, for outlets without tables.
    await cur.execute(
        f"""
        select o.outlet_id, count(*)::int as orders
        from app.orders o
        join app.outlets ol on ol.id = o.outlet_id
        join {_RANGES} on r.outlet_id = o.outlet_id
        where {_PAID} and {_LOCAL_DATE} between r.d_from and r.d_to
          and extract(isodow from o.created_at at time zone ol.timezone)
              = extract(isodow from %(now)s at time zone ol.timezone)
          and {_LOCAL_HOUR} = extract(hour from %(now)s at time zone ol.timezone)
        group by 1
        """,  # noqa: S608 - constant SQL fragments only
        {**_range_params(outlets, "map_range"), "now": now},
    )
    usual = {r["outlet_id"]: r["orders"] / MAP_WEEKS for r in await cur.fetchall()}
    out = []
    for o in outlets:
        r = live[o["id"]]
        out.append(
            {
                "outlet_id": o["id"],
                "name": o["name"],
                "timezone": o["timezone"],
                "occupied_tables": r["occupied_tables"],
                "total_tables": r["total_tables"],
                "active_orders": r["active_orders"],
                "level": crowd_level(
                    r["occupied_tables"],
                    r["total_tables"],
                    r["active_orders"],
                    usual.get(o["id"], 0.0),
                ),
            }
        )
    return out


async def _low_stock(conn: AsyncConnection, outlets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Active stock items that are out or at/below their low threshold, per outlet; sold out
    first."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select si.name as stock_item, ol.id as outlet_id, ol.name as outlet,
               coalesce(os.on_hand, 0) as on_hand, coalesce(os.low_threshold, 0) as low_threshold,
               si.unit::text as unit, si.display_unit
        from app.stock_items si
        cross join app.outlets ol
        left join app.outlet_stock os on os.stock_item_id = si.id and os.outlet_id = ol.id
        where si.is_active and ol.id = any(%s)
        order by si.name, ol.created_at
        """,
        ([o["id"] for o in outlets],),
    )
    rows = []
    for r in await cur.fetchall():
        status = stock_status(r["on_hand"], r["low_threshold"])
        if status != "ok":
            rows.append({**r, "status": status})
    rows.sort(key=lambda r: r["status"] != "out")  # stable: sold out first, then by name
    return rows


async def summary(
    conn: AsyncConnection,
    *,
    outlet_id: UUID | None,
    period: DashboardPeriod,
    hours: HoursFilter,
    now: datetime | None = None,
) -> dict[str, Any]:
    """O2 tab Ringkasan: every card except "Item terlaris" (its own endpoint)."""
    now = now or datetime.now(UTC)
    outlets = await _load_outlets(conn, outlet_id)
    if not outlets:
        return _empty_summary(period, hours, now)
    for o in outlets:
        today = now.astimezone(ZoneInfo(o["timezone"])).date()
        o["range"] = period_range(today, period)
        o["prev_range"] = previous_range(today, period)
        o["map_range"] = (today - timedelta(weeks=MAP_WEEKS), today - timedelta(days=1))

    series = await _orders_per_hour(conn, outlets, "range")
    hour_set = None if hours == "all" else [s["hour"] for s in series if s["mark"] == hours]
    cur = await _figures(conn, outlets, "range", hour_set)
    prev = await _figures(conn, outlets, "prev_range", hour_set)
    k, pk = cur["kpis"], prev["kpis"]
    return {
        "period": period,
        "hours": hours,
        "as_of": now,
        "kpis": {
            "revenue_excl_pb1": k["revenue"],
            "change_pct": change_pct(k["revenue"], pk["revenue"]),
            "orders": k["orders"],
            "cash_count": k["cash_count"],
            "qris_count": k["qris_count"],
            "pb1_collected": k["pb1"],
            "delivery_fee": k["delivery_fee"],
            "delivery_orders": k["delivery_orders"],
        },
        "busyness_map": await _busyness_map(conn, outlets),
        "current_crowd": await _current_crowd(conn, outlets, now),
        "orders_per_hour": series,
        "busy_summary": hour_summary(series, "busy"),
        "quiet_summary": hour_summary(series, "quiet"),
        "low_stock": await _low_stock(conn, outlets),
        "channel_mix": cur["channel_mix"],
        "payment_methods": cur["payment_methods"],
    }


def _empty_summary(period: str, hours: str, now: datetime) -> dict[str, Any]:
    none = {"hours": [], "orders": 0, "share_pct": 0}
    return {
        "period": period,
        "hours": hours,
        "as_of": now,
        "kpis": {
            "revenue_excl_pb1": 0,
            "change_pct": None,
            "orders": 0,
            "cash_count": 0,
            "qris_count": 0,
            "pb1_collected": 0,
            "delivery_fee": 0,
            "delivery_orders": 0,
        },
        "busyness_map": [],
        "current_crowd": [],
        "orders_per_hour": [],
        "busy_summary": none,
        "quiet_summary": dict(none),
        "low_stock": [],
        "channel_mix": [
            {"channel": c, "orders": 0, "share_pct": 0}
            for c in ("whatsapp_online", "whatsapp_table", "counter")
        ],
        "payment_methods": [
            {"method": m, "amount": 0, "transactions": 0} for m in ("cash", "qris")
        ],
    }
