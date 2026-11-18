"""O2 "Item terlaris" (T-071) against Postgres through RLS: top 5 by quantity sold, paid
orders only, outlet-local day / month / year, owner only.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
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

DOMAIN = "o2top.test"
OWNER = UUID("50000000-0000-0000-0000-0000000002f0")
STAFF = UUID("50000000-0000-0000-0000-0000000002f1")
URL = "/api/v1/owner/dashboard/top-items"


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
        json={"business": {"name": "Kopi Top", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, outlet = res.json()["tenant_id"], res.json()["outlet_id"]
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
    products = admin_sql(
        "select id, name from app.products where tenant_id = %s order by name limit 6", (tenant,)
    )
    assert len(products) == 6
    return {
        "tenant": tenant,
        "outlet": outlet,
        "owner": _bearer(OWNER, tenant, "owner"),
        "staff": _bearer(STAFF, tenant, "staff"),
        "products": [(str(p), n) for p, n in products],
    }


def _order(
    ctx: dict[str, Any],
    lines: list[tuple[int, int, int]],
    *,
    status: str = "completed",
    payment: str = "paid",
    created_at: str = "now()",
) -> None:
    """One counter order with (product index, quantity, line_total) lines, written directly."""
    subtotal = sum(total for _, _, total in lines)
    number = admin_sql(
        "select coalesce(max(order_no), 1000) + 1 from app.orders where outlet_id = %s",
        (ctx["outlet"],),
    )[0][0]
    order = admin_sql(
        "insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode,"
        " status, payment_status, subtotal, total, created_by_actor, created_by_id, created_at)"
        " values (%s, %s, %s, 'counter', 'takeaway', 'pay_first', %s, %s, %s, %s, 'user', %s,"
        f" {created_at}) returning id",
        (ctx["tenant"], ctx["outlet"], number, status, payment, subtotal, subtotal, STAFF),
    )[0][0]
    for idx, qty, total in lines:
        product, name = ctx["products"][idx]
        admin_sql(
            "insert into app.order_items (tenant_id, outlet_id, order_id, product_id, name,"
            " unit_price, quantity, line_total) values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (ctx["tenant"], ctx["outlet"], order, product, name, total // qty, qty, total),
        )


def test_top_items_today_paid_only_sorted_and_capped(client, ctx) -> None:
    names = [n for _, n in ctx["products"]]
    _order(ctx, [(0, 3, 75000), (1, 2, 52000)])
    _order(ctx, [(0, 1, 30000), (2, 2, 40000), (3, 1, 20000)])  # 2 vs 2: higher revenue first
    _order(ctx, [(4, 1, 18000), (5, 1, 15000)])
    # Not sales: unpaid, proof waiting, cancelled, and reversed (refunded) orders.
    _order(ctx, [(5, 9, 90000)], status="pending_payment", payment="unpaid")
    _order(ctx, [(5, 9, 90000)], status="pending_payment", payment="proof_submitted")
    _order(ctx, [(5, 9, 90000)], status="cancelled", payment="unpaid")
    _order(ctx, [(5, 9, 90000)], status="cancelled", payment="refunded")

    res = client.get(URL, headers=ctx["owner"], params={"outlet_id": ctx["outlet"]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["period"] == "day"
    assert body["top_items"] == [
        {"name": names[0], "quantity_sold": 4, "revenue": 105000},
        {"name": names[1], "quantity_sold": 2, "revenue": 52000},
        {"name": names[2], "quantity_sold": 2, "revenue": 40000},
        {"name": names[3], "quantity_sold": 1, "revenue": 20000},
        {"name": names[4], "quantity_sold": 1, "revenue": 18000},
    ]
    # All outlets gives the same (one outlet).
    assert client.get(URL, headers=ctx["owner"]).json()["top_items"] == body["top_items"]


def test_top_items_period_is_outlet_local(client, ctx) -> None:
    """An order just before the outlet-local midnight counts for this month and year only
    (unless today is the 1st, or 1 January)."""
    yesterday = (
        "(date_trunc('day', now() at time zone 'Asia/Jakarta') at time zone 'Asia/Jakarta')"
        " - interval '1 second'"
    )
    _order(ctx, [(5, 50, 500000)], created_at=yesterday)
    today = datetime.now(ZoneInfo("Asia/Jakarta")).date()

    def first(period: str) -> dict[str, Any]:
        res = client.get(URL, headers=ctx["owner"], params={"period": period})
        assert res.status_code == 200, res.text
        return res.json()["top_items"][0]

    # Product 5 sold 1 today (first test) and 50 just before midnight.
    big = {"name": ctx["products"][5][1], "quantity_sold": 51, "revenue": 515000}
    assert first("day") != big
    assert (first("month") == big) is (today.day != 1)
    assert (first("year") == big) is (today.timetuple().tm_yday != 1)


def test_top_items_empty_rejects_bad_period_and_staff(client, ctx) -> None:
    res = client.get(URL, headers=ctx["owner"], params={"period": "week"})
    assert res.status_code == 422, res.text
    assert client.get(URL, headers=ctx["staff"]).status_code == 403
    other = "00000000-0000-0000-0000-000000000099"
    assert client.get(URL, headers=ctx["owner"], params={"outlet_id": other}).status_code == 404


def test_top_items_empty_list_and_tenant_isolation(client, ctx) -> None:
    """A new business sees no items, although the first tenant has sales today."""
    owner, domain = UUID("50000000-0000-0000-0000-0000000002f2"), "o2empty.test"
    cleanup_domain(domain)
    invite_owner(owner, f"owner@{domain}")
    try:
        res = client.post(
            "/api/v1/owner/onboarding",
            headers=_bearer(owner, None, "owner_pending"),
            json={"business": {"name": "Kosong", "type": "cafe"}, "outlet": {"name": "Riau"}},
        )
        assert res.status_code == 201, res.text
        headers = _bearer(owner, res.json()["tenant_id"], "owner")
        body = client.get(URL, headers=headers, params={"period": "year"}).json()
        assert body == {"period": "year", "top_items": []}
    finally:
        cleanup_domain(domain)
