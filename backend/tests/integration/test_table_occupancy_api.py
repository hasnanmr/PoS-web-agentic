"""T-149 API tests against Postgres through RLS: automatic table occupancy (FR9.11,
AC9.14-AC9.19). A table with an open dine-in order (table QR or counter) or an open bill is
skipped for bookings that start today; other days are unaffected; existing bookings stay
and are flagged on the S6 board; "Kosongkan meja" releases the table until a new order;
activity older than 12 hours does not count; the O2 crowd card uses the same rule.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.core import reservations as core
from app.core.actor import ActorContext
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "t149.test"
OWNER = UUID("61490000-0000-0000-0000-0000000000f0")
STAFF = UUID("61490000-0000-0000-0000-0000000000f1")
WIB = ZoneInfo("Asia/Jakarta")

OPEN_ALL_DAY = {
    "is_enabled": True,
    "bookable_from": "00:00",
    "bookable_until": "23:59",
    "default_duration_minutes": 90,
    "booking_window_days": 14,
    "max_party_size": 8,
    "reminder_offset_minutes": 120,
    "cancellation_cutoff_minutes": 180,
}


def _bearer(sub: UUID, tenant: str | None, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=str(sub), tenant_id=tenant, app_role=role)}"}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    cleanup_domain(DOMAIN)
    invite_owner(OWNER, f"owner@{DOMAIN}")
    with TestClient(
        create_app(Settings(database_url=APP_URL), token_verifier=make_verifier())
    ) as c:
        yield c
    cleanup_domain(DOMAIN)


@pytest.fixture(scope="module")
def ctx(client: TestClient) -> dict[str, Any]:
    res = client.post(
        "/api/v1/owner/onboarding",
        headers=_bearer(OWNER, None, "owner_pending"),
        json={"business": {"name": "Kopi Meja", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, outlet = res.json()["tenant_id"], res.json()["outlet_id"]
    owner = _bearer(OWNER, tenant, "owner")
    admin_sql("insert into auth.users (id, email) values (%s, %s)", (STAFF, f"rina@{DOMAIN}"))
    admin_sql(
        "insert into app.users (id, tenant_id, email, display_name, role,"
        " invitation_accepted_at) values (%s, %s, %s, 'Rina', 'staff', now())",
        (STAFF, tenant, f"rina@{DOMAIN}"),
    )
    admin_sql(
        "insert into app.staff_outlets (user_id, outlet_id, tenant_id) values (%s, %s, %s)",
        (STAFF, outlet, tenant),
    )
    tables: dict[str, str] = {}
    for name, cap in (("M05", 4), ("M07", 4), ("M09", 6)):
        res = client.post(
            f"/api/v1/owner/outlets/{outlet}/tables",
            headers=owner,
            json={"name": name, "capacity": cap, "area": "Indoor", "is_bookable": True},
        )
        assert res.status_code == 201, res.text
        tables[name] = res.json()["id"]
    res = client.put(
        f"/api/v1/owner/outlets/{outlet}/reservation-settings", headers=owner, json=OPEN_ALL_DAY
    )
    assert res.status_code == 200, res.text
    return {
        "tenant": tenant,
        "outlet": outlet,
        "owner": owner,
        "staff": _bearer(STAFF, tenant, "staff"),
        "tables": tables,
    }


@pytest.fixture(autouse=True)
def fresh(ctx: dict[str, Any]) -> Iterator[None]:
    """Every test starts with free tables: no active bookings, orders, bills, or releases."""
    admin_sql(
        "update app.reservations set status = 'cancelled' where tenant_id = %s"
        " and status in ('booked', 'seated')",
        (ctx["tenant"],),
    )
    admin_sql(
        "update app.orders set status = 'cancelled' where tenant_id = %s"
        " and status not in ('completed', 'cancelled')",
        (ctx["tenant"],),
    )
    admin_sql(
        "update app.bills set status = 'voided' where tenant_id = %s and status = 'open'",
        (ctx["tenant"],),
    )
    admin_sql(
        "update app.tables set occupancy_released_at = null, occupancy_released_by = null"
        " where tenant_id = %s",
        (ctx["tenant"],),
    )
    yield


def _later_today(minutes: int = 30) -> datetime:
    """A start later today (WIB), on a whole minute; skips the test close to midnight."""
    now = datetime.now(WIB)
    start = (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
    if start.date() != now.date() or start.time() > time(23, 0):
        pytest.skip("too close to midnight for a booking later today")
    return start


def _tomorrow(hour: int = 12) -> datetime:
    return datetime.combine(datetime.now(WIB).date() + timedelta(days=1), time(hour), tzinfo=WIB)


def _order(
    ctx: dict[str, Any],
    table: str,
    *,
    channel: str = "web_table",
    status: str = "pending_payment",
    payment_mode: str = "pay_first",
    bill: str | None = None,
    created_at: str = "now()",
) -> str:
    """A dine-in order on a table, written directly (a table QR order by default, unpaid)."""
    number = admin_sql(
        "select coalesce(max(order_no), 1000) + 1 from app.orders where outlet_id = %s",
        (ctx["outlet"],),
    )[0][0]
    return str(
        admin_sql(
            "insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode,"
            " status, table_id, bill_id, subtotal, total, created_by_actor, access_key_hash,"
            " created_at) values (%s, %s, %s, %s, 'dine_in', %s, %s, %s, %s, 25000, 25000,"
            " 'system', case when %s = 'web_table'"
            " then encode(sha256(gen_random_uuid()::text::bytea), 'hex') end,"
            f" {created_at}) returning id",
            (
                ctx["tenant"],
                ctx["outlet"],
                number,
                channel,
                payment_mode,
                status,
                ctx["tables"][table],
                bill,
                channel,
            ),
        )[0][0]
    )


def _open_bill(ctx: dict[str, Any], table: str) -> str:
    return str(
        admin_sql(
            "insert into app.bills (tenant_id, outlet_id, table_id, opened_by_actor)"
            " values (%s, %s, %s, 'system') returning id",
            (ctx["tenant"], ctx["outlet"], ctx["tables"][table]),
        )[0][0]
    )


def _book(client: TestClient, ctx: dict[str, Any], starts_at: datetime, **body: Any):
    payload = {"guest_name": "Dewi", "party_size": 2, "source": "phone", **body}
    payload["starts_at"] = starts_at.isoformat()
    return client.post(
        f"/api/v1/ops/outlets/{ctx['outlet']}/reservations", headers=ctx["staff"], json=payload
    )


def _board(client: TestClient, ctx: dict[str, Any], day: date | None = None) -> dict[str, Any]:
    params = {"date": day.isoformat()} if day else {}
    res = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/reservations", headers=ctx["staff"], params=params
    )
    assert res.status_code == 200, res.text
    return res.json()


def _occupancy(board: dict[str, Any], ctx: dict[str, Any], table: str) -> dict[str, Any] | None:
    return next(t for t in board["tables"] if t["id"] == ctx["tables"][table])["occupancy"]


def test_qr_order_blocks_bookings_today_until_finished(client, ctx) -> None:
    """AC9.14 + AC9.16: an unpaid QR order occupies the table for today only."""
    order = _order(ctx, "M05")
    start = _later_today()
    res = _book(client, ctx, start, table_id=ctx["tables"]["M05"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "table_occupied", res.text
    # The smallest free table that fits skips M05 (M05 and M07 both seat 4).
    res = _book(client, ctx, start, party_size=4)
    assert res.status_code == 201, res.text
    assert res.json()["table_id"] == ctx["tables"]["M07"]
    # Tomorrow is unaffected.
    res = _book(client, ctx, _tomorrow(), table_id=ctx["tables"]["M05"])
    assert res.status_code == 201, res.text
    occ = _occupancy(_board(client, ctx), ctx, "M05")
    assert occ is not None and occ["open_orders"] == 1 and occ["bill_id"] is None
    assert occ["allowed_actions"] == ["release"]
    assert _occupancy(_board(client, ctx, _tomorrow().date()), ctx, "M05") is None
    # Completed (paid and served) → free again.
    admin_sql(
        "update app.orders set status = 'completed', payment_status = 'paid' where id = %s",
        (order,),
    )
    res = _book(client, ctx, start, table_id=ctx["tables"]["M05"])
    assert res.status_code == 201, res.text


def test_cancelled_order_frees_the_table(client, ctx) -> None:
    order = _order(ctx, "M05", channel="counter", status="confirmed")
    assert _occupancy(_board(client, ctx), ctx, "M05") is not None
    admin_sql("update app.orders set status = 'cancelled' where id = %s", (order,))
    assert _occupancy(_board(client, ctx), ctx, "M05") is None


def test_open_bill_blocks_until_closed_or_voided(client, ctx) -> None:
    """AC9.15: an open bill occupies its table; closing or voiding it frees the table."""
    bill = _open_bill(ctx, "M07")
    _order(ctx, "M07", channel="counter", status="served", payment_mode="open_bill", bill=bill)
    occ = _occupancy(_board(client, ctx), ctx, "M07")
    assert occ is not None and occ["bill_id"] == bill and occ["open_orders"] == 1
    res = _book(client, ctx, _later_today(), table_id=ctx["tables"]["M07"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "table_occupied"
    admin_sql(
        "update app.orders set status = 'completed', payment_status = 'paid' where bill_id = %s",
        (bill,),
    )
    admin_sql("update app.bills set status = 'voided' where id = %s", (bill,))
    res = _book(client, ctx, _later_today(), table_id=ctx["tables"]["M07"])
    assert res.status_code == 201, res.text


def test_existing_booking_stays_and_is_flagged(client, ctx) -> None:
    """AC9.17: an order on a table booked later today is accepted; the booking is flagged."""
    res = _book(client, ctx, _later_today(60), table_id=ctx["tables"]["M05"])
    assert res.status_code == 201, res.text
    booking = res.json()["id"]
    _order(ctx, "M05")
    rows = {r["id"]: r for r in _board(client, ctx)["reservations"]}
    assert rows[booking]["status"] == "booked"
    assert rows[booking]["table_occupied"] is True
    # The detail view never flags (only the board compares with occupancy).
    detail = client.get(f"/api/v1/ops/reservations/{booking}", headers=ctx["staff"]).json()
    assert detail["table_occupied"] is False
    # Seated guests ordering at their own table are not flagged.
    admin_sql(
        "update app.reservations set status = 'seated', starts_at = now(),"
        " ends_at = now() + interval '90 minutes' where id = %s",
        (booking,),
    )
    rows = {r["id"]: r for r in _board(client, ctx)["reservations"]}
    assert rows[booking]["table_occupied"] is False


def test_walk_in_move_and_delete_refused_on_an_occupied_table(client, ctx) -> None:
    _order(ctx, "M09")
    res = client.post(
        f"/api/v1/ops/outlets/{ctx['outlet']}/walk-ins",
        headers=ctx["staff"],
        json={"table_id": ctx["tables"]["M09"], "party_size": 4},
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "table_occupied"
    res = _book(client, ctx, _later_today(), table_id=ctx["tables"]["M05"])
    assert res.status_code == 201, res.text
    booking = res.json()["id"]
    res = client.post(
        f"/api/v1/ops/reservations/{booking}/move",
        headers=ctx["staff"],
        json={"table_id": ctx["tables"]["M09"]},
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "table_occupied"
    # A booking for tomorrow can move onto it.
    res = _book(client, ctx, _tomorrow(), table_id=ctx["tables"]["M05"])
    assert res.status_code == 201, res.text
    res = client.post(
        f"/api/v1/ops/reservations/{res.json()['id']}/move",
        headers=ctx["staff"],
        json={"table_id": ctx["tables"]["M09"]},
    )
    assert res.status_code == 204, res.text
    admin_sql(
        "update app.reservations set status = 'cancelled' where table_id = %s",
        (ctx["tables"]["M09"],),
    )
    res = client.delete(f"/api/v1/owner/tables/{ctx['tables']['M09']}", headers=ctx["owner"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "table_in_use"


def test_release_override_until_a_new_order(client, ctx) -> None:
    """AC9.18: Kosongkan meja frees the table, is audit-logged, and a new order re-occupies."""
    table = ctx["tables"]["M05"]
    res = client.post(f"/api/v1/ops/tables/{table}/release-occupancy", headers=ctx["staff"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "not_occupied"
    order = _order(ctx, "M05", status="ready", channel="counter")
    res = client.post(
        f"/api/v1/ops/tables/{table}/release-occupancy",
        headers=ctx["staff"],
        json={"reason": "Tamu sudah pulang"},
    )
    assert res.status_code == 204, res.text
    assert _occupancy(_board(client, ctx), ctx, "M05") is None
    # The order itself is not changed.
    assert admin_sql("select status::text from app.orders where id = %s", (order,)) == [("ready",)]
    audit = admin_sql(
        "select actor_id, reason, data->'order_ids' from app.audit_events"
        " where action = 'table.occupancy_released' and entity_id = %s",
        (table,),
    )
    assert audit == [(STAFF, "Tamu sudah pulang", [order])]
    assert admin_sql("select occupancy_released_by from app.tables where id = %s", (table,)) == [
        (STAFF,)
    ]
    res = _book(client, ctx, _later_today(), table_id=table)
    assert res.status_code == 201, res.text
    # A new order after the release occupies the table again.
    _order(ctx, "M05")
    assert _occupancy(_board(client, ctx), ctx, "M05") is not None


def test_new_order_on_an_open_bill_after_release_occupies_again(client, ctx) -> None:
    bill = _open_bill(ctx, "M07")
    admin_sql("update app.bills set opened_at = now() - interval '1 hour' where id = %s", (bill,))
    res = client.post(
        f"/api/v1/ops/tables/{ctx['tables']['M07']}/release-occupancy", headers=ctx["owner"]
    )
    assert res.status_code == 204, res.text
    assert _occupancy(_board(client, ctx), ctx, "M07") is None
    _order(ctx, "M07", channel="counter", status="confirmed", payment_mode="open_bill", bill=bill)
    assert _occupancy(_board(client, ctx), ctx, "M07") is not None


def test_activity_older_than_12_hours_does_not_count(client, ctx) -> None:
    """AC9.19: a forgotten order does not occupy the table; the crowd card agrees."""
    _order(ctx, "M05", created_at="now() - interval '13 hours'")
    assert _occupancy(_board(client, ctx), ctx, "M05") is None
    res = _book(client, ctx, _later_today(), table_id=ctx["tables"]["M05"])
    assert res.status_code == 201, res.text
    _order(ctx, "M07")
    _open_bill(ctx, "M09")
    res = client.get(
        "/api/v1/owner/dashboard", headers=ctx["owner"], params={"outlet_id": ctx["outlet"]}
    )
    assert res.status_code == 200, res.text
    crowd = res.json()["current_crowd"][0]
    assert crowd["occupied_tables"] == 2 and crowd["total_tables"] == 3


async def test_available_times_skip_occupied_tables_today_only(client, ctx) -> None:
    """C10 and the agent read these times: only M09 seats 6, so an order on it empties today."""
    assert APP_URL
    start = _later_today(60)
    _order(ctx, "M09")
    pool = db.create_pool(APP_URL, min_size=1, max_size=1)
    await pool.open()
    try:
        actor = ActorContext.for_user(UUID(ctx["tenant"]), OWNER)
        async with db.transaction(pool, actor) as conn:
            now = datetime.now(UTC)
            today = await core.available_start_times(
                conn, UUID(ctx["outlet"]), start.date(), 6, now=now
            )
            assert today == []
            assert await core.available_start_times(
                conn, UUID(ctx["outlet"]), start.date(), 4, now=now
            )
            tomorrow = await core.available_start_times(
                conn, UUID(ctx["outlet"]), _tomorrow().date(), 6, now=now
            )
            assert len(tomorrow) == 48  # 00:00 … 23:30 every 30 minutes
    finally:
        await pool.close()
