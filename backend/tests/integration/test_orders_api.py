"""Wave 3 API tests (T-025 to T-033, T-038, T-039 open, T-041 sale/refund posting) against
Postgres through RLS: counter orders with stock deduction, PB1, cash/QRIS payment and
ledger, idempotency, sold out, status machine, cancel, reversal, and open bills.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "w3.test"
OWNER = UUID("40000000-0000-0000-0000-0000000000f0")
STAFF = UUID("40000000-0000-0000-0000-0000000000f1")


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
        json={"business": {"name": "Kopi Tiga", "type": "cafe"}, "outlet": {"name": "Dago"}},
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
    for name in ("M01", "M02"):
        admin_sql(
            "insert into app.tables (tenant_id, outlet_id, name, capacity, area)"
            " values (%s, %s, %s, 4, 'Indoor')",
            (tenant, outlet, name),
        )
    owner = _bearer(OWNER, tenant, "owner")
    # PB1 10% for the tests (sample outlets start with PB1 off).
    client.patch(
        f"/api/v1/owner/outlets/{outlet}",
        headers=owner,
        json={"pb1_enabled": True, "pb1_rate_bps": 1000},
    )
    return {
        "tenant": tenant,
        "outlet": outlet,
        "owner": owner,
        "staff": _bearer(STAFF, tenant, "staff"),
    }


def _menu(client: TestClient, ctx: dict[str, Any]) -> dict[str, dict[str, Any]]:
    res = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/menu", headers=ctx["staff"])
    return {m["name"]: m for m in res.json()}


def _option(item: dict[str, Any], name: str) -> str:
    return next(o["id"] for g in item["addon_groups"] for o in g["options"] if o["name"] == name)


def _stock(client: TestClient, ctx: dict[str, Any], name: str) -> Decimal:
    view = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/stock", headers=ctx["staff"]).json()
    return Decimal(next(i for i in view["items"] if i["name"] == name)["on_hand"])


def _order(client: TestClient, ctx: dict[str, Any], body: dict[str, Any], key: str | None = None):
    headers = dict(ctx["staff"])
    if key:
        headers["Idempotency-Key"] = key
    return client.post(f"/api/v1/ops/outlets/{ctx['outlet']}/orders", headers=headers, json=body)


def _ledger(order_id: str) -> list[tuple[str, int, str | None]]:
    return admin_sql(
        "select type::text, amount, payment_method::text from app.ledger_entries"
        " where order_id = %s order by id",
        (order_id,),
    )


def test_quote_requires_addons_and_applies_pb1(client, ctx) -> None:
    menu = _menu(client, ctx)
    kopi = menu["Es Kopi Susu Senja"]
    url = f"/api/v1/ops/outlets/{ctx['outlet']}/quotes"
    res = client.post(
        url,
        headers=ctx["staff"],
        json={"items": [{"product_id": kopi["product_id"], "quantity": 1}]},
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "addon_required"
    res = client.post(
        url,
        headers=ctx["staff"],
        json={
            "items": [
                {
                    "product_id": kopi["product_id"],
                    "quantity": 2,
                    "addon_option_ids": [
                        _option(kopi, "Regular"),
                        _option(kopi, "Oat milk"),
                        _option(kopi, "Less sugar"),
                    ],
                }
            ]
        },
    )
    body = res.json()
    assert (body["subtotal"], body["pb1_rate_bps"], body["pb1_amount"], body["total"]) == (
        60000,
        1000,
        6000,
        66000,
    )
    res = client.post(
        url,
        headers=ctx["staff"],
        json={
            "items": [
                {
                    "product_id": kopi["product_id"],
                    "quantity": 1,
                    "addon_option_ids": [_option(kopi, "Regular"), _option(kopi, "Large")],
                }
            ]
        },
    )
    assert res.json()["error"]["code"] == "addon_invalid"  # single choice


def test_cash_needs_open_shift_then_pays_with_change_and_ledger(client, ctx) -> None:
    menu = _menu(client, ctx)
    body = {
        "type": "takeaway",
        "items": [
            {"product_id": menu["Americano"]["product_id"], "quantity": 1},
            {"product_id": menu["Roti Bakar Cokelat"]["product_id"], "quantity": 1},
        ],
        "payment": {"method": "cash", "cash_received": 50000},
    }
    res = _order(client, ctx, body)
    assert res.status_code == 409 and res.json()["error"]["code"] == "shift_not_open"

    drawers = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/drawers", headers=ctx["staff"]
    ).json()
    res = client.post(
        f"/api/v1/ops/drawers/{drawers[0]['drawer']['id']}/shifts",
        headers=ctx["staff"],
        json={"starting_cash": 500000},
    )
    assert res.status_code == 201
    current = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/shifts/current", headers=ctx["staff"]
    ).json()
    assert current[0]["drawer_name"] == "Kasir depan" and current[0]["drawer_number"] == 1

    short = _order(client, ctx, {**body, "payment": {"method": "cash", "cash_received": 40000}})
    assert short.json()["error"]["code"] == "cash_insufficient"

    beans_before = _stock(client, ctx, "Biji kopi house blend")
    res = _order(client, ctx, body, key="counter-test-0001")
    assert res.status_code == 201, res.text
    order = res.json()
    # 22.000 + 20.000 = 42.000; PB1 4.200; total 46.200; change 3.800 (S2 #A-1039).
    assert (order["order_no"], order["total"], order["change_due"], order["payment_status"]) == (
        "#A-1001",
        46200,
        3800,
        "paid",
    )
    assert _ledger(order["id"]) == [("revenue", 42000, "cash"), ("pb1", 4200, "cash")]
    assert _stock(client, ctx, "Biji kopi house blend") == beans_before - 18

    # Same Idempotency-Key: same order back, nothing charged or deducted twice.
    again = _order(client, ctx, body, key="counter-test-0001")
    assert again.json()["id"] == order["id"]
    assert _stock(client, ctx, "Biji kopi house blend") == beans_before - 18
    drawers = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/drawers", headers=ctx["staff"]
    ).json()
    assert drawers[0]["shift"]["cash_in"] == 46200 and drawers[0]["shift"]["cash_in_count"] == 1


def test_status_machine_board_and_events(client, ctx) -> None:
    menu = _menu(client, ctx)
    order = _order(
        client,
        ctx,
        {
            "type": "takeaway",
            "items": [{"product_id": menu["Americano"]["product_id"], "quantity": 1}],
            "payment": {"method": "qris"},
        },
    ).json()
    assert _ledger(order["id"]) == [("revenue", 22000, "qris"), ("pb1", 2200, "qris")]
    board = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/orders/board", headers=ctx["staff"]
    ).json()
    card = next(c for c in board["confirmed"] if c["id"] == order["id"])
    assert card["allowed_actions"] == ["preparing", "reversal"]
    assert card["item_summary"] == "1× Americano" and card["payment_method"] == "qris"  # noqa: RUF001

    url = f"/api/v1/ops/orders/{order['id']}/transitions"
    bad = client.post(url, headers=ctx["staff"], json={"to_status": "completed"})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "invalid_transition"
    for to in ("preparing", "ready", "completed"):
        res = client.post(url, headers=ctx["staff"], json={"to_status": to})
        assert res.status_code == 200, res.text
    detail = res.json()
    assert detail["status"] == "completed" and detail["allowed_actions"] == ["reversal"]
    assert [(e["kind"], e["to"], e["actor"]["name"]) for e in detail["events"]][-3:] == [
        ("status_changed", "preparing", "Rina"),
        ("status_changed", "ready", "Rina"),
        ("status_changed", "completed", "Rina"),
    ]
    board = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/orders/board?q={order['order_no']}",
        headers=ctx["staff"],
    ).json()
    assert [c["id"] for c in board["done_today"]] == [order["id"]]


def test_sold_out_names_the_item_and_changes_nothing(client, ctx) -> None:
    menu = _menu(client, ctx)
    croissant = menu["Croissant Butter"]["product_id"]
    before = _stock(client, ctx, "Croissant (frozen)")
    res = _order(
        client,
        ctx,
        {
            "type": "takeaway",
            "items": [{"product_id": croissant, "quantity": int(before) + 1}],
            "payment": {"method": "qris"},
        },
    )
    assert res.status_code == 409
    assert res.json()["error"] == {
        "code": "item_sold_out",
        "message": "Croissant Butter habis",
        "details": {"product_id": croissant, "name": "Croissant Butter"},
    }
    assert _stock(client, ctx, "Croissant (frozen)") == before
    # Take the last ones, then the item shows sold out on the counter menu.
    assert (
        _order(
            client,
            ctx,
            {
                "type": "takeaway",
                "items": [{"product_id": croissant, "quantity": int(before)}],
                "payment": {"method": "qris"},
            },
        ).status_code
        == 201
    )
    item = _menu(client, ctx)["Croissant Butter"]
    assert item["sold_out"] is True and item["sold_out_reason"] == "Bahan tidak cukup"


def test_reversal_requires_reason_posts_refund_and_records_waste(client, ctx) -> None:
    menu = _menu(client, ctx)
    order = _order(
        client,
        ctx,
        {
            "type": "takeaway",
            "items": [{"product_id": menu["Matcha Latte"]["product_id"], "quantity": 1}],
            "payment": {"method": "cash", "cash_received": 30800},
        },
    ).json()
    url = f"/api/v1/ops/orders/{order['id']}"
    client.post(f"{url}/transitions", headers=ctx["staff"], json={"to_status": "preparing"})
    matcha = _stock(client, ctx, "Bubuk matcha")
    assert client.post(f"{url}/cancel", headers=ctx["staff"], json={}).status_code == 409
    res = client.post(f"{url}/reversal", headers=ctx["staff"], json={"reason": "  "})
    assert res.status_code == 422 and res.json()["error"]["code"] == "reason_required"
    res = client.post(f"{url}/reversal", headers=ctx["staff"], json={"reason": "salah input"})
    assert res.status_code == 200, res.text
    detail = res.json()
    assert (detail["status"], detail["payment_status"], detail["refund"]) == (
        "cancelled",
        "refunded",
        {"amount": 30800, "method": "cash"},
    )
    assert _ledger(order["id"])[-1] == ("refund", -30800, "cash")
    assert _stock(client, ctx, "Bubuk matcha") == matcha  # prepared: kept out as waste
    kinds = admin_sql(
        "select type::text from app.stock_movements where order_id = %s order by id", (order["id"],)
    )
    assert [k[0] for k in kinds][-2:] == ["sale_reversal", "waste"]
    assert detail["events"][-1]["reason"] == "salah input"


def test_open_bill_flow(client, ctx) -> None:
    owner, staff, outlet = ctx["owner"], ctx["staff"], ctx["outlet"]
    client.patch(
        f"/api/v1/owner/outlets/{outlet}", headers=owner, json={"payment_mode": "open_bill"}
    )
    tables = client.get(f"/api/v1/ops/outlets/{outlet}/tables", headers=staff).json()
    m01 = next(t for t in tables if t["name"] == "M01")
    menu = _menu(client, ctx)
    americano = menu["Americano"]["product_id"]
    roti = menu["Roti Bakar Cokelat"]["product_id"]

    paid_now = _order(
        client,
        ctx,
        {
            "type": "dine_in",
            "table_id": m01["id"],
            "items": [{"product_id": americano, "quantity": 1}],
            "payment": {"method": "qris"},
        },
    )
    assert paid_now.status_code == 422  # dine-in at an open-bill outlet goes to the bill

    first = _order(
        client,
        ctx,
        {
            "type": "dine_in",
            "table_id": m01["id"],
            "items": [{"product_id": americano, "quantity": 2}],
            "payment": {"to_open_bill": True},
        },
    ).json()
    second = _order(
        client,
        ctx,
        {
            "type": "dine_in",
            "table_id": m01["id"],
            "items": [{"product_id": roti, "quantity": 1}],
            "payment": {"to_open_bill": True},
        },
    ).json()
    third = _order(
        client,
        ctx,
        {
            "type": "dine_in",
            "table_id": m01["id"],
            "items": [{"product_id": roti, "quantity": 1}],
            "payment": {"to_open_bill": True},
        },
    ).json()
    assert first["bill_id"] == second["bill_id"] == third["bill_id"]
    assert first["payment_status"] == "unpaid" and _ledger(first["id"]) == []

    # Open-bill orders can be prepared before payment; served, not completed.
    url = f"/api/v1/ops/orders/{first['id']}/transitions"
    for to in ("preparing", "ready", "served"):
        assert client.post(url, headers=staff, json={"to_status": to}).status_code == 200
    detail = client.get(f"/api/v1/ops/orders/{first['id']}", headers=staff).json()
    assert detail["allowed_actions"] == ["cancel"]

    roti_stock = _stock(client, ctx, "Roti tawar")
    client.post(f"/api/v1/ops/orders/{third['id']}/cancel", headers=staff, json={"reason": "batal"})
    assert _stock(client, ctx, "Roti tawar") == roti_stock + 2

    bills = client.get(f"/api/v1/ops/outlets/{outlet}/bills", headers=staff).json()
    assert bills["payment_mode"] == "open_bill"
    card = next(b for b in bills["bills"] if b["id"] == first["bill_id"])
    # 44.000 + 20.000 = 64.000 + PB1 6.400 (once on the bill subtotal).
    assert (card["table_name"], card["order_count"], card["running_total"]) == ("M01", 2, 70400)
    tables = client.get(f"/api/v1/ops/outlets/{outlet}/tables", headers=staff).json()
    assert next(t for t in tables if t["name"] == "M01")["open_bill"]["total"] == 70400
    dup = client.post(
        f"/api/v1/ops/outlets/{outlet}/bills", headers=staff, json={"table_id": m01["id"]}
    )
    assert dup.status_code == 409

    res = client.post(
        f"/api/v1/ops/bills/{first['bill_id']}/close",
        headers={**staff, "Idempotency-Key": "bill-close-0001"},
        json={"method": "cash", "cash_received": 100000},
    )
    assert res.status_code == 200, res.text
    assert (res.json()["total"], res.json()["change_due"], res.json()["orders_completed"]) == (
        70400,
        29600,
        2,
    )
    for oid in (first["id"], second["id"]):
        d = client.get(f"/api/v1/ops/orders/{oid}", headers=staff).json()
        assert (d["status"], d["payment_status"], d["payment_method"]) == (
            "completed",
            "paid",
            "cash",
        )
    ledger = admin_sql(
        "select type::text, amount from app.ledger_entries where bill_id = %s order by id",
        (first["bill_id"],),
    )
    assert ledger == [("revenue", 64000), ("pb1", 6400)]
    again = client.post(
        f"/api/v1/ops/bills/{first['bill_id']}/close",
        headers={**staff, "Idempotency-Key": "bill-close-0001"},
        json={"method": "cash", "cash_received": 100000},
    )
    assert again.json()["total"] == 70400  # stored response, not a second payment

    guest = client.post(
        f"/api/v1/ops/outlets/{outlet}/bills", headers=staff, json={"guest_name": "Pak Joko"}
    )
    assert guest.status_code == 201 and guest.json()["guest_name"] == "Pak Joko"
