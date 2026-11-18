"""Owner reports from the ledger (T-043) and closed shifts (T-040, T-102) — O9, O10.

Day boundaries are the outlet's: ledger rows carry an outlet-local `business_date`, and
shifts are grouped by the outlet-local date they opened, so "1 Nov" at a WIB outlet and at a
WITA outlet are both 1 Nov (glossary §3). Cross-outlet figures are sums of those days.

O9 figures, all from `app.ledger_entries` (signed amounts):

- cash_in  = revenue + PB1 + delivery fee (split by payment method: cash / QRIS)
- cash_out = refunds + expenses (an expense reversal reduces expenses)
- cash_difference = cash surplus + cash shortage (signed)
- net = cash_in - cash_out + cash_difference
- pb1_collected = PB1 - PB1 given back in refunds (`pb1_portion`)
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.errors import ValidationFailedError

Granularity = Literal["daily", "weekly", "monthly"]
MAX_RANGE_DAYS = 366


def validate_range(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise ValidationFailedError("the start date is after the end date", {"field": "from"})
    if (date_to - date_from).days >= MAX_RANGE_DAYS:
        raise ValidationFailedError("choose at most one year", {"field": "to"})


def default_range(today: date) -> tuple[date, date]:
    """Month to date, as O9 opens ("1-17 Nov 2026")."""
    return today.replace(day=1), today


def _minus_month(day: date, months: int = 1) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def previous_period(date_from: date, date_to: date) -> tuple[date, date]:
    """The period O9 compares against ("▲ 12% vs 1-17 Okt"). A range that starts on the 1st
    is compared with the same days of the previous month(s); any other range with the same
    number of days immediately before it."""
    if date_from.day == 1:
        months = (date_to.year - date_from.year) * 12 + date_to.month - date_from.month + 1
        prev_from = _minus_month(date_from, months)
        prev_to = _minus_month(date_to, months)
        if date_to.day == calendar.monthrange(date_to.year, date_to.month)[1]:
            # A full month compares with the full previous month (31 Okt, 30 Nov, 28 Feb).
            prev_to = prev_to.replace(day=calendar.monthrange(prev_to.year, prev_to.month)[1])
        return prev_from, prev_to
    days = (date_to - date_from).days + 1
    return date_from - timedelta(days=days), date_from - timedelta(days=1)


def change_pct(current: int, previous: int) -> int | None:
    """Whole percent change; None when there is nothing to compare with."""
    if previous == 0:
        return None
    return round((current - previous) * 100 / abs(previous))


def bucket(day: date, granularity: Granularity) -> date:
    if granularity == "weekly":
        return day - timedelta(days=day.weekday())  # Monday
    if granularity == "monthly":
        return day.replace(day=1)
    return day


_SUMS = """
select l.business_date, l.outlet_id,
       l.type::text as type, l.payment_method::text as method,
       r.type::text as reversed_type,
       sum(l.amount) as amount, sum(l.pb1_portion) as pb1_portion, count(*) as entries
from app.ledger_entries l
left join app.ledger_entries r on r.id = l.reverses_entry_id
where l.business_date between %(from)s and %(to)s
  and (%(outlet)s::uuid is null or l.outlet_id = %(outlet)s)
group by 1, 2, 3, 4, 5
"""


async def _ledger_rows(
    conn: AsyncConnection, outlet_id: UUID | None, date_from: date, date_to: date
) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(_SUMS, {"from": date_from, "to": date_to, "outlet": outlet_id})
    return await cur.fetchall()


def _category(row: dict[str, Any]) -> str:
    """Reversal rows count against what they reverse (an expense reversal lowers expenses)."""
    return row["reversed_type"] if row["type"] == "reversal" else row["type"]


def _totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    t: dict[str, int] = defaultdict(int)
    for r in rows:
        amount = int(r["amount"])
        category = _category(r)
        if category in ("revenue", "pb1", "delivery_fee"):
            t[category] += amount
            t["cash_in"] += amount
            t[r["method"] or "cash"] += amount
        elif category == "refund":
            t["refunds"] -= amount
            t["pb1_refunded"] += int(r["pb1_portion"])
        elif category == "expense":
            t["expenses"] -= amount
        elif category in ("cash_shortage", "cash_surplus"):
            t["cash_difference"] += amount
    t["cash_out"] = t["refunds"] + t["expenses"]
    t["net"] = t["cash_in"] - t["cash_out"] + t["cash_difference"]
    t["pb1_collected"] = t["pb1"] - t["pb1_refunded"]
    return t


def _series(
    rows: list[dict[str, Any]], date_from: date, date_to: date, granularity: Granularity
) -> list[dict[str, Any]]:
    by_bucket: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_bucket[bucket(r["business_date"], granularity)].append(r)
    out = []
    day = bucket(date_from, granularity)
    seen: set[date] = set()
    while day <= date_to:
        b = bucket(day, granularity)
        if b not in seen:
            seen.add(b)
            t = _totals(by_bucket.get(b, []))
            out.append({"date": b, "cash_in": t["cash_in"], "cash_out": t["cash_out"]})
        day += timedelta(days=1)
    return out


async def cashflow(
    conn: AsyncConnection,
    *,
    outlet_id: UUID | None,
    date_from: date,
    date_to: date,
    granularity: Granularity,
) -> dict[str, Any]:
    """O9 "Laporan Cashflow": KPI tiles vs the previous period, chart series, breakdown, and
    expenses per outlet."""
    validate_range(date_from, date_to)
    prev_from, prev_to = previous_period(date_from, date_to)
    rows = await _ledger_rows(conn, outlet_id, date_from, date_to)
    prev = _totals(await _ledger_rows(conn, outlet_id, prev_from, prev_to))
    cur = _totals(rows)

    def tile(key: str) -> dict[str, Any]:
        return {"amount": cur[key], "change_pct": change_pct(cur[key], prev[key])}

    names = conn.cursor(row_factory=dict_row)
    await names.execute(
        "select id, name from app.outlets where %s::uuid is null or id = %s order by created_at",
        (outlet_id, outlet_id),
    )
    outlets = await names.fetchall()
    expenses: dict[UUID, dict[str, int]] = defaultdict(lambda: {"amount": 0, "count": 0})
    for r in rows:
        if _category(r) != "expense":
            continue
        e = expenses[r["outlet_id"]]
        e["amount"] -= int(r["amount"])
        # A reversed expense no longer counts as an entry.
        e["count"] += int(r["entries"]) if r["type"] == "expense" else -int(r["entries"])
    by_outlet = [
        {"outlet_id": o["id"], "outlet": o["name"], **expenses[o["id"]]}
        for o in outlets
        # An outlet whose expenses were all reversed is left out, not shown as "Rp 0 · 0 entri".
        if expenses[o["id"]]["count"] or expenses[o["id"]]["amount"]
    ]
    by_outlet.sort(key=lambda e: -e["amount"])
    return {
        "from": date_from,
        "to": date_to,
        "granularity": granularity,
        "previous": {"from": prev_from, "to": prev_to},
        "totals": {
            "cash_in": tile("cash_in"),
            "cash_out": tile("cash_out"),
            "net": tile("net"),
            "pb1_collected": tile("pb1_collected"),
        },
        "series": _series(rows, date_from, date_to, granularity),
        "breakdown": {
            "revenue_excl_pb1": cur["revenue"],
            "pb1": cur["pb1"],
            "delivery_fee": cur["delivery_fee"],
            "cash": cur["cash"],
            "qris": cur["qris"],
            "refunds": cur["refunds"],
            "expenses": cur["expenses"],
            "cash_difference": cur["cash_difference"],
        },
        "expenses_by_outlet": by_outlet,
        "expenses_total": sum(e["amount"] for e in by_outlet),
        "expenses_count": sum(e["count"] for e in by_outlet),
    }


# O10 cash count ------------------------------------------------------------------------------


_CASH_COUNT = """
select s.id as shift_id, s.opened_at, s.closed_at, s.outlet_id, o.name as outlet_name,
       o.timezone, s.drawer_id, d.name as drawer_name,
       (select count(*) from app.cash_drawers d2
        where d2.outlet_id = d.outlet_id and d2.created_at <= d.created_at)
         as drawer_number,
       s.starting_cash, s.expected_cash, s.counted_cash, s.difference,
       u.display_name as counted_by
from app.cashier_shifts s
join app.outlets o on o.id = s.outlet_id
join app.cash_drawers d on d.id = s.drawer_id
left join app.users u on u.id = s.closed_by
where s.status = 'closed'
  and (%(outlet)s::uuid is null or s.outlet_id = %(outlet)s)
  and (%(drawer)s::uuid is null or s.drawer_id = %(drawer)s)
  and (s.opened_at at time zone o.timezone)::date between %(from)s and %(to)s
order by s.opened_at desc
"""


def _kind(difference: int) -> str:
    return "shortage" if difference < 0 else "surplus" if difference > 0 else "none"


async def cash_count(
    conn: AsyncConnection,
    *,
    outlet_id: UUID | None,
    drawer_id: UUID | None,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    """O10: closed shifts with expected, counted, and difference (posted to the ledger)."""
    validate_range(date_from, date_to)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        _CASH_COUNT,
        {
            "outlet": outlet_id,
            "drawer": drawer_id,
            "from": date_from,
            "to": date_to,
        },
    )
    rows = [
        {
            "shift_id": r["shift_id"],
            "opened_at": r["opened_at"],
            "closed_at": r["closed_at"],
            "timezone": r["timezone"],
            "outlet": {"id": r["outlet_id"], "name": r["outlet_name"]},
            "drawer": {
                "id": r["drawer_id"],
                "name": r["drawer_name"],
                "number": r["drawer_number"],
            },
            "starting_cash": r["starting_cash"],
            "expected_cash": r["expected_cash"],
            "counted_cash": r["counted_cash"],
            "difference": r["difference"],
            "kind": _kind(r["difference"]),
            "counted_by": r["counted_by"],
        }
        for r in await cur.fetchall()
    ]
    return {
        "from": date_from,
        "to": date_to,
        "summary": {
            "shifts": len(rows),
            "shifts_with_difference": sum(1 for r in rows if r["difference"]),
            "total_shortage": sum(r["difference"] for r in rows if r["difference"] < 0),
            "total_surplus": sum(r["difference"] for r in rows if r["difference"] > 0),
        },
        "rows": rows,
    }
