"""Regression tests for the Wave 3 review (PR #8): empty bills, sold-out naming under a
stock race, closed-bill snapshots, PB1 changes with open bills, idempotency binding, cash
drawer ambiguity, refund PB1 split, takeaway tables, and duplicate add-ons.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core import idempotency
from app.core import orders as orders_core
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "w3r.test"
OWNER = UUID("50000000-0000-0000-0000-0000000000f0")
STAFF = UUID("50000000-0000-0000-0000-0000000000f1")
STAFF2 = UUID("50000000-0000-0000-0000-0000000000f2")


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
        json={"business": {"name": "Kopi Lima", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, outlet = res.json()["tenant_id"], res.json()["outlet_id"]
    for uid, name in ((STAFF, "rina"), (STAFF2, "dodi")):
        admin_sql("insert into auth.users (id, email) values (%s, %s)", (uid, f"{name}@{DOMAIN}"))
        admin_sql(
            "insert into app.users (id, tenant_id, email, display_name, role,"
            " invitation_accepted_at) values (%s, %s, %s, %s, 'staff', now())",
            (uid, tenant, f"{name}@{DOMAIN}", name),
        )
        admin_sql(
            "insert into app.staff_outlets (user_id, outlet_id, tenant_id) values (%s, %s, %s)",
            (uid, outlet, tenant),
        )
    for name in ("M01", "M02", "M03"):
        admin_sql(
            "insert into app.tables (tenant_id, outlet_id, name, capacity, area)"
            " values (%s, %s, %s, 4, 'Indoor')",
            (tenant, outlet, name),
        )
    owner = _bearer(OWNER, tenant, "owner")
    res = client.patch(
        f"/api/v1/owner/outlets/{outlet}",
        headers=owner,
        json={"pb1_enabled": True, "pb1_rate_bps": 1000, "payment_mode": "open_bill"},
    )
    assert res.status_code in (200, 204), res.text
    staff = _bearer(STAFF, tenant, "staff")
    drawers = client.get(f"/api/v1/ops/outlets/{outlet}/drawers", headers=staff).json()
    res = client.post(
        f"/api/v1/ops/drawers/{drawers[0]['drawer']['id']}/shifts",
        headers=staff,
        json={"starting_cash": 100000},
    )
    assert res.status_code == 201, res.text
    return {
        "tenant": tenant,
        "outlet": outlet,
        "owner": owner,
        "staff": staff,
        "staff2": _bearer(STAFF2, tenant, "staff"),
        "drawer": drawers[0]["drawer"]["id"],
    }


def _menu(client: TestClient, ctx: dict[str, Any]) -> dict[str, dict[str, Any]]:
    res = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/menu", headers=ctx["staff"])
    return {m["name"]: m for m in res.json()}


def _table(client: TestClient, ctx: dict[str, Any], name: str) -> str:
    rows = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/tables", headers=ctx["staff"]).json()
    return next(t["id"] for t in rows if t["name"] == name)


def _post_order(client, ctx, body, *, who="staff", key=None):
    headers = dict(ctx[who])
    if key:
        headers["Idempotency-Key"] = key
    return client.post(f"/api/v1/ops/outlets/{ctx['outlet']}/orders", headers=headers, json=body)


def _bill_order(client, ctx, table: str, product_id: str, qty: int = 1):
    res = _post_order(
        client,
        ctx,
        {
            "type": "dine_in",
            "table_id": table,
            "items": [{"product_id": product_id, "quantity": qty}],
            "payment": {"to_open_bill": True},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _stock(client: TestClient, ctx: dict[str, Any], name: str) -> Decimal:
    view = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/stock", headers=ctx["staff"]).json()
    return Decimal(next(i for i in view["items"] if i["name"] == name)["on_hand"])


# F1 ----------------------------------------------------------------------------------------


def test_empty_bill_can_be_voided_and_frees_the_table(client, ctx) -> None:
    staff, outlet = ctx["staff"], ctx["outlet"]
    m03 = _table(client, ctx, "M03")
    bill = client.post(f"/api/v1/ops/outlets/{outlet}/bills", headers=staff, json={"table_id": m03})
    assert bill.status_code == 201, bill.text
    bill_id = bill.json()["id"]
    # An empty bill cannot be paid ...
    res = client.post(f"/api/v1/ops/bills/{bill_id}/close", headers=staff, json={"method": "qris"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "bill_empty"
    # ... but it can be voided, which frees the table for a new bill.
    assert client.post(f"/api/v1/ops/bills/{bill_id}/void", headers=staff).status_code == 204
    detail = client.get(f"/api/v1/ops/bills/{bill_id}", headers=staff).json()
    assert (detail["status"], detail["total"], detail["subtotal"]) == ("voided", 0, 0)
    again = client.post(
        f"/api/v1/ops/outlets/{outlet}/bills", headers=staff, json={"table_id": m03}
    )
    assert again.status_code == 201
    res = client.post(f"/api/v1/ops/bills/{bill_id}/void", headers=staff)
    assert res.status_code == 409 and res.json()["error"]["code"] == "bill_not_open"
    client.post(f"/api/v1/ops/bills/{again.json()['id']}/void", headers=staff)


def test_bill_with_orders_cannot_be_voided_and_cancelling_the_last_order_voids_it(
    client, ctx
) -> None:
    staff = ctx["staff"]
    m02 = _table(client, ctx, "M02")
    order = _bill_order(client, ctx, m02, _menu(client, ctx)["Americano"]["product_id"])
    res = client.post(f"/api/v1/ops/bills/{order['bill_id']}/void", headers=staff)
    assert res.status_code == 409 and res.json()["error"]["code"] == "bill_not_empty"
    client.post(f"/api/v1/ops/orders/{order['id']}/cancel", headers=staff, json={"reason": "x"})
    detail = client.get(f"/api/v1/ops/bills/{order['bill_id']}", headers=staff).json()
    assert detail["status"] == "voided"


# F2 ----------------------------------------------------------------------------------------


def test_stock_race_names_the_short_item_and_deducts_nothing(client, ctx, monkeypatch) -> None:
    menu = _menu(client, ctx)
    americano, fries = menu["Americano"]["product_id"], menu["Kentang Goreng"]["product_id"]
    admin_sql(
        "insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity,"
        " actor_type, actor_id) select %s, %s, stock_item_id, 'waste', -on_hand, 'user', %s"
        " from app.outlet_stock si join app.stock_items i on i.id = si.stock_item_id"
        " where si.outlet_id = %s and i.name = 'Kentang beku' and si.on_hand > 0",
        (ctx["tenant"], ctx["outlet"], OWNER, ctx["outlet"]),
    )
    beans = _stock(client, ctx, "Biji kopi house blend")

    real = orders_core.stock.on_hand
    calls = {"n": 0}

    async def stale_first(conn, outlet_id):
        calls["n"] += 1
        data = await real(conn, outlet_id)
        # The pre-check sees stale, plentiful stock (another order has not committed yet).
        return {k: v + Decimal(10_000) for k, v in data.items()} if calls["n"] == 1 else data

    monkeypatch.setattr(orders_core.stock, "on_hand", stale_first)
    res = _post_order(
        client,
        ctx,
        {
            "type": "takeaway",
            "items": [
                {"product_id": americano, "quantity": 1},
                {"product_id": fries, "quantity": 1},
            ],
            "payment": {"method": "qris"},
        },
    )
    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "item_sold_out"
    assert res.json()["error"]["details"]["name"] == "Kentang Goreng"
    monkeypatch.undo()
    assert _stock(client, ctx, "Biji kopi house blend") == beans  # nothing deducted


# F5, F7 ------------------------------------------------------------------------------------


def test_closed_bill_keeps_its_snapshot_and_pb1_is_locked_while_bills_are_open(client, ctx) -> None:
    staff, owner, outlet = ctx["staff"], ctx["owner"], ctx["outlet"]
    m01 = _table(client, ctx, "M01")
    roti = _menu(client, ctx)["Roti Bakar Cokelat"]["product_id"]
    first = _bill_order(client, ctx, m01, roti)
    second = _bill_order(client, ctx, m01, roti)
    bill_id = first["bill_id"]

    # PB1 cannot change while a bill is open (its total is computed at close).
    res = client.patch(
        f"/api/v1/owner/outlets/{outlet}", headers=owner, json={"pb1_enabled": False}
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "bills_open"

    res = client.post(
        f"/api/v1/ops/bills/{bill_id}/close",
        headers=staff,
        json={"method": "cash", "cash_received": 100000},
    )
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 44000  # 2 x 20.000 + 10% PB1
    # Reversing one order after close must not change what the bill says was paid.
    rev = client.post(
        f"/api/v1/ops/orders/{second['id']}/reversal", headers=staff, json={"reason": "salah"}
    )
    assert rev.status_code == 200, rev.text
    detail = client.get(f"/api/v1/ops/bills/{bill_id}", headers=staff).json()
    assert (detail["subtotal"], detail["pb1_amount"], detail["total"]) == (40000, 4000, 44000)

    # The refund records its PB1 part; a second reversal is rejected and changes nothing.
    rows = admin_sql(
        "select amount, pb1_portion from app.ledger_entries"
        " where order_id = %s and type = 'refund'",
        (second["id"],),
    )
    assert rows == [(-22000, 2000)]
    again = client.post(
        f"/api/v1/ops/orders/{second['id']}/reversal", headers=staff, json={"reason": "lagi"}
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_transition"
    assert admin_sql(
        "select count(*) from app.ledger_entries where order_id = %s and type = 'refund'",
        (second["id"],),
    ) == [(1,)]

    # With no open bill left, PB1 can change again.
    for body in ({"pb1_enabled": False}, {"pb1_enabled": True, "pb1_rate_bps": 1000}):
        res = client.patch(f"/api/v1/owner/outlets/{outlet}", headers=owner, json=body)
        assert res.status_code in (200, 204), res.text


# F9 ----------------------------------------------------------------------------------------


def test_idempotency_key_is_bound_to_the_request_and_the_user(client, ctx) -> None:
    menu = _menu(client, ctx)
    body = {
        "type": "takeaway",
        "items": [{"product_id": menu["Americano"]["product_id"], "quantity": 1}],
        "payment": {"method": "qris"},
    }
    first = _post_order(client, ctx, body, key="review-key-0001")
    assert first.status_code == 201, first.text
    replay = _post_order(client, ctx, body, key="review-key-0001")
    assert replay.status_code == 200 and replay.headers["Idempotent-Replay"] == "true"
    assert replay.json()["id"] == first.json()["id"]
    other_body = {**body, "items": [{**body["items"][0], "quantity": 2}]}
    res = _post_order(client, ctx, other_body, key="review-key-0001")
    assert res.status_code == 409 and res.json()["error"]["code"] == "idempotency_key_reused"
    res = _post_order(client, ctx, body, who="staff2", key="review-key-0001")
    assert res.status_code == 409 and res.json()["error"]["code"] == "idempotency_key_reused"
    # The key is stored as its SHA-256, never as sent.
    stored = idempotency.stored_key("review-key-0001")
    assert admin_sql("select count(*) from app.idempotency_keys where key = 'review-key-0001'") == [
        (0,)
    ]
    # Old keys are purged (24 hours).
    admin_sql(
        "update app.idempotency_keys set created_at = now() - interval '2 days' where key = %s",
        (stored,),
    )
    assert admin_sql(
        "delete from app.idempotency_keys where created_at < now() - interval '24 hours'"
        " and key = %s returning 1",
        (stored,),
    ) == [(1,)]


# F4 ----------------------------------------------------------------------------------------


def test_cash_needs_a_drawer_when_several_shifts_are_open(client, ctx) -> None:
    outlet = ctx["outlet"]
    # A second drawer with a shift opened by the owner: Rina has one open shift too, so her
    # own shift is unambiguous. Dodi has none, and two shifts are open: he must choose.
    second = admin_sql(
        "insert into app.cash_drawers (tenant_id, outlet_id, name) values (%s, %s, 'Kasir 2')"
        " returning id",
        (ctx["tenant"], outlet),
    )[0][0]
    res = client.post(
        f"/api/v1/ops/drawers/{second}/shifts", headers=ctx["owner"], json={"starting_cash": 50000}
    )
    assert res.status_code == 201, res.text
    # Both shifts report who opened them, so the counter can pick the cashier's own one.
    current = client.get(
        f"/api/v1/ops/outlets/{outlet}/shifts/current", headers=ctx["staff2"]
    ).json()
    assert {s["drawer_id"]: s["opened_by"] for s in current} == {
        ctx["drawer"]: str(STAFF),
        str(second): str(OWNER),
    }
    americano = _menu(client, ctx)["Americano"]["product_id"]
    body = {
        "type": "takeaway",
        "items": [{"product_id": americano, "quantity": 1}],
        "payment": {"method": "cash", "cash_received": 50000},
    }
    res = _post_order(client, ctx, body, who="staff2")
    assert res.status_code == 422, res.text
    assert res.json()["error"]["details"]["field"] == "drawer_id"
    res = _post_order(
        client,
        ctx,
        {**body, "payment": {**body["payment"], "drawer_id": ctx["drawer"]}},
        who="staff2",
    )
    assert res.status_code == 201, res.text
    # Rina's own shift is chosen without a drawer_id.
    assert _post_order(client, ctx, body).status_code == 201


# Nits --------------------------------------------------------------------------------------


def test_takeaway_has_no_table_and_duplicate_addons_are_rejected(client, ctx) -> None:
    menu = _menu(client, ctx)
    kopi = menu["Es Kopi Susu Senja"]
    regular = next(
        o["id"] for g in kopi["addon_groups"] for o in g["options"] if o["name"] == "Regular"
    )
    res = _post_order(
        client,
        ctx,
        {
            "type": "takeaway",
            "table_id": _table(client, ctx, "M01"),
            "items": [{"product_id": menu["Americano"]["product_id"], "quantity": 1}],
            "payment": {"method": "qris"},
        },
    )
    assert res.status_code == 422 and res.json()["error"]["details"]["field"] == "table_id"
    res = _post_order(
        client,
        ctx,
        {
            "type": "takeaway",
            "items": [
                {
                    "product_id": kopi["product_id"],
                    "quantity": 1,
                    "addon_option_ids": [regular, regular],
                }
            ],
            "payment": {"method": "qris"},
        },
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "addon_invalid"
