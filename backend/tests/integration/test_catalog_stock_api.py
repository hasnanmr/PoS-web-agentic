"""Wave 2 API tests (T-016 to T-024) against Postgres through RLS as app_backend:
sample menu at onboarding, products and prices (O5), add-on groups, recipes and
availability (O6), thresholds, and stock movements with sold-out recovery (S7).
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

DOMAIN = "w2.test"
OWNER = UUID("30000000-0000-0000-0000-0000000000f0")
STAFF = UUID("30000000-0000-0000-0000-0000000000f1")


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
    token = make_token(sub=str(OWNER), tenant_id=None, app_role="owner_pending")
    pending = {"Authorization": f"Bearer {token}"}
    res = client.post(
        "/api/v1/owner/onboarding",
        headers=pending,
        json={"business": {"name": "Kopi Dua", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    ids = res.json()
    tenant, outlet = ids["tenant_id"], ids["outlet_id"]
    # A staff member assigned to the outlet (created directly; invitations are tested in Wave 1).
    admin_sql("insert into auth.users (id, email) values (%s, %s)", (STAFF, f"rina@{DOMAIN}"))
    admin_sql(
        "insert into app.users (id, tenant_id, email, display_name, role, invitation_accepted_at)"
        " values (%s, %s, %s, 'Rina', 'staff', now())",
        (STAFF, tenant, f"rina@{DOMAIN}"),
    )
    admin_sql(
        "insert into app.staff_outlets (user_id, outlet_id, tenant_id) values (%s, %s, %s)",
        (STAFF, outlet, tenant),
    )
    owner = {
        "Authorization": f"Bearer {make_token(sub=str(OWNER), tenant_id=tenant, app_role='owner')}"
    }
    staff = {
        "Authorization": f"Bearer {make_token(sub=str(STAFF), tenant_id=tenant, app_role='staff')}"
    }
    return {"tenant": tenant, "outlet": outlet, "owner": owner, "staff": staff}


def _product(client: TestClient, ctx: dict[str, Any], name: str) -> dict[str, Any]:
    rows = client.get(
        f"/api/v1/owner/products?price_outlet_id={ctx['outlet']}", headers=ctx["owner"]
    ).json()
    return next(r for r in rows if r["name"] == name)


def _stock(client: TestClient, ctx: dict[str, Any], name: str) -> dict[str, Any]:
    view = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/stock", headers=ctx["staff"]).json()
    return next(i for i in view["items"] if i["name"] == name)


def test_onboarding_seeds_editable_sample_menu(client, ctx) -> None:
    rows = client.get(
        f"/api/v1/owner/products?price_outlet_id={ctx['outlet']}", headers=ctx["owner"]
    ).json()
    assert {r["name"] for r in rows} == {
        "Es Kopi Susu Senja",
        "Americano",
        "Matcha Latte",
        "Croissant Butter",
        "Roti Bakar Cokelat",
        "Kentang Goreng",
    }
    kopi = next(r for r in rows if r["name"] == "Es Kopi Susu Senja")
    assert (
        kopi["price"],
        kopi["status"],
        kopi["is_sample"],
        kopi["addon_group_count"],
        kopi["ingredient_count"],
    ) == (25000, "active", True, 3, 4)
    detail = client.get(f"/api/v1/owner/products/{kopi['id']}", headers=ctx["owner"]).json()
    assert [g["name"] for g in detail["addon_groups"]] == ["Ukuran", "Pilihan susu", "Gula"]
    large = detail["addon_groups"][0]["options"][1]
    assert large["name"] == "Large" and large["prices"][0]["price"] == 5000
    assert {(r["stock_item"], Decimal(r["quantity"])) for r in large["recipe"]} == {
        ("Biji kopi house blend", Decimal(6)),
        ("Susu UHT", Decimal(50)),
    }


def test_product_crud_prices_and_status_filter(client, ctx) -> None:
    res = client.post(
        "/api/v1/owner/products",
        headers=ctx["owner"],
        json={"name": "Teh Tarik", "category": "Non-kopi", "tags": ["Sweet", "sweet", " tea "]},
    )
    assert res.status_code == 201
    teh = res.json()
    assert teh["tags"] == ["sweet", "tea"] and teh["catalog_sync"] == "not_configured"
    prices = client.put(
        f"/api/v1/owner/products/{teh['id']}/prices",
        headers=ctx["owner"],
        json=[{"outlet_id": ctx["outlet"], "price": 15000}],
    ).json()
    assert prices[0]["price"] == 15000
    # A new item has no photo yet, so it starts Nonaktif (T-132); with a photo it can go live.
    assert teh["is_active"] is False and teh["has_photo"] is False
    assert _product(client, ctx, "Teh Tarik")["status"] == "inactive"
    admin_sql("update app.products set photo_path = 'x/teh.jpg' where id = %s", (teh["id"],))
    res = client.patch(
        f"/api/v1/owner/products/{teh['id']}", headers=ctx["owner"], json={"is_active": True}
    )
    assert res.status_code == 200, res.text
    # No recipe yet → cannot be sold → sold out at the outlet.
    assert _product(client, ctx, "Teh Tarik")["status"] == "sold_out"

    patched = client.patch(
        f"/api/v1/owner/products/{teh['id']}",
        headers=ctx["owner"],
        json={"is_active": False, "description": None},
    ).json()
    assert patched["is_active"] is False
    inactive = client.get(
        f"/api/v1/owner/products?price_outlet_id={ctx['outlet']}&status=inactive",
        headers=ctx["owner"],
    ).json()
    assert [r["name"] for r in inactive] == ["Teh Tarik"]
    assert client.delete(f"/api/v1/owner/products/{teh['id']}", headers=ctx["owner"]).json() == {
        "result": "deleted"
    }


def test_sample_flag_cleared_on_edit(client, ctx) -> None:
    kentang = _product(client, ctx, "Kentang Goreng")
    res = client.patch(
        f"/api/v1/owner/products/{kentang['id']}",
        headers=ctx["owner"],
        json={"name": "Kentang Goreng Keju"},
    )
    assert res.json()["is_sample"] is False


def test_addon_group_limits_and_replace(client, ctx) -> None:
    kopi = _product(client, ctx, "Americano")
    too_many = [{"name": f"Opsi {i}"} for i in range(11)]
    res = client.post(
        f"/api/v1/owner/products/{kopi['id']}/addon-groups",
        headers=ctx["owner"],
        json={"name": "Shot", "options": too_many},
    )
    assert res.status_code == 422
    res = client.post(
        f"/api/v1/owner/products/{kopi['id']}/addon-groups",
        headers=ctx["owner"],
        json={
            "name": "Shot",
            "selection": "multiple",
            "options": [
                {"name": "Extra shot", "prices": [{"outlet_id": ctx["outlet"], "price": 6000}]},
                {"name": "Decaf"},
            ],
        },
    )
    assert res.status_code == 201
    group = next(g for g in res.json()["addon_groups"] if g["name"] == "Shot")
    extra = group["options"][0]
    # Replace: keep Extra shot (renamed), drop Decaf.
    res = client.patch(
        f"/api/v1/owner/addon-groups/{group['id']}",
        headers=ctx["owner"],
        json={
            "name": "Shot",
            "selection": "multiple",
            "is_required": False,
            "options": [{"id": extra["id"], "name": "Extra shot espresso"}],
        },
    )
    group = next(g for g in res.json()["addon_groups"] if g["name"] == "Shot")
    assert [o["name"] for o in group["options"]] == ["Extra shot espresso"]
    assert (
        client.delete(f"/api/v1/owner/addon-groups/{group['id']}", headers=ctx["owner"]).status_code
        == 204
    )


def test_addon_group_slot_freed_by_removing_an_option(client, ctx) -> None:
    """Regression: removed options are deactivated, and only active ones count toward 10."""
    kopi = _product(client, ctx, "Americano")
    res = client.post(
        f"/api/v1/owner/products/{kopi['id']}/addon-groups",
        headers=ctx["owner"],
        json={"name": "Topping", "options": [{"name": f"T{i}"} for i in range(10)]},
    )
    assert res.status_code == 201, res.text
    group = next(g for g in res.json()["addon_groups"] if g["name"] == "Topping")
    options = group["options"]
    assert len(options) == 10
    # Remove one and add one in the same save (what the editor does).
    body = {
        "name": "Topping",
        "selection": "single",
        "is_required": False,
        "options": [{"id": o["id"], "name": o["name"]} for o in options[1:]] + [{"name": "Baru"}],
    }
    res = client.patch(f"/api/v1/owner/addon-groups/{group['id']}", headers=ctx["owner"], json=body)
    assert res.status_code == 200, res.text
    group = next(g for g in res.json()["addon_groups"] if g["name"] == "Topping")
    assert [o["name"] for o in group["options"]][-1] == "Baru"
    assert len(group["options"]) == 10
    # An 11th active option is still rejected.
    body["options"].append({"name": "Terlalu banyak"})
    res = client.patch(f"/api/v1/owner/addon-groups/{group['id']}", headers=ctx["owner"], json=body)
    assert res.status_code == 422
    client.delete(f"/api/v1/owner/addon-groups/{group['id']}", headers=ctx["owner"])


def test_unknown_outlet_in_option_prices_is_422_not_500(client, ctx) -> None:
    kopi = _product(client, ctx, "Americano")
    res = client.post(
        f"/api/v1/owner/products/{kopi['id']}/addon-groups",
        headers=ctx["owner"],
        json={
            "name": "Salah outlet",
            "options": [
                {
                    "name": "X",
                    "prices": [
                        {"outlet_id": "00000000-0000-0000-0000-0000000000ff", "price": 1000}
                    ],
                }
            ],
        },
    )
    assert res.status_code == 422, res.text


def test_blank_names_are_validation_errors(client, ctx) -> None:
    owner = ctx["owner"]
    assert (
        client.post("/api/v1/owner/products", headers=owner, json={"name": "  "}).status_code == 422
    )
    kopi = _product(client, ctx, "Americano")
    res = client.patch(f"/api/v1/owner/products/{kopi['id']}", headers=owner, json={"name": " "})
    assert res.status_code == 422
    res = client.post("/api/v1/owner/stock-items", headers=owner, json={"name": " ", "unit": "g"})
    assert res.status_code == 422
    # Trimmed on the way in.
    res = client.post(
        "/api/v1/owner/stock-items", headers=owner, json={"name": "  Es batu  ", "unit": "g"}
    )
    assert res.status_code == 201, res.text


def test_reorder_requires_every_group_once(client, ctx) -> None:
    kopi = _product(client, ctx, "Es Kopi Susu Senja")
    detail = client.get(f"/api/v1/owner/products/{kopi['id']}", headers=ctx["owner"]).json()
    ids = [g["id"] for g in detail["addon_groups"]]
    url = f"/api/v1/owner/products/{kopi['id']}/addon-groups/order"
    assert client.put(url, headers=ctx["owner"], json=ids[:-1]).status_code == 422
    assert client.put(url, headers=ctx["owner"], json=list(reversed(ids))).status_code == 204


def test_recipe_rules_and_availability(client, ctx) -> None:
    croissant = _product(client, ctx, "Croissant Butter")
    url = f"/api/v1/owner/products/{croissant['id']}/recipe"
    assert client.put(url, headers=ctx["owner"], json=[]).status_code == 422
    item = _stock(client, ctx, "Croissant (frozen)")
    res = client.put(
        url, headers=ctx["owner"], json=[{"stock_item_id": item["stock_item_id"], "quantity": "2"}]
    )
    assert res.status_code == 200 and Decimal(res.json()[0]["quantity"]) == 2
    avail = client.get(
        f"/api/v1/owner/products/{croissant['id']}/availability", headers=ctx["owner"]
    ).json()
    assert avail[0]["portions_available"] == 10  # 20 pcs opening stock / 2 per portion


def test_stock_view_movements_and_sold_out_recovery(client, ctx) -> None:
    base = f"/api/v1/ops/outlets/{ctx['outlet']}"
    matcha = _stock(client, ctx, "Bubuk matcha")
    assert (Decimal(matcha["on_hand"]), matcha["status"]) == (Decimal(500), "ok")

    # Waste everything: matcha goes out, Matcha Latte becomes sold out (staff can do this).
    res = client.post(
        f"{base}/stock-movements",
        headers=ctx["staff"],
        json={
            "type": "waste",
            "stock_item_id": matcha["stock_item_id"],
            "quantity": "500",
            "note": "basah",
        },
    )
    assert res.status_code == 201, res.text
    matcha = _stock(client, ctx, "Bubuk matcha")
    assert matcha["status"] == "out"
    assert {"name": "Matcha Latte", "kind": "product", "sold_out": True} in matcha[
        "affected_products"
    ]
    assert _product(client, ctx, "Matcha Latte")["status"] == "sold_out"

    # Cannot go below zero.
    res = client.post(
        f"{base}/stock-movements",
        headers=ctx["staff"],
        json={"type": "adjustment", "stock_item_id": matcha["stock_item_id"], "quantity": "-1"},
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "insufficient_stock"

    # Restock 150 g (threshold 200) → low, and the latte is available again.
    client.post(
        f"{base}/stock-movements",
        headers=ctx["staff"],
        json={"type": "restock", "stock_item_id": matcha["stock_item_id"], "quantity": "150"},
    )
    matcha = _stock(client, ctx, "Bubuk matcha")
    assert matcha["status"] == "low"
    assert _product(client, ctx, "Matcha Latte")["status"] == "active"
    low = client.get(f"{base}/stock?status=low", headers=ctx["staff"]).json()
    assert [i["name"] for i in low["items"]] == ["Bubuk matcha"] and low["counts"]["low"] == 1

    history = client.get(
        f"{base}/stock-movements?stock_item_id={matcha['stock_item_id']}", headers=ctx["staff"]
    ).json()
    assert [(m["type"], Decimal(m["quantity"]), m["actor"]) for m in history["items"]] == [
        ("restock", Decimal(150), "Rina"),
        ("waste", Decimal(-500), "Rina"),
        ("restock", Decimal(500), "system"),
    ]
    # Movements are append-only, even for the backend role.
    with pytest.raises(Exception, match="permission denied"):
        import psycopg

        assert APP_URL
        with psycopg.connect(APP_URL) as conn:
            conn.execute("delete from app.stock_movements")


def test_thresholds_owner_only(client, ctx) -> None:
    item = _stock(client, ctx, "Roti tawar")
    url = f"/api/v1/owner/stock-items/{item['stock_item_id']}/thresholds"
    body = [{"outlet_id": ctx["outlet"], "low_threshold": "30"}]
    assert client.put(url, headers=ctx["staff"], json=body).status_code == 403
    assert client.put(url, headers=ctx["owner"], json=body).status_code == 204
    assert _stock(client, ctx, "Roti tawar")["status"] == "low"  # 24 <= 30


def test_stock_items_and_new_outlet_gets_prices(client, ctx) -> None:
    res = client.post(
        "/api/v1/owner/stock-items",
        headers=ctx["owner"],
        json={"name": "Teh celup", "unit": "pcs", "display_unit": "kg"},
    )
    assert res.status_code == 422  # kg does not fit pcs
    res = client.post(
        "/api/v1/owner/stock-items", headers=ctx["owner"], json={"name": "Teh celup", "unit": "pcs"}
    )
    assert res.status_code == 201
    assert (
        client.post(
            "/api/v1/owner/stock-items",
            headers=ctx["owner"],
            json={"name": "Teh celup", "unit": "pcs"},
        ).status_code
        == 409
    )

    outlet = client.post(
        "/api/v1/owner/outlets", headers=ctx["owner"], json={"name": "Riau"}
    ).json()
    rows = client.get(
        f"/api/v1/owner/products?price_outlet_id={outlet['id']}", headers=ctx["owner"]
    ).json()
    assert next(r for r in rows if r["name"] == "Americano")["price"] == 22000
    assert (
        next(r for r in rows if r["name"] == "Americano")["status"] == "sold_out"
    )  # no stock there
    # Staff not assigned to the new outlet cannot read its stock.
    assert (
        client.get(f"/api/v1/ops/outlets/{outlet['id']}/stock", headers=ctx["staff"]).status_code
        == 404
    )
