"""O2b drawer `GET /owner/dashboard/orders` and O2 Rentang (`period=range`) against Postgres
through RLS: the drawer totals equal the O2 figure that was clicked (Revenue / Order tile, an
Order per jam bar, an Item terlaris row); chips, Kanal, and search filter only the list;
cursor paging; range validation; owner only.

"Dago" gets real orders through the counter API (items, cash + QRIS, ledger posted by the
app); "Riau" gets rows written directly at chosen outlet-local hours.
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

DOMAIN = "o2drill.test"
OWNER = UUID("50000000-0000-0000-0000-0000000002d0")
STAFF = UUID("50000000-0000-0000-0000-0000000002d1")
URL = "/api/v1/owner/dashboard/orders"
SUMMARY = "/api/v1/owner/dashboard"
TOP = "/api/v1/owner/dashboard/top-items"
TZ = "Asia/Jakarta"
WIREFRAME = {8: 2, 9: 4, 10: 6, 11: 9, 12: 14, 13: 12, 14: 7, 15: 3, 16: 4, 17: 8, 18: 12, 19: 14,
             20: 10, 21: 4}  # fmt: skip
LOCAL_MIDNIGHT = f"(date_trunc('day', now() at time zone '{TZ}') at time zone '{TZ}')"


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
        json={"business": {"name": "Kopi Drill", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, dago = res.json()["tenant_id"], res.json()["outlet_id"]
    owner = _bearer(OWNER, tenant, "owner")
    res = client.post("/api/v1/owner/outlets", headers=owner, json={"name": "Riau"})
    assert res.status_code == 201, res.text
    riau = res.json()["id"]
    for outlet in (dago, riau):
        admin_sql("delete from app.outlet_opening_hours where outlet_id = %s", (outlet,))
        admin_sql(
            "insert into app.outlet_opening_hours (outlet_id, tenant_id, weekday, opens_at,"
            " closes_at) select %s, %s, d, '08:00', '22:00' from generate_series(1, 7) d",
            (outlet, tenant),
        )
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
    other = next(
        m
        for m in menu
        if m["name"] != "Americano"
        and not m["sold_out"]
        and not any(g["is_required"] for g in m["addon_groups"])
    )
    drawers = client.get(f"/api/v1/ops/outlets/{dago}/drawers", headers=staff).json()
    res = client.post(
        f"/api/v1/ops/drawers/{drawers[0]['drawer']['id']}/shifts",
        headers=staff,
        json={"starting_cash": 200000},
    )
    assert res.status_code == 201, res.text
    # Dago today: Americano x2 cash, Americano x1 QRIS, other x1 QRIS.
    orders = []
    for product, qty, payment in (
        (americano, 2, {"method": "cash", "cash_received": 200000}),
        (americano, 1, {"method": "qris"}),
        (other, 1, {"method": "qris"}),
    ):
        res = client.post(
            f"/api/v1/ops/outlets/{dago}/orders",
            headers=staff,
            json={
                "type": "takeaway",
                "items": [{"product_id": product["product_id"], "quantity": qty}],
                "payment": payment,
            },
        )
        assert res.status_code == 201, res.text
        orders.append(res.json())
    # Riau today: the O2 wireframe's 109 orders from 08 to 21, plus 5 yesterday.
    for hour, n in WIREFRAME.items():
        _insert_orders(tenant, riau, n, f"{LOCAL_MIDNIGHT} + interval '{hour} hours 10 minutes'")
    _insert_orders(tenant, riau, 5, f"{LOCAL_MIDNIGHT} - interval '10 hours'")
    # Not counted: unpaid and cancelled.
    _insert_orders(tenant, riau, 3, f"{LOCAL_MIDNIGHT} + interval '12 hours'", payment="unpaid",
                   status="pending_payment")  # fmt: skip
    _insert_orders(tenant, riau, 3, f"{LOCAL_MIDNIGHT} + interval '12 hours'", status="cancelled")
    return {
        "tenant": tenant,
        "dago": dago,
        "riau": riau,
        "owner": owner,
        "staff": staff,
        "americano": americano,
        "orders": orders,
    }


def _insert_orders(tenant: str, outlet: str, n: int, at: str, *, status: str = "completed",
                   payment: str = "paid") -> None:  # fmt: skip
    """`n` paid counter orders of Rp 10.000 (no payment row) created at the SQL time `at`."""
    admin_sql(
        "insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode,"
        " status, payment_status, subtotal, total, created_by_actor, created_at)"
        " select %s, %s, (select coalesce(max(order_no), 1000) from app.orders"
        "   where outlet_id = %s) + g, 'counter', 'takeaway', 'pay_first', %s, %s, 10000, 10000,"
        f" 'system', {at} from generate_series(1, %s) g",
        (tenant, outlet, outlet, status, payment, n),
    )


def _get(client: TestClient, ctx: dict[str, Any], url: str = URL, **params: Any) -> dict[str, Any]:
    res = client.get(url, headers=ctx["owner"], params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _today() -> Any:
    return datetime.now(ZoneInfo(TZ)).date()


def test_tiles_drawer_matches_kpis_and_lists_orders(client, ctx) -> None:
    dago = ctx["dago"]
    kpis = _get(client, ctx, SUMMARY, outlet_id=dago)["kpis"]
    body = _get(client, ctx, outlet_id=dago)
    assert body["period"] == "today"
    s = body["summary"]
    assert s["orders"] == kpis["orders"] == 3
    assert s["revenue_excl_pb1"] == kpis["revenue_excl_pb1"]
    assert (s["cash_count"], s["qris_count"]) == (kpis["cash_count"], kpis["qris_count"]) == (1, 2)
    assert body["item"] is None
    assert body["by_outlet"] == [
        {"outlet_id": dago, "name": "Dago", "orders": 3, "revenue_excl_pb1": s["revenue_excl_pb1"]}
    ]
    rows = body["orders"]
    assert [r["order_no"] for r in rows] == [o["order_no"] for o in reversed(ctx["orders"])]
    first = rows[-1]  # the cash Americano x2
    assert first["payment_method"] == "cash"
    assert first["item_summary"] == "2× Americano"  # noqa: RUF001
    assert first["channel"] == "counter" and first["type"] == "takeaway"
    assert first["outlet"] == "Dago" and first["timezone"] == TZ
    assert first["revenue_excl_pb1"] == first["total"]  # PB1 off on a new outlet
    assert body["next_cursor"] is None


def test_chips_channel_and_search_filter_only_the_list(client, ctx) -> None:
    dago = ctx["dago"]
    full = _get(client, ctx, outlet_id=dago)["summary"]
    cash = _get(client, ctx, outlet_id=dago, method="cash")
    assert cash["summary"] == full
    assert [r["payment_method"] for r in cash["orders"]] == ["cash"]
    assert len(_get(client, ctx, outlet_id=dago, method="qris")["orders"]) == 2
    for channel in ("whatsapp_online", "web_table"):
        body = _get(client, ctx, outlet_id=dago, channel=channel)
        assert body["orders"] == [] and body["summary"] == full
    label = ctx["orders"][1]["order_no"]  # "#A-1002" style
    number = label.split("-")[-1]
    for q in (label, label.lstrip("#"), number):
        assert [r["order_no"] for r in _get(client, ctx, outlet_id=dago, q=q)["orders"]] == [label]
    assert _get(client, ctx, outlet_id=dago, q="Z-" + number)["orders"] == []
    assert _get(client, ctx, outlet_id=dago, q="kopi")["orders"] == []
    # A phone number pasted into the box is no order number (and no 500, #75).
    assert _get(client, ctx, outlet_id=dago, q="081234567890")["orders"] == []


def test_item_row_drawer_matches_top_items(client, ctx) -> None:
    dago = ctx["dago"]
    top = _get(client, ctx, TOP, outlet_id=dago)["top_items"]
    americano = next(t for t in top if t["name"] == "Americano")
    assert americano["product_id"] == ctx["americano"]["product_id"]
    for period, card in (("today", "day"), ("month", "month"), ("year", "year")):
        row = next(
            t for t in _get(client, ctx, TOP, outlet_id=dago, period=card)["top_items"]
            if t["name"] == "Americano"
        )  # fmt: skip
        body = _get(client, ctx, outlet_id=dago, period=period, product_id=row["product_id"])
        assert body["item"] == {
            "product_id": row["product_id"],
            "name": "Americano",
            "quantity": row["quantity_sold"],
            "revenue": row["revenue"],
        }
        assert body["summary"]["orders"] == 2
        assert all("Americano" in r["item_summary"] for r in body["orders"])


def test_hour_bar_and_busy_hours_match_o2(client, ctx) -> None:
    riau = ctx["riau"]
    o2 = _get(client, ctx, SUMMARY, outlet_id=riau)
    bar = next(b for b in o2["orders_per_hour"] if b["hour"] == 12)
    body = _get(client, ctx, outlet_id=riau, hour=12)
    assert body["summary"]["orders"] == bar["orders"] == 14
    assert body["summary"]["revenue_excl_pb1"] == 140000
    assert len(body["orders"]) == 14
    busy = _get(client, ctx, SUMMARY, outlet_id=riau, hours="busy")["kpis"]
    drawer = _get(client, ctx, outlet_id=riau, hours="busy")["summary"]
    assert drawer["orders"] == busy["orders"] == 52
    # A bar outside the busy hours with hours=busy: nothing.
    assert _get(client, ctx, outlet_id=riau, hours="busy", hour=8)["summary"]["orders"] == 0


def test_cursor_pages_newest_first_without_gaps(client, ctx) -> None:
    riau, seen, cursor = ctx["riau"], [], None
    while True:
        params: dict[str, Any] = {"outlet_id": ctx["riau"], "limit": 40}
        if cursor:
            params["cursor"] = cursor
        body = _get(client, ctx, **params)
        assert body["summary"]["orders"] == 109
        seen += body["orders"]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 109 and len({r["id"] for r in seen}) == 109
    times = [r["created_at"] for r in seen]
    assert times == sorted(times, reverse=True)
    res = client.get(URL, headers=ctx["owner"], params={"outlet_id": riau, "cursor": "nope"})
    assert res.status_code == 422 and res.json()["error"]["details"]["field"] == "cursor"


def test_all_outlets_by_outlet_largest_revenue_first(client, ctx) -> None:
    body = _get(client, ctx)
    assert [o["name"] for o in body["by_outlet"]] == ["Riau", "Dago"]
    assert body["summary"]["orders"] == 112
    assert body["summary"]["revenue_excl_pb1"] == sum(
        o["revenue_excl_pb1"] for o in body["by_outlet"]
    )


def test_range_period_figures_and_drawer(client, ctx) -> None:
    riau, today = ctx["riau"], _today()
    yesterday = today - timedelta(days=1)
    params = {"outlet_id": riau, "period": "range", "from": str(yesterday), "to": str(today)}
    o2 = _get(client, ctx, SUMMARY, **params)
    assert o2["period"] == "range"
    assert (o2["from"], o2["to"]) == (str(yesterday), str(today))
    assert o2["kpis"]["orders"] == 114  # 109 today + 5 yesterday
    drawer = _get(client, ctx, **params)["summary"]
    assert drawer["orders"] == 114 and drawer["revenue_excl_pb1"] == 1140000
    # Non-range periods report their days too.
    plain = _get(client, ctx, SUMMARY, outlet_id=riau, period="week")
    assert plain["to"] == str(today)
    assert plain["from"] == str(today - timedelta(days=today.weekday()))


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"period": "range", "to": "2026-01-02"}, "from"),
        ({"period": "range", "from": "2026-01-02"}, "to"),
        ({"period": "range", "from": "2026-01-05", "to": "2026-01-02"}, "from"),
        ({"period": "range", "from": "2025-01-01", "to": "2025-06-30"}, "from"),
    ],
)
def test_range_validation(client, ctx, params, field) -> None:
    for url in (SUMMARY, URL):
        res = client.get(url, headers=ctx["owner"], params=params)
        assert res.status_code == 422, res.text
        assert res.json()["error"]["details"]["field"] == field


def test_range_cannot_end_after_today(client, ctx) -> None:
    tomorrow = _today() + timedelta(days=2)  # past today in every Indonesian zone
    params = {"period": "range", "from": str(_today()), "to": str(tomorrow)}
    for url in (SUMMARY, URL):
        res = client.get(url, headers=ctx["owner"], params=params)
        assert res.status_code == 422, res.text
        assert res.json()["error"]["details"]["field"] == "to"


def test_owner_only_and_bad_input(client, ctx) -> None:
    assert client.get(URL, headers=ctx["staff"]).status_code == 403
    for params in ({"hour": 24}, {"limit": 101}, {"method": "card"}, {"channel": "email"},
                   {"period": "decade"}):  # fmt: skip
        assert client.get(URL, headers=ctx["owner"], params=params).status_code == 422, params
    missing = "00000000-0000-0000-0000-000000000099"
    assert client.get(URL, headers=ctx["owner"], params={"outlet_id": missing}).status_code == 404
    res = client.get(URL, headers=ctx["owner"], params={"product_id": missing})
    assert res.status_code == 404
    # "year" is a drawer period (Item terlaris "Tahun ini"), not an O2 header period.
    assert client.get(SUMMARY, headers=ctx["owner"], params={"period": "year"}).status_code == 422
