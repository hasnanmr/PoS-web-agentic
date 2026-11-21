"""Customer table web page (T-133, T-134, T-136; issue #44) against Postgres through RLS.

Wireframes Q0-Q5 and O8; PRD FR2.13-FR2.16, AC2.15-AC2.21, ACN6. Web orders are always paid first
with the outlet's static QRIS: "Saya sudah bayar" → staff accept or reject in S4.
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

DOMAIN = "tableqr.test"
OWNER = UUID("70000000-0000-0000-0000-0000000000a0")
STAFF = UUID("70000000-0000-0000-0000-0000000000a1")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _bearer(sub: UUID, tenant: str | None, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=str(sub), tenant_id=tenant, app_role=role)}"}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    cleanup_domain(DOMAIN)
    invite_owner(OWNER, f"owner@{DOMAIN}")
    settings = Settings(database_url=APP_URL, admin_app_url="https://admin.test")
    with TestClient(create_app(settings, token_verifier=make_verifier())) as c:
        yield c
    cleanup_domain(DOMAIN)


@pytest.fixture(scope="module")
def ctx(client: TestClient) -> dict[str, Any]:
    res = client.post(
        "/api/v1/owner/onboarding",
        headers=_bearer(OWNER, None, "owner_pending"),
        json={"business": {"name": "Kopi QR", "type": "cafe"}, "outlet": {"name": "Dago"}},
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
    owner = _bearer(OWNER, tenant, "owner")
    staff = _bearer(STAFF, tenant, "staff")
    # Open-bill outlet with PB1 10%: web orders must still be paid first (AC2.17).
    res = client.patch(
        f"/api/v1/owner/outlets/{outlet}",
        headers=owner,
        json={"payment_mode": "open_bill", "pb1_enabled": True, "pb1_rate_bps": 1000},
    )
    assert res.status_code == 200, res.text
    for name in ("M05", "M06"):
        res = client.post(
            f"/api/v1/owner/outlets/{outlet}/tables",
            headers=owner,
            json={"name": name, "capacity": 4, "area": "Indoor"},
        )
        assert res.status_code == 201, res.text
    rows = admin_sql(
        "select name, id, qr_token from app.tables where outlet_id = %s order by name", (outlet,)
    )
    tables = {r[0]: {"id": str(r[1]), "token": r[2]} for r in rows}
    return {
        "tenant": tenant,
        "outlet": outlet,
        "owner": owner,
        "staff": staff,
        "m05": tables["M05"],
        "m06": tables["M06"],
    }


def _token(ctx: dict[str, Any], table: str = "m05") -> str:
    return admin_sql("select qr_token from app.tables where id = %s", (ctx[table]["id"],))[0][0]


def _upload_qris(client: TestClient, ctx: dict[str, Any]) -> None:
    res = client.put(
        f"/api/v1/owner/outlets/{ctx['outlet']}/qris?filename=qris.png",
        headers={**ctx["owner"], "Content-Type": "image/png"},
        content=PNG,
    )
    assert res.status_code == 200, res.text


def _menu(client: TestClient, token: str) -> dict[str, dict[str, Any]]:
    res = client.get(f"/api/v1/public/t/{token}/menu")
    assert res.status_code == 200, res.text
    return {m["name"]: m for m in res.json()}


def _place(
    client: TestClient,
    token: str,
    items: list[dict[str, Any]],
    key: str | None = None,
    **extra: Any,
) -> Any:
    return client.post(
        f"/api/v1/public/t/{token}/orders",
        headers={"Idempotency-Key": key or uuid4().hex},
        json={"items": items, **extra},
    )


def _americano(client: TestClient, ctx: dict[str, Any]) -> dict[str, Any]:
    token = _token(ctx)
    americano = _menu(client, token)["Americano"]["product_id"]
    res = _place(client, token, [{"product_id": americano, "quantity": 1}], customer_name="Rina")
    assert res.status_code == 201, res.text
    return {**res.json(), "token": token}


def _status(client: TestClient, order: dict[str, Any], key: str | None = None) -> Any:
    return client.get(
        f"/api/v1/public/t/{order['token']}/orders/{order['order_id']}",
        headers={"X-Order-Key": key if key is not None else order["access_key"]},
    )


def _card(client: TestClient, ctx: dict[str, Any], order_id: str) -> dict[str, Any]:
    board = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/orders/board", headers=ctx["staff"])
    assert board.status_code == 200, board.text
    return next(c for col in board.json().values() for c in col if c["id"] == order_id)


def _claim(client: TestClient, order: dict[str, Any]) -> Any:
    return client.post(
        f"/api/v1/public/t/{order['token']}/orders/{order['order_id']}/payment-claim",
        headers={"X-Order-Key": order["access_key"]},
    )


# Q0 · Q1 -------------------------------------------------------------------------------------


def test_unknown_token_is_q0_without_any_data(client, ctx) -> None:
    for token in ("x" * 32, "short", "bad token with spaces!!!!!!!!!!!"):
        res = client.get(f"/api/v1/public/t/{token}")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "table_qr_invalid"


def test_table_page_without_whatsapp_or_qris(client, ctx) -> None:
    res = client.get(f"/api/v1/public/t/{_token(ctx)}")
    assert res.status_code == 200, res.text
    page = res.json()
    assert page["outlet"]["name"] == "Dago" and page["table"] == {"name": "M05", "area": "Indoor"}
    # WhatsApp isn't connected → always the web page (FR2.16); no QRIS yet → menu only.
    assert page["target"] == "web" and page["whatsapp_url"] is None
    assert page["web_ordering"] is False
    americano = _menu(client, _token(ctx))["Americano"]["product_id"]
    res = _place(client, _token(ctx), [{"product_id": americano, "quantity": 1}])
    assert res.status_code == 409 and res.json()["error"]["code"] == "web_ordering_unavailable"


def test_qr_target_and_whatsapp_link(client, ctx) -> None:
    url = f"/api/v1/owner/outlets/{ctx['outlet']}/table-qr-settings"
    assert client.get(url, headers=ctx["owner"]).json() == {
        "target": "web_whatsapp",
        "whatsapp_connected": False,
    }
    assert client.put(url, headers=ctx["staff"], json={"target": "web"}).status_code == 403
    admin_sql(
        "update app.outlets set whatsapp_status = 'connected', whatsapp_phone = '+6281234567890'"
        " where id = %s",
        (ctx["outlet"],),
    )
    try:
        page = client.get(f"/api/v1/public/t/{_token(ctx)}").json()
        assert page["target"] == "web_whatsapp"
        assert page["whatsapp_url"].startswith("https://wa.me/6281234567890?text=MEJA%20M05")
        res = client.put(url, headers=ctx["owner"], json={"target": "whatsapp"})
        assert res.status_code == 200 and res.json()["target"] == "whatsapp"
        assert client.get(f"/api/v1/public/t/{_token(ctx)}").json()["target"] == "whatsapp"
        res = client.put(url, headers=ctx["owner"], json={"target": "web"})
        page = client.get(f"/api/v1/public/t/{_token(ctx)}").json()
        assert page["target"] == "web" and page["whatsapp_url"] is None
    finally:
        admin_sql(
            "update app.outlets set whatsapp_status = 'not_started', whatsapp_phone = null,"
            " table_qr_target = 'web_whatsapp' where id = %s",
            (ctx["outlet"],),
        )
    audit = admin_sql(
        "select count(*) from app.audit_events where action = 'table_qr_settings.updated'"
        " and outlet_id = %s",
        (ctx["outlet"],),
    )
    assert audit[0][0] >= 2


# Q2 · Q3 -------------------------------------------------------------------------------------


def test_web_order_is_pay_first_and_never_joins_the_open_bill(client, ctx) -> None:
    _upload_qris(client, ctx)
    token = _token(ctx)
    assert client.get(f"/api/v1/public/t/{token}").json()["web_ordering"] is True
    # Table M05 already has an open bill from the counter.
    menu = _menu(client, token)
    roti = menu["Roti Bakar Cokelat"]["product_id"]
    res = client.post(
        f"/api/v1/ops/outlets/{ctx['outlet']}/orders",
        headers=ctx["staff"],
        json={
            "type": "dine_in",
            "table_id": ctx["m05"]["id"],
            "items": [{"product_id": roti, "quantity": 1}],
            "payment": {"to_open_bill": True},
        },
    )
    assert res.status_code == 201, res.text
    bill_id = res.json()["bill_id"]
    bill_before = client.get(f"/api/v1/ops/bills/{bill_id}", headers=ctx["staff"]).json()

    americano = menu["Americano"]
    res = client.post(f"/api/v1/public/t/{token}/orders", json={"items": []})
    assert res.status_code == 422  # Idempotency-Key + items required
    key = uuid4().hex
    body = [{"product_id": americano["product_id"], "quantity": 2, "note": "es sedikit"}]
    res = _place(client, token, body, key, note="kurang manis", customer_name="  Rina ")
    assert res.status_code == 201, res.text
    order = res.json()
    assert order["status"] == "pending_payment" and order["payment_status"] == "unpaid"
    assert order["subtotal"] == 2 * americano["price"]
    assert order["total"] == order["subtotal"] + order["pb1_amount"]
    assert len(order["access_key"]) >= 30 and order["pay_by"]

    # A retry with the same key returns the same order, not a second order. The old Q3 page
    # sends no X-Order-Key, so the replay gets a NEW access key (the first is not stored in
    # plaintext anywhere) and the earlier one stops working.
    again = _place(client, token, body, key, note="kurang manis", customer_name="  Rina ")
    assert again.status_code == 200 and again.headers["Idempotent-Replay"] == "true"
    assert again.json()["order_id"] == order["order_id"]
    assert again.json()["access_key"] != order["access_key"]
    stale = client.get(
        f"/api/v1/public/t/{token}/orders/{order['order_id']}",
        headers={"X-Order-Key": order["access_key"]},
    )
    assert stale.status_code == 404
    order = {**order, "access_key": again.json()["access_key"]}

    row = admin_sql(
        "select channel::text, payment_mode::text, bill_id, customer_name, note from app.orders"
        " where id = %s",
        (order["order_id"],),
    )[0]
    assert row == ("web_table", "pay_first", None, "Rina", "kurang manis")
    bill_after = client.get(f"/api/v1/ops/bills/{bill_id}", headers=ctx["staff"]).json()
    assert bill_after["total"] == bill_before["total"]  # AC2.17

    # S2 card: web channel, table, name, note, unpaid with an auto-cancel time.
    card = _card(client, ctx, order["order_id"])
    assert card["channel"] == "web_table" and card["table"] == "M05"
    assert card["customer_name"] == "Rina" and card["note"] == "kurang manis"
    assert card["item_summary"] == "2× Americano (es sedikit)"  # noqa: RUF001 - per-item note
    status = client.get(
        f"/api/v1/public/t/{token}/orders/{order['order_id']}",
        headers={"X-Order-Key": order["access_key"]},
    ).json()
    assert status["items"][0]["note"] == "es sedikit"
    assert card["auto_cancel_at"] is not None and card["payment_claimed_at"] is None
    assert "preparing" not in card["allowed_actions"]


def test_price_changed_when_the_page_total_is_stale(client, ctx) -> None:
    token = _token(ctx)
    americano = _menu(client, token)["Americano"]["product_id"]
    q = client.post(
        f"/api/v1/public/t/{token}/quote",
        json={"items": [{"product_id": americano, "quantity": 2}]},
    )
    assert q.status_code == 200, q.text
    assert q.json()["pb1_rate_bps"] == 1000
    assert q.json()["total"] == q.json()["subtotal"] + q.json()["pb1_amount"]
    ok = _place(
        client,
        token,
        [{"product_id": americano, "quantity": 2}],
        expected_total=q.json()["total"],
    )
    assert ok.status_code == 201, ok.text
    res = _place(client, token, [{"product_id": americano, "quantity": 1}], expected_total=1)
    assert res.status_code == 409 and res.json()["error"]["code"] == "price_changed"
    assert res.json()["error"]["details"]["quote"]["total"] > 1


# Q4 · Q5 · S2 · S4 ---------------------------------------------------------------------------


def test_order_needs_its_access_key_and_its_table(client, ctx) -> None:
    order = _americano(client, ctx)
    assert _status(client, order).status_code == 200
    assert _status(client, order, key="").status_code == 404
    assert _status(client, order, key="wrong-key-" * 3).status_code == 404
    other = {**order, "token": _token(ctx, "m06")}
    assert _status(client, other).status_code == 404  # same key, other table
    qris = client.get(
        f"/api/v1/public/t/{order['token']}/orders/{order['order_id']}/qris",
        headers={"X-Order-Key": order["access_key"]},
    )
    assert qris.status_code == 200 and qris.content == PNG
    no_key = client.get(f"/api/v1/public/t/{order['token']}/orders/{order['order_id']}/qris")
    assert no_key.status_code == 404


def test_claim_then_staff_accept_sends_it_to_the_kitchen(client, ctx) -> None:
    order = _americano(client, ctx)
    res = _claim(client, order)
    assert res.status_code == 200, res.text
    assert res.json()["payment_status"] == "proof_submitted" and res.json()["claimed_at"]
    assert _claim(client, order).status_code == 200  # idempotent

    card = _card(client, ctx, order["order_id"])
    assert card["payment_claimed_at"] is not None and card["proof_id"]
    assert card["auto_cancel_at"] is None  # the timer stopped
    queue = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/payment-proofs", headers=ctx["staff"]
    ).json()
    item = next(q for q in queue if q["order_id"] == order["order_id"])
    assert item["kind"] == "customer_claim" and item["table"] == "M05"
    detail = client.get(f"/api/v1/ops/payment-proofs/{card['proof_id']}", headers=ctx["staff"])
    assert detail.json()["kind"] == "customer_claim" and detail.json()["image_url"] is None

    res = client.post(
        f"/api/v1/ops/payment-proofs/{card['proof_id']}/accept",
        headers=ctx["staff"],
        json={"merchant_account_checked": True},
    )
    assert res.status_code == 200, res.text
    status = _status(client, order).json()
    assert status["status"] == "confirmed" and status["payment_status"] == "paid"
    assert [e["status"] for e in status["events"]][:2] == ["pending_payment", "confirmed"]
    ledger = admin_sql(
        "select count(*) from app.ledger_entries where order_id = %s", (order["order_id"],)
    )
    assert ledger[0][0] >= 1


def test_staff_reject_cancels_and_returns_stock(client, ctx) -> None:
    order = _americano(client, ctx)
    assert _claim(client, order).status_code == 200
    proof_id = _card(client, ctx, order["order_id"])["proof_id"]
    res = client.post(
        f"/api/v1/ops/payment-proofs/{proof_id}/reject",
        headers=ctx["staff"],
        json={"reason": "Pembayaran tidak ditemukan"},
    )
    assert res.status_code == 200, res.text
    status = _status(client, order).json()
    assert status["status"] == "cancelled"
    assert status["reject_reason"] == "Pembayaran tidak ditemukan"
    moved = admin_sql(
        "select coalesce(sum(quantity), 0) from app.stock_movements where order_id = %s",
        (order["order_id"],),
    )
    assert moved[0][0] == 0  # sale and sale_reversal cancel out


def test_customer_cancels_only_before_claiming(client, ctx) -> None:
    order = _americano(client, ctx)
    url = f"/api/v1/public/t/{order['token']}/orders/{order['order_id']}/cancel"
    res = client.post(url, headers={"X-Order-Key": order["access_key"]})
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert res.json()["cancel_reason"]

    claimed = _americano(client, ctx)
    assert _claim(client, claimed).status_code == 200
    url = f"/api/v1/public/t/{claimed['token']}/orders/{claimed['order_id']}/cancel"
    res = client.post(url, headers={"X-Order-Key": claimed["access_key"]})
    assert res.status_code == 409 and res.json()["error"]["code"] == "order_not_cancellable"


def test_unpaid_order_is_cancelled_after_the_limit(client, ctx) -> None:
    order = _americano(client, ctx)
    admin_sql(
        "update app.orders set created_at = now() - interval '16 minutes' where id = %s",
        (order["order_id"],),
    )
    status = _status(client, order).json()  # any public call runs the check first
    assert status["status"] == "cancelled" and "Batal otomatis" in status["cancel_reason"]
    res = _claim(client, order)
    assert res.status_code == 409 and res.json()["error"]["code"] == "order_not_payable"
    actor = admin_sql(
        "select actor_type::text from app.order_events where order_id = %s"
        " and to_status = 'cancelled'",
        (order["order_id"],),
    )
    assert actor == [("system",)]


# O8 · QR download and token -----------------------------------------------------------------


def test_owner_downloads_qr_and_replaces_the_token(client, ctx) -> None:
    table = ctx["m06"]["id"]
    png = client.get(f"/api/v1/owner/tables/{table}/qr.png", headers=ctx["owner"])
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")
    assert (
        client.get(f"/api/v1/owner/tables/{table}/qr.png", headers=ctx["staff"]).status_code == 403
    )
    pdf = client.get(f"/api/v1/owner/outlets/{ctx['outlet']}/tables/qr.pdf", headers=ctx["owner"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-1.4")
    assert pdf.content.count(b"/Type /Page ") == 2  # M05 and M06

    old = _token(ctx, "m06")
    res = client.post(f"/api/v1/owner/tables/{table}/qr-token", headers=ctx["owner"])
    assert res.status_code == 200, res.text
    new = res.json()["qr_token"]
    assert new != old and res.json()["url"] == f"https://admin.test/t/{new}"
    old_page = client.get(f"/api/v1/public/t/{old}")
    assert old_page.status_code == 404 and old_page.json()["error"]["code"] == "table_qr_invalid"
    assert client.get(f"/api/v1/public/t/{new}").status_code == 200
    audit = admin_sql(
        "select count(*) from app.audit_events where action = 'table.qr_token_replaced'"
        " and entity_id = %s",
        (table,),
    )
    assert audit == [(1,)]
