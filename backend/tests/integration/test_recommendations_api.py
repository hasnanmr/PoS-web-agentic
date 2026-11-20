"""O7 "Rekomendasi" (T-073) against Postgres through RLS: owner's picks (order, replace),
tags, and the per-outlet preview (picks first, best sellers of 30 days, sold-out and
duplicates left out, owner only, tenant isolated).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "o7reco.test"
OWNER = UUID("50000000-0000-0000-0000-0000000007f0")
STAFF = UUID("50000000-0000-0000-0000-0000000007f1")
BASE = "/api/v1/owner"


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
        f"{BASE}/onboarding",
        headers=_bearer(OWNER, None, "owner_pending"),
        json={"business": {"name": "Kopi Reko", "type": "cafe"}, "outlet": {"name": "Dago"}},
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
    products = {
        n: str(i)
        for i, n in admin_sql("select id, name from app.products where tenant_id = %s", (tenant,))
    }
    return {
        "tenant": tenant,
        "outlet": outlet,
        "owner": _bearer(OWNER, tenant, "owner"),
        "staff": _bearer(STAFF, tenant, "staff"),
        "p": products,
    }


def _sell(ctx: dict[str, Any], name: str, quantity: int, *, payment: str = "paid") -> None:
    """One order of `name` written directly; `payment` other than paid is not a sale."""
    number = admin_sql(
        "select coalesce(max(order_no), 1000) + 1 from app.orders where outlet_id = %s",
        (ctx["outlet"],),
    )[0][0]
    status = "completed" if payment == "paid" else "pending_payment"
    order = admin_sql(
        "insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode,"
        " status, payment_status, subtotal, total, created_by_actor, created_by_id)"
        " values (%s, %s, %s, 'counter', 'takeaway', 'pay_first', %s, %s, %s, %s, 'user', %s)"
        " returning id",
        (
            ctx["tenant"],
            ctx["outlet"],
            number,
            status,
            payment,
            10000 * quantity,
            10000 * quantity,
            STAFF,
        ),
    )[0][0]
    admin_sql(
        "insert into app.order_items (tenant_id, outlet_id, order_id, product_id, name,"
        " unit_price, quantity, line_total) values (%s, %s, %s, %s, %s, 10000, %s, %s)",
        (ctx["tenant"], ctx["outlet"], order, ctx["p"][name], name, quantity, 10000 * quantity),
    )


def _preview(client: TestClient, ctx: dict[str, Any]) -> dict[str, Any]:
    res = client.get(f"{BASE}/outlets/{ctx['outlet']}/recommendation-preview", headers=ctx["owner"])
    assert res.status_code == 200, res.text
    return res.json()


def test_sample_picks_in_order_with_tags_and_tag_list(client, ctx) -> None:
    picks = client.get(f"{BASE}/owner-picks", headers=ctx["owner"]).json()
    assert [p["name"] for p in picks] == [
        "Es Kopi Susu Senja",
        "Matcha Latte",
        "Roti Bakar Cokelat",
    ]
    assert picks[0]["tags"] == ["coffee", "sweet"]
    assert picks[0]["product_id"] == ctx["p"]["Es Kopi Susu Senja"]
    assert client.get(f"{BASE}/tags", headers=ctx["owner"]).json() == ["coffee", "sharing", "sweet"]


def test_put_replaces_the_list_and_keeps_the_order(client, ctx) -> None:
    p = ctx["p"]
    ids = [p["Kentang Goreng"], p["Es Kopi Susu Senja"], p["Americano"]]
    res = client.put(f"{BASE}/owner-picks", headers=ctx["owner"], json={"product_ids": ids})
    assert res.status_code == 204, res.text
    got = client.get(f"{BASE}/owner-picks", headers=ctx["owner"]).json()
    assert [r["product_id"] for r in got] == ids
    # Products that were dropped are no longer picks on the O5 list either.
    rows = client.get(f"{BASE}/products", headers=ctx["owner"]).json()
    assert {r["name"] for r in rows if r["is_owner_pick"]} == {
        "Kentang Goreng",
        "Es Kopi Susu Senja",
        "Americano",
    }
    audit = admin_sql(
        "select count(*) from app.audit_events where tenant_id = %s"
        " and action = 'owner_picks.updated'",
        (ctx["tenant"],),
    )[0][0]
    assert audit == 1
    # Saving the same list again changes nothing and writes no second audit event.
    client.put(f"{BASE}/owner-picks", headers=ctx["owner"], json={"product_ids": ids})
    assert (
        admin_sql(
            "select count(*) from app.audit_events where tenant_id = %s"
            " and action = 'owner_picks.updated'",
            (ctx["tenant"],),
        )[0][0]
        == 1
    )


def test_put_validation(client, ctx) -> None:
    p = ctx["p"]
    url = f"{BASE}/owner-picks"
    twice = [p["Americano"], p["Americano"]]
    assert client.put(url, headers=ctx["owner"], json={"product_ids": twice}).status_code == 422
    unknown = {"product_ids": [str(uuid4())]}
    assert client.put(url, headers=ctx["owner"], json=unknown).status_code == 422
    too_many = {"product_ids": [str(uuid4()) for _ in range(31)]}
    assert client.put(url, headers=ctx["owner"], json=too_many).status_code == 422
    # Nothing was saved by the failed calls; an empty list clears every pick.
    assert len(client.get(url, headers=ctx["owner"]).json()) == 3
    assert client.put(url, headers=ctx["owner"], json={"product_ids": []}).status_code == 204
    assert client.get(url, headers=ctx["owner"]).json() == []


def test_preview_picks_then_best_sellers_without_duplicates(client, ctx) -> None:
    p = ctx["p"]
    ids = [p["Es Kopi Susu Senja"], p["Matcha Latte"]]
    client.put(f"{BASE}/owner-picks", headers=ctx["owner"], json={"product_ids": ids})
    _sell(ctx, "Americano", 3)
    _sell(ctx, "Americano", 2)
    _sell(ctx, "Croissant Butter", 4)
    _sell(ctx, "Es Kopi Susu Senja", 9)  # a pick that also sells: listed once, as a pick
    _sell(ctx, "Kentang Goreng", 50, payment="unpaid")  # not a sale

    body = _preview(client, ctx)
    assert [(i["name"], i["position"], i["skipped_reason"]) for i in body["picks"]] == [
        ("Es Kopi Susu Senja", 1, None),
        ("Matcha Latte", 2, None),
    ]
    assert [
        (i["name"], i["units_30d"], i["position"], i["skipped_reason"])
        for i in body["best_sellers"]
    ] == [
        ("Es Kopi Susu Senja", 9, None, "duplicate"),
        ("Americano", 5, 3, None),
        ("Croissant Butter", 4, 4, None),
    ]
    assert body["listed_count"] == 4 and body["max_items"] == 30


def test_preview_skips_sold_out_and_unavailable_items(client, ctx) -> None:
    p = ctx["p"]
    ids = [p["Matcha Latte"], p["Roti Bakar Cokelat"], p["Es Kopi Susu Senja"]]
    client.put(f"{BASE}/owner-picks", headers=ctx["owner"], json={"product_ids": ids})
    # Matcha: out of matcha powder → sold out. Roti Bakar: hidden at this outlet.
    stock = client.get(
        f"{BASE.replace('owner', 'ops')}/outlets/{ctx['outlet']}/stock", headers=ctx["staff"]
    ).json()
    matcha = next(i for i in stock["items"] if i["name"] == "Bubuk matcha")
    res = client.post(
        f"/api/v1/ops/outlets/{ctx['outlet']}/stock-movements",
        headers=ctx["staff"],
        json={
            "type": "waste",
            "stock_item_id": matcha["stock_item_id"],
            "quantity": "500",
            "note": "tumpah",
        },
    )
    assert res.status_code == 201, res.text
    admin_sql(
        "update app.outlet_prices set is_available = false"
        " where outlet_id = %s and product_id = %s",
        (ctx["outlet"], p["Roti Bakar Cokelat"]),
    )
    _sell(ctx, "Matcha Latte", 20)  # best seller too, but sold out → still left out

    body = _preview(client, ctx)
    assert [(i["name"], i["position"], i["skipped_reason"]) for i in body["picks"]] == [
        ("Matcha Latte", None, "sold_out"),
        ("Roti Bakar Cokelat", None, "unavailable"),
        ("Es Kopi Susu Senja", 1, None),
    ]
    sellers = {i["name"]: i for i in body["best_sellers"]}
    assert sellers["Matcha Latte"]["skipped_reason"] == "sold_out"
    assert sellers["Matcha Latte"]["position"] is None


def test_preview_is_capped_at_30_items(client, ctx) -> None:
    tenant, outlet = ctx["tenant"], ctx["outlet"]
    for i in range(30):
        admin_sql(
            "insert into app.products (tenant_id, name, is_active) values (%s, %s, true)",
            (tenant, f"Bulk {i:02d}"),
        )
    # Each one uses a cup from stock, so none is sold out; and each has an outlet price.
    admin_sql(
        "insert into app.outlet_prices (tenant_id, outlet_id, product_id, price)"
        " select %s, %s, id, 10000 from app.products where tenant_id = %s and name like 'Bulk %%'",
        (tenant, outlet, tenant),
    )
    admin_sql(
        "insert into app.recipe_items (tenant_id, product_id, stock_item_id, quantity)"
        " select %s, p.id, s.id, 1 from app.products p, app.stock_items s"
        " where p.tenant_id = %s and p.name like 'Bulk %%' and s.tenant_id = p.tenant_id"
        " and s.name = 'Cup 16oz'",
        (tenant, tenant),
    )
    bulk = [
        str(r[0])
        for r in admin_sql(
            "select id from app.products where tenant_id = %s and name like 'Bulk %%'"
            " order by name",
            (tenant,),
        )
    ]
    res = client.put(f"{BASE}/owner-picks", headers=ctx["owner"], json={"product_ids": bulk})
    assert res.status_code == 204, res.text
    _sell(ctx, "Americano", 5)
    body = _preview(client, ctx)
    assert [i["position"] for i in body["picks"]] == list(range(1, 31))
    # The list is full: the best seller does not fit.
    assert body["best_sellers"] == [] and body["listed_count"] == 30


def test_owner_only_and_tenant_isolated(client, ctx) -> None:
    for url in (
        f"{BASE}/owner-picks",
        f"{BASE}/tags",
        f"{BASE}/outlets/{ctx['outlet']}/recommendation-preview",
    ):
        assert client.get(url, headers=ctx["staff"]).status_code == 403
        assert client.get(url).status_code == 401
    assert (
        client.put(
            f"{BASE}/owner-picks", headers=ctx["staff"], json={"product_ids": []}
        ).status_code
        == 403
    )
    missing = f"{BASE}/outlets/{uuid4()}/recommendation-preview"
    assert client.get(missing, headers=ctx["owner"]).status_code == 404
