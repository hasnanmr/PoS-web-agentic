"""Owner audit log of order changes — wireframe O11 (T-101).

Read-only view of `app.order_events` (append-only): reversals, status changes, and payment
changes, newest first. Contract: docs/architecture/screen-endpoint-map.md → O11.
Order creation is history, not a change, so it is left out.
"""

from __future__ import annotations

import base64
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.errors import ValidationFailedError
from app.core.orders import order_label

Kind = Literal["reversal", "status", "payment"]
PAGE_SIZE = 50  # O11 "Muat lagi" loads 50 more
KINDS: tuple[Kind, ...] = ("reversal", "status", "payment")
_EVENTS: dict[Kind, tuple[str, ...]] = {
    "reversal": ("reversed",),
    "status": ("status_changed",),
    "payment": ("payment_changed", "proof_rejected"),
}
_KIND_OF = {event: kind for kind, events in _EVENTS.items() for event in events}
_METHOD = {"cash": "cash", "qris": "QRIS", "transfer": "transfer"}

_SELECT = """
select e.id, e.created_at, e.event, e.from_status::text as from_status,
       e.to_status::text as to_status, e.from_payment::text as from_payment,
       e.to_payment::text as to_payment, e.reason, e.data,
       e.actor_type::text as actor_type, e.actor_id, u.display_name as actor_name,
       u.role::text as actor_role,
       o.id as order_id, o.order_no, ol.order_prefix, ol.timezone, ol.id as outlet_id
from app.order_events e
join app.orders o on o.id = e.order_id
join app.outlets ol on ol.id = e.outlet_id
left join app.users u on u.id = e.actor_id
where e.event = any(%(events)s)
  and (%(outlet)s::uuid is null or e.outlet_id = %(outlet)s)
  and (%(actor)s::uuid is null or e.actor_id = %(actor)s)
  -- Without dates: month to date in each event's own outlet zone (a WITA outlet's today can
  -- already be tomorrow in WIB).
  and (e.created_at at time zone ol.timezone)::date
      between coalesce(%(from)s::date, date_trunc('month', now() at time zone ol.timezone)::date)
          and coalesce(%(to)s::date, (now() at time zone ol.timezone)::date)
  and (%(after_at)s::timestamptz is null
       or (e.created_at, e.id) < (%(after_at)s::timestamptz, %(after_id)s::bigint))
order by e.created_at desc, e.id desc
limit %(limit)s
"""


def change_text(row: dict[str, Any]) -> str:
    """What changed, as on the wireframe: "paid → refunded", "preparing → ready",
    "proof rejected", "marked paid (QRIS)"."""
    event, data = row["event"], row["data"] or {}
    if event == "reversed":
        text = f"{row['from_payment']} → {row['to_payment']}"
        if data.get("ingredients"):
            text += f" · bahan → {data['ingredients']}"
        return text
    if event == "proof_rejected":
        return "proof rejected"
    if event == "payment_changed":
        method = _METHOD.get(data.get("method", ""))
        if row["to_payment"] == "paid" and method:
            return f"marked paid ({method})"
        return f"{row['from_payment']} → {row['to_payment']}"
    return f"{row['from_status']} → {row['to_status']}"


def _encode(row: dict[str, Any]) -> str:
    raw = f"{row['created_at'].isoformat()}|{row['id']}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(cursor: str) -> tuple[datetime, int]:
    try:
        at, event_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(at), int(event_id)
    except (ValueError, UnicodeDecodeError):
        raise ValidationFailedError("invalid cursor", {"field": "cursor"}) from None


async def list_events(
    conn: AsyncConnection,
    *,
    outlet_id: UUID | None,
    actor_id: UUID | None,
    kinds: list[Kind],
    date_from: date | None,
    date_to: date | None,
    cursor: str | None,
    limit: int = PAGE_SIZE,
) -> dict[str, Any]:
    """O11 rows, newest first. Days are each outlet's local days; without dates, month to
    date per outlet."""
    if date_from and date_to and date_from > date_to:
        raise ValidationFailedError("the start date is after the end date", {"field": "from"})
    after = _decode(cursor) if cursor else None
    events = [e for k in (kinds or KINDS) for e in _EVENTS[k]]
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        _SELECT,
        {
            "events": events,
            "outlet": outlet_id,
            "actor": actor_id,
            "from": date_from,
            "to": date_to,
            "after_at": after[0] if after else None,
            "after_id": after[1] if after else None,
            "limit": limit + 1,
        },
    )
    rows = await cur.fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "timezone": r["timezone"],
                "outlet_id": r["outlet_id"],
                "order_id": r["order_id"],
                "order_no": order_label(r["order_prefix"], r["order_no"]),
                "kind": _KIND_OF[r["event"]],
                "change": change_text(r),
                "actor": {
                    "type": r["actor_type"],
                    "id": r["actor_id"],
                    "name": r["actor_name"],
                    "role": r["actor_role"],
                },
                "reason": r["reason"],
            }
            for r in rows
        ],
        "next_cursor": _encode(rows[-1]) if more and rows else None,
    }
