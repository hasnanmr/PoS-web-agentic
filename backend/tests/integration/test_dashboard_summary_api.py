"""O2 tab Ringkasan `GET /owner/dashboard` (T-071, T-123) against Postgres through RLS:
KPI tiles from the ledger, paid-order counts, busy/quiet hours and the hour filter, the
4-week busyness map, current crowd, low stock, owner only.

Two outlets: "Dago" gets real orders through the counter API (cash + QRIS, ledger posted by
the app); "Riau" gets rows written directly at chosen outlet-local hours.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "o2sum.test"
OWNER = UUID("50000000-0000-0000-0000-0000000002e0")
STAFF = UUID("50000000-0000-0000-0000-0000000002e1")
URL = "/api/v1/owner/dashboard"
TZ = "Asia/Jakarta"
# The O2 wireframe's "Order per jam · hari ini": 109 orders from 08 to 21.
WIREFRAME = {8: 2, 9: 4, 10: 6, 11: 9, 12: 14, 13: 12, 14: 7, 15: 3, 16: 4, 17: 8, 18: 12, 19: 14,
             20: 10, 21: 4}  # fmt: skip
LOCAL_MIDNIGHT = f"(date_trunc('day', now() at time zone '{TZ}') at time zone '{TZ}')"


def _bearer(sub: UUID, tenant: str | None, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=str(sub), tenant_id=tenant, app_role=role)}"}


def _opening_hours(tenant: str, outlet: str) -> None:
    """Every day 08:00-22:00, as on the wireframe."""
    admin_sql("delete from app.outlet_opening_hours where outlet_id = %s", (outlet,))
    admin_sql(
        "insert into app.outlet_opening_hours (outlet_id, tenant_id, weekday, opens_at, closes_at)"
        " select %s, %s, d, '08:00', '22:00' from generate_series(1, 7) d",
        (outlet, tenant),
    )


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
        json={"business": {"name": "Kopi Ringkas", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, dago = res.json()["tenant_id"], res.json()["outlet_id"]
    owner = _bearer(OWNER, tenant, "owner")
    res = client.post("/api/v1/owner/outlets", headers=owner, json={"name": "Riau"})
    assert res.status_code == 201, res.text
    riau = res.json()["id"]
    res = client.post("/api/v1/owner/outlets", headers=owner, json={"name": "Kemang"})
    assert res.status_code == 201, res.text
    kemang = res.json()["id"]  # money tests only
    for outlet in (dago, riau, kemang):
        _opening_hours(tenant, outlet)
    admin_sql("insert into auth.users (id, email) values (%s, %s)", (STAFF, f"rina@{DOMAIN}"))
    admin_sql(
        "insert into app.users (id, tenant_id, email, display_name, role,"
        " invitation_accepted_at) values (%s, %s, %s, 'Rina', 'staff', now())",
        (STAFF, tenant, f"rina@{DOMAIN}"),
    )
    admin_sql(
        "insert into app.staff_outlets (user_id, outlet_id, tenant_id) values (%s, %s, %s)",
        (STAFF, dago, tenant),
    )
    staff = _bearer(STAFF, tenant, "staff")
    menu = client.get(f"/api/v1/ops/outlets/{dago}/menu", headers=staff).json()
    americano = next(m for m in menu if m["name"] == "Americano")
    drawers = client.get(f"/api/v1/ops/outlets/{dago}/drawers", headers=staff).json()
    return {
        "tenant": tenant,
        "dago": dago,
        "riau": riau,
        "kemang": kemang,
        "owner": owner,
        "staff": staff,
        "americano": americano,
        "drawer": drawers[0]["drawer"]["id"],
    }


def _get(client: TestClient, ctx: dict[str, Any], **params: str) -> dict[str, Any]:
    res = client.get(URL, headers=ctx["owner"], params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _insert_orders(ctx: dict[str, Any], outlet: str, n: int, at: str, **cols: str) -> None:
    """`n` paid counter orders of Rp 10.000 created at the SQL timestamp `at`."""
    channel = cols.get("channel", "counter")
    kind = cols.get("type", "takeaway")
    status = cols.get("status", "completed")
    payment = cols.get("payment", "paid")
    table = cols.get("table_id")
    admin_sql(
        "insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode,"
        " status, payment_status, table_id, subtotal, total, created_by_actor, created_at)"
        " select %s, %s, (select coalesce(max(order_no), 1000) from app.orders"
        "   where outlet_id = %s) + g, %s, %s, 'pay_first', %s, %s, %s, 10000, 10000, 'system',"
        f" {at} from generate_series(1, %s) g",
        (ctx["tenant"], outlet, outlet, channel, kind, status, payment, table, n),
    )


def _paid_order(ctx: dict[str, Any], outlet: str, at: str, subtotal: int, pb1: int = 0,
                delivery: int = 0, *, paid_days_later: int = 0) -> str:  # fmt: skip
    """A paid order created at the SQL timestamp `at`, with its ledger rows (revenue, PB1,
    delivery fee) posted on the payment date `paid_days_later` days after it."""
    kind = ("whatsapp_online", "delivery") if delivery else ("counter", "takeaway")
    order = admin_sql(
        "insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode,"
        " status, payment_status, subtotal, pb1_amount, delivery_fee, total, delivery_address,"
        " created_by_actor, created_at) select %s, %s, coalesce(max(order_no), 1000) + 1, %s, %s,"
        " 'pay_first', 'completed', 'paid', %s, %s, %s, %s, %s, 'system', "
        f"{at} from app.orders where outlet_id = %s returning id, created_at",
        (ctx["tenant"], outlet, *kind, subtotal, pb1, delivery, subtotal + pb1 + delivery,
         "Jl. Riau 1" if delivery else None, outlet),
    )  # fmt: skip
    order_id, created = order[0]
    day = created.astimezone(ZoneInfo(TZ)).date() + timedelta(days=paid_days_later)
    for kind_, amount in (("revenue", subtotal), ("pb1", pb1), ("delivery_fee", delivery)):
        if amount:
            _ledger(ctx, outlet, kind_, amount, day, order_id)
    return str(order_id)


def _ledger(ctx: dict[str, Any], outlet: str, kind: str, amount: int, day: Any, order: Any,
            pb1_portion: int = 0) -> None:  # fmt: skip
    admin_sql(
        "insert into app.ledger_entries (tenant_id, outlet_id, type, amount, payment_method,"
        " business_date, pb1_portion, order_id, actor_type) values (%s, %s, %s, %s, 'qris', %s,"
        " %s, %s, 'system')",
        (ctx["tenant"], outlet, kind, amount, day, pb1_portion, order),
    )


def test_kpis_and_methods_from_real_counter_orders(client, ctx) -> None:
    res = client.post(
        f"/api/v1/ops/drawers/{ctx['drawer']}/shifts",
        headers=ctx["staff"],
        json={"starting_cash": 200000},
    )
    assert res.status_code == 201, res.text
    totals = []
    for payment in ({"method": "cash", "cash_received": 100000}, {"method": "qris"}):
        res = client.post(
            f"/api/v1/ops/outlets/{ctx['dago']}/orders",
            headers=ctx["staff"],
            json={
                "type": "takeaway",
                "items": [{"product_id": ctx["americano"]["product_id"], "quantity": 2}],
                "payment": payment,
            },
        )
        assert res.status_code == 201, res.text
        totals.append(res.json()["total"])

    body = _get(client, ctx, outlet_id=ctx["dago"])
    assert body["period"] == "today" and body["hours"] == "all"
    k = body["kpis"]
    assert k["revenue_excl_pb1"] == sum(totals)  # PB1 is off on a new outlet
    assert k["change_pct"] is None  # nothing yesterday
    assert (k["orders"], k["cash_count"], k["qris_count"]) == (2, 1, 1)
    assert (k["pb1_collected"], k["delivery_fee"], k["delivery_orders"]) == (0, 0, 0)
    assert body["payment_methods"] == [
        {"method": "cash", "amount": totals[0], "transactions": 1},
        {"method": "qris", "amount": totals[1], "transactions": 1},
    ]
    assert body["channel_mix"] == [
        {"channel": "web_online", "orders": 0, "share_pct": 0},
        {"channel": "web_table", "orders": 0, "share_pct": 0},
        {"channel": "counter", "orders": 2, "share_pct": 100},
    ]  # the Phase 3 WhatsApp channels appear only when they have orders
    # Week and month include today.
    for period in ("week", "month"):
        assert _get(client, ctx, outlet_id=ctx["dago"], period=period)["kpis"]["orders"] == 2


def test_money_follows_order_time_refunds_and_previous_period(client, ctx) -> None:
    kemang = ctx["kemang"]
    today = datetime.now(ZoneInfo(TZ)).date()
    noon = f"{LOCAL_MIDNIGHT} + interval '12 hours'"
    _paid_order(ctx, kemang, noon, 150000, pb1=15000)
    # A delivery order reversed the same day: revenue, PB1 and delivery fee all go back to 0.
    reversed_id = _paid_order(ctx, kemang, noon, 50000, pb1=5000, delivery=10000)
    _ledger(ctx, kemang, "refund", -65000, today, reversed_id, pb1_portion=5000)
    # Opened yesterday 23:30, paid today: counts yesterday (order time), not today.
    _paid_order(ctx, kemang, f"{LOCAL_MIDNIGHT} - interval '30 minutes'", 80000,
                paid_days_later=1)  # fmt: skip
    k = _get(client, ctx, outlet_id=kemang)["kpis"]
    assert k["revenue_excl_pb1"] == 150000
    assert k["pb1_collected"] == 15000
    assert k["delivery_fee"] == 0
    assert k["change_pct"] == 88  # 150.000 vs 80.000 yesterday


def test_hour_filter_counts_money_by_order_hour(client, ctx) -> None:
    """Money follows the hour the order was created, not when it was paid: with any hour
    filter, revenue matches the orders counted (every order here is Rp 10.000, and all its
    ledger rows are posted now, at some other hour)."""
    res = client.post("/api/v1/owner/outlets", headers=ctx["owner"], json={"name": "Senopati"})
    assert res.status_code == 201, res.text
    outlet = res.json()["id"]
    _opening_hours(ctx["tenant"], outlet)
    for hour, n in ((8, 1), (12, 6), (13, 1), (14, 1)):
        for _ in range(n):
            _paid_order(ctx, outlet, f"{LOCAL_MIDNIGHT} + interval '{hour} hours 5 minutes'", 10000)
    seen = set()
    for hours in ("all", "busy", "quiet"):
        k = _get(client, ctx, outlet_id=outlet, hours=hours)["kpis"]
        assert k["revenue_excl_pb1"] == k["orders"] * 10000, hours
        seen.add(k["orders"])
    assert 9 in seen  # "all" counts every order


def test_orders_per_hour_marks_and_hour_filter(client, ctx) -> None:
    riau = ctx["riau"]
    for hour, n in WIREFRAME.items():
        _insert_orders(ctx, riau, n, f"{LOCAL_MIDNIGHT} + interval '{hour} hours 10 minutes'")
    # Not counted: unpaid and cancelled.
    _insert_orders(ctx, riau, 5, f"{LOCAL_MIDNIGHT} + interval '12 hours'", payment="unpaid",
                   status="pending_payment")  # fmt: skip
    _insert_orders(ctx, riau, 5, f"{LOCAL_MIDNIGHT} + interval '12 hours'", status="cancelled")

    body = _get(client, ctx, outlet_id=riau)
    series = body["orders_per_hour"]
    assert [s["hour"] for s in series] == list(range(8, 22))
    assert {s["hour"]: s["orders"] for s in series} == WIREFRAME
    assert body["busy_summary"] == {"hours": [12, 13, 18, 19], "orders": 52, "share_pct": 48}
    assert body["quiet_summary"] == {"hours": [8, 9, 15, 16, 21], "orders": 17, "share_pct": 16}
    assert body["kpis"]["orders"] == 109

    busy = _get(client, ctx, outlet_id=riau, hours="busy")
    assert busy["kpis"]["orders"] == 52
    assert busy["channel_mix"][2] == {"channel": "counter", "orders": 52, "share_pct": 100}
    assert busy["orders_per_hour"] == series  # the chart itself is not filtered
    quiet = _get(client, ctx, outlet_id=riau, hours="quiet")
    assert quiet["kpis"]["orders"] == 17


def test_busyness_map_averages_four_weeks_in_opening_hours(client, ctx) -> None:
    riau = ctx["riau"]
    week_ago = f"{LOCAL_MIDNIGHT} - interval '7 days' + interval '12 hours 30 minutes'"
    _insert_orders(ctx, riau, 8, week_ago)
    _insert_orders(ctx, riau, 40, f"{LOCAL_MIDNIGHT} - interval '40 days' + interval '12 hours'")
    body = _get(client, ctx, outlet_id=riau, period="month", hours="busy")
    cells = body["busyness_map"]
    assert len(cells) == 7 * 14  # every weekday, 08..21
    weekday = (datetime.now(ZoneInfo(TZ)).date() - timedelta(days=7)).isoweekday()
    by = {(c["weekday"], c["hour"]): c["avg_orders"] for c in cells}
    assert by[(weekday, 12)] == 2.0  # 8 orders over 4 weeks; today and 40 days ago excluded
    assert sum(by.values()) == 2.0


def test_current_crowd_from_tables_bills_and_active_orders(client, ctx) -> None:
    riau = ctx["riau"]
    tables = [
        admin_sql(
            "insert into app.tables (tenant_id, outlet_id, name, capacity) values (%s, %s, %s, 4)"
            " returning id",
            (ctx["tenant"], riau, f"M{i}"),
        )[0][0]
        for i in range(1, 5)
    ]
    admin_sql(
        "insert into app.bills (tenant_id, outlet_id, table_id, opened_by_actor)"
        " values (%s, %s, %s, 'system')",
        (ctx["tenant"], riau, tables[0]),
    )
    _insert_orders(ctx, riau, 2, "now()", channel="whatsapp_table", type="dine_in",
                   status="preparing", payment="paid", table_id=str(tables[1]))  # fmt: skip
    _insert_orders(ctx, riau, 1, "now() - interval '2 days'", status="ready")  # stale
    crowd = {c["name"]: c for c in _get(client, ctx)["current_crowd"]}
    assert crowd["Riau"]["occupied_tables"] == 2
    assert crowd["Riau"]["total_tables"] == 4
    assert crowd["Riau"]["active_orders"] == 2
    assert crowd["Riau"]["level"] == "normal"  # 50%
    assert crowd["Riau"]["timezone"] == TZ
    admin_sql(
        "insert into app.reservations (tenant_id, outlet_id, table_id, guest_name, party_size,"
        " starts_at, ends_at, source, status, created_by_actor) values (%s, %s, %s, 'Budi', 2,"
        " now() - interval '10 minutes', now() + interval '80 minutes', 'walk_in', 'seated',"
        " 'system')",
        (ctx["tenant"], riau, tables[2]),
    )
    crowd = {c["name"]: c for c in _get(client, ctx)["current_crowd"]}
    assert crowd["Riau"]["occupied_tables"] == 3
    assert crowd["Riau"]["level"] == "ramai"  # 75%
    # A seated walk-in and an open bill nobody closed since yesterday do not count.
    admin_sql(
        "update app.reservations set starts_at = now() - interval '20 hours',"
        " ends_at = now() - interval '18 hours' where table_id = %s",
        (tables[2],),
    )
    admin_sql("update app.bills set opened_at = now() - interval '20 hours' where table_id = %s",
              (tables[0],))  # fmt: skip
    crowd = {c["name"]: c for c in _get(client, ctx)["current_crowd"]}
    assert crowd["Riau"]["occupied_tables"] == 1  # only the table with the live order
    assert crowd["Dago"]["total_tables"] == 0 and crowd["Dago"]["level"] in ("sepi", "normal")


def test_low_stock_lists_out_then_low_for_the_selected_outlets(client, ctx) -> None:
    items = admin_sql(
        "select id, name from app.stock_items where tenant_id = %s and is_active order by name",
        (ctx["tenant"],),
    )
    for sid, _ in items:  # Dago: everything plenty, one item low, one out
        admin_sql(
            "insert into app.outlet_stock (tenant_id, outlet_id, stock_item_id, on_hand,"
            " low_threshold) values (%s, %s, %s, 100000, 10) on conflict (outlet_id,"
            " stock_item_id) do update set on_hand = 100000, low_threshold = 10",
            (ctx["tenant"], ctx["dago"], sid),
        )
    admin_sql(
        "update app.outlet_stock set on_hand = 5 where outlet_id = %s and stock_item_id = %s",
        (ctx["dago"], items[0][0]),
    )
    admin_sql(
        "update app.outlet_stock set on_hand = 0 where outlet_id = %s and stock_item_id = %s",
        (ctx["dago"], items[1][0]),
    )
    rows = _get(client, ctx, outlet_id=ctx["dago"])["low_stock"]
    assert [(r["stock_item"], r["status"], r["outlet"]) for r in rows] == [
        (items[1][1], "out", "Dago"),
        (items[0][1], "low", "Dago"),
    ]
    assert rows[1]["on_hand"] == "5.000" and rows[1]["low_threshold"] == "10.000"
    # All outlets: Riau never stocked these items, so nothing shows as sold out there.
    every = _get(client, ctx)["low_stock"]
    assert [(r["stock_item"], r["outlet"]) for r in every] == [
        (items[1][1], "Dago"),
        (items[0][1], "Dago"),
    ]


def test_owner_only_validation_and_tenant_isolation(client, ctx) -> None:
    assert client.get(URL, headers=ctx["staff"]).status_code == 403
    assert client.get(URL, headers=ctx["owner"], params={"period": "year"}).status_code == 422
    assert client.get(URL, headers=ctx["owner"], params={"hours": "peak"}).status_code == 422
    other = "00000000-0000-0000-0000-000000000099"
    res = client.get(URL, headers=ctx["owner"], params={"outlet_id": other})
    assert res.status_code == 404

    owner, domain = UUID("50000000-0000-0000-0000-0000000002e2"), "o2sumempty.test"
    cleanup_domain(domain)
    invite_owner(owner, f"owner@{domain}")
    try:
        res = client.post(
            "/api/v1/owner/onboarding",
            headers=_bearer(owner, None, "owner_pending"),
            json={"business": {"name": "Kosong", "type": "cafe"}, "outlet": {"name": "Riau"}},
        )
        assert res.status_code == 201, res.text
        body = client.get(URL, headers=_bearer(owner, res.json()["tenant_id"], "owner")).json()
        assert body["kpis"]["orders"] == 0 and body["kpis"]["revenue_excl_pb1"] == 0
        assert sum(c["avg_orders"] for c in body["busyness_map"]) == 0
        assert [c["name"] for c in body["current_crowd"]] == ["Riau"]
    finally:
        cleanup_domain(domain)
