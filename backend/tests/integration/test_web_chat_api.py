"""Customer web chat from the outlet link (T-140, T-141, T-049, T-055) against Postgres via RLS.

Wireframes C1-C9 and C13 on page 07; PRD FR2.0-FR2.6, FR2.10, FR2.14, FR2.15, FR6.2, FR6.4,
FR12.1, FR12.2; AC2.1, AC2.7, AC2.11, AC2.17, AC2.20, AC6.5, AC6.6, AC12.1, AC12.2.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.web_chat import PRIVACY_NOTICE_VERSION
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "webchat.test"
OWNER = UUID("71000000-0000-0000-0000-0000000000a0")
STAFF = UUID("71000000-0000-0000-0000-0000000000a1")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SESSION = {"X-Chat-Session": "s-" + "a" * 30}


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
        json={"business": {"name": "Kopi Chat", "type": "cafe"}, "outlet": {"name": "Senja Dago"}},
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
    # AC2.7: Rp10.000 delivery fee and 10% PB1.
    res = client.patch(
        f"/api/v1/owner/outlets/{outlet}",
        headers=owner,
        json={"pb1_enabled": True, "pb1_rate_bps": 1000, "delivery_fee": 10000},
    )
    assert res.status_code == 200, res.text
    res = client.post(
        f"/api/v1/owner/outlets/{outlet}/tables",
        headers=owner,
        json={"name": "M01", "capacity": 4, "area": "Indoor"},
    )
    assert res.status_code == 201, res.text
    slug = f"senja-dago-{uuid4().hex[:6]}"
    admin_sql("update app.outlets set public_slug = %s where id = %s", (slug, outlet))
    token = admin_sql("select qr_token from app.tables where outlet_id = %s", (outlet,))[0][0]
    return {
        "tenant": tenant,
        "outlet": outlet,
        "owner": owner,
        "staff": _bearer(STAFF, tenant, "staff"),
        "slug": slug,
        "token": token,
    }


def _base(ctx: dict[str, Any]) -> str:
    return f"/api/v1/public/o/{ctx['slug']}"


def _upload_qris(client: TestClient, ctx: dict[str, Any]) -> None:
    res = client.put(
        f"/api/v1/owner/outlets/{ctx['outlet']}/qris?filename=qris.png",
        headers={**ctx["owner"], "Content-Type": "image/png"},
        content=PNG,
    )
    assert res.status_code == 200, res.text


def _menu(client: TestClient, ctx: dict[str, Any]) -> dict[str, dict[str, Any]]:
    res = client.get(f"{_base(ctx)}/menu")
    assert res.status_code == 200, res.text
    return {m["name"]: m for m in res.json()}


def _order(
    client: TestClient,
    ctx: dict[str, Any],
    *,
    fulfillment: str = "pickup",
    key: str | None = None,
    order_key: str | None = None,
    customer: dict[str, Any] | None = None,
    **extra: Any,
) -> Any:
    americano = _menu(client, ctx)["Americano"]["product_id"]
    body = {
        "items": [{"product_id": americano, "quantity": 1}],
        "fulfillment": fulfillment,
        "customer": customer or {"name": "Bima", "phone": "0812-3456 7890"},
        "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        **extra,
    }
    headers = {"Idempotency-Key": key or uuid4().hex, "X-Order-Key": order_key or _new_key()}
    return client.post(f"{_base(ctx)}/orders", headers=headers, json=body)


def _new_key() -> str:
    return "k-" + uuid4().hex + uuid4().hex


def _placed(client: TestClient, ctx: dict[str, Any], **kw: Any) -> dict[str, Any]:
    res = _order(client, ctx, **kw)
    assert res.status_code == 201, res.text
    return res.json()


def _board_card(client: TestClient, ctx: dict[str, Any], order_id: str) -> dict[str, Any]:
    board = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/orders/board", headers=ctx["staff"])
    assert board.status_code == 200, board.text
    return next(c for col in board.json().values() for c in col if c["id"] == order_id)


def _status(client: TestClient, ctx: dict[str, Any], order: dict[str, Any]) -> Any:
    return client.get(
        f"{_base(ctx)}/orders/{order['order_id']}", headers={"X-Order-Key": order["access_key"]}
    )


# C1 · C13 -------------------------------------------------------------------------------------


def test_unknown_or_old_slug_shows_nothing(client, ctx) -> None:
    for slug in ("tidak-ada-outlet", "x", "Bad Slug!"):
        res = client.get(f"/api/v1/public/o/{slug}")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "outlet_link_invalid"
        assert "Senja" not in res.text
    # AC2.11: the owner changes the slug → the old link stops working, the new one works.
    old, new = ctx["slug"], f"dago-baru-{uuid4().hex[:6]}"
    admin_sql("update app.outlets set public_slug = %s where id = %s", (new, ctx["outlet"]))
    try:
        assert client.get(f"/api/v1/public/o/{old}").status_code == 404
        assert client.get(f"/api/v1/public/o/{new}/menu").status_code == 200
    finally:
        admin_sql("update app.outlets set public_slug = %s where id = %s", (old, ctx["outlet"]))


def test_greeting_and_main_menu_options(client, ctx) -> None:
    page = client.get(_base(ctx)).json()
    assert page["outlet"]["name"] == "Senja Dago" and page["outlet"]["short_name"] == "SD"
    assert page["delivery_fee"] == 10000 and page["agent_enabled"] is False
    assert page["privacy_notice"]["version"] == PRIVACY_NOTICE_VERSION
    assert page["reservations_enabled"] is False  # AC2.1: no Reservasi buttons
    res = client.put(
        f"/api/v1/owner/outlets/{ctx['outlet']}/reservation-settings",
        headers=ctx["owner"],
        json={"is_enabled": True},
    )
    if res.status_code == 200:
        assert client.get(_base(ctx)).json()["reservations_enabled"] is True


def test_no_qris_means_menu_only(client, ctx) -> None:
    if client.get(_base(ctx)).json()["web_ordering"]:
        pytest.skip("QRIS already uploaded by an earlier test")
    res = _order(client, ctx)
    assert res.status_code == 409 and res.json()["error"]["code"] == "web_ordering_unavailable"
    assert admin_sql("select count(*) from app.customers where outlet_id = %s", (ctx["outlet"],))[
        0
    ] == (0,)  # rolled back with the refused order


# C4 · C5 ---------------------------------------------------------------------------------------


def test_quote_adds_the_delivery_fee_outside_pb1(client, ctx) -> None:
    americano = _menu(client, ctx)["Americano"]
    items = [{"product_id": americano["product_id"], "quantity": 2}]
    pickup = client.post(f"{_base(ctx)}/quote", json={"items": items, "fulfillment": "pickup"})
    delivery = client.post(f"{_base(ctx)}/quote", json={"items": items, "fulfillment": "delivery"})
    assert pickup.status_code == delivery.status_code == 200
    p, d = pickup.json(), delivery.json()
    assert p["delivery_fee"] == 0 and d["delivery_fee"] == 10000
    assert d["pb1_amount"] == p["pb1_amount"] == p["subtotal"] // 10
    assert d["total"] == d["subtotal"] + d["pb1_amount"] + 10000


def test_pickup_order_records_customer_and_privacy_notice(client, ctx) -> None:
    _upload_qris(client, ctx)
    key, order_key = uuid4().hex, _new_key()
    order = _placed(client, ctx, key=key, order_key=order_key)
    assert order["status"] == "pending_payment" and order["delivery_fee"] == 0
    assert order["access_key"] == order_key  # the page's own key, echoed
    # AC6.6: a double tap returns the same order and the same key.
    again = _order(client, ctx, key=key, order_key=order_key)
    assert again.status_code == 200 and again.json()["order_id"] == order["order_id"]
    assert again.json()["access_key"] == order_key
    # A replay with another key does not get the order (proof of holding the key).
    other = _order(client, ctx, key=key, order_key=_new_key())
    assert other.status_code == 409 and other.json()["error"]["code"] == "idempotency_key_reused"
    # The key is never stored in plaintext, also not in the idempotency cache (FR2.15).
    cached = admin_sql(
        "select count(*) from app.idempotency_keys where response::text like %s",
        (f"%{order_key}%",),
    )
    assert cached == [(0,)]
    row = admin_sql(
        "select o.channel::text, o.type::text, o.payment_mode::text, o.table_id, c.name, c.phone,"
        " a.notice_version from app.orders o join app.customers c on c.id = o.customer_id"
        " join app.privacy_notice_acknowledgements a on a.customer_id = c.id where o.id = %s",
        (order["order_id"],),
    )
    assert row == [
        ("web_online", "pickup", "pay_first", None, "Bima", "081234567890", PRIVACY_NOTICE_VERSION)
    ]
    status = _status(client, ctx, order).json()
    assert status["fulfillment"] == "pickup" and status["customer_name"] == "Bima"
    card = _board_card(client, ctx, order["order_id"])
    assert card["channel"] == "web_online" and card["auto_cancel_at"] is not None
    assert card["type"] == "pickup" and card["customer_phone"] == "081234567890"
    assert card["delivery_address"] is None


def test_details_are_checked(client, ctx) -> None:
    res = _order(client, ctx, fulfillment="delivery")  # no address
    assert res.status_code == 422 and res.json()["error"]["details"]["field"] == "address"
    res = _order(client, ctx, customer={"name": "Bima", "phone": "0812-abcd-999"})
    assert res.status_code == 422 and res.json()["error"]["details"]["field"] == "phone"
    res = _order(client, ctx, privacy_notice_version="2020-01-01")
    assert res.status_code == 422
    assert res.json()["error"]["details"]["field"] == "privacy_notice_version"
    res = client.post(f"{_base(ctx)}/orders", json={})
    assert res.status_code == 422
    no_key = client.post(
        f"{_base(ctx)}/orders",
        headers={"Idempotency-Key": uuid4().hex},
        json={
            "items": [{"product_id": str(uuid4()), "quantity": 1}],
            "fulfillment": "pickup",
            "customer": {"name": "Bima", "phone": "081234567890"},
            "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        },
    )
    assert no_key.status_code == 422 and no_key.json()["error"]["details"]["field"] == "access_key"
    short = _order(client, ctx, order_key="too-short")
    assert short.status_code == 422 and short.json()["error"]["details"]["field"] == "access_key"


def test_delivery_completed_is_anonymized(client, ctx) -> None:
    order = _placed(
        client,
        ctx,
        fulfillment="delivery",
        customer={"name": "Sari", "phone": "+6281111111111", "address": "Jl. Dago 1"},
    )
    assert order["delivery_fee"] == 10000
    assert order["total"] == order["subtotal"] + order["pb1_amount"] + 10000
    assert _status(client, ctx, order).json()["delivery_address"] == "Jl. Dago 1"
    claim = client.post(
        f"{_base(ctx)}/orders/{order['order_id']}/payment-claim",
        headers={"X-Order-Key": order["access_key"]},
    )
    assert claim.status_code == 200 and claim.json()["payment_status"] == "proof_submitted"
    proof = admin_sql(
        "select id from app.payment_proofs where order_id = %s", (order["order_id"],)
    )[0][0]
    res = client.post(
        f"/api/v1/ops/payment-proofs/{proof}/accept",
        headers=ctx["staff"],
        json={"merchant_account_checked": True},
    )
    assert res.status_code == 200, res.text
    # S2 card: who to call and where to deliver (review finding on PR #63).
    card = _board_card(client, ctx, order["order_id"])
    assert card["type"] == "delivery" and card["customer_name"] == "Sari"
    assert card["customer_phone"] == "+6281111111111"
    assert card["delivery_address"] == "Jl. Dago 1"
    queue = client.get(f"/api/v1/ops/payment-proofs/{proof}", headers=ctx["staff"]).json()
    assert queue["customer_phone_masked"] == "+62 811-xxxx-111"
    # O2: paid web_online orders count in the channel mix, and the shares cover every order.
    summary = client.get(
        "/api/v1/owner/dashboard", headers=ctx["owner"], params={"outlet_id": ctx["outlet"]}
    ).json()
    mix = {c["channel"]: c for c in summary["channel_mix"]}
    assert mix["web_online"]["orders"] >= 1
    assert sum(c["orders"] for c in summary["channel_mix"]) == summary["kpis"]["orders"]
    for step in ("preparing", "ready", "out_for_delivery", "completed"):
        res = client.post(
            f"/api/v1/ops/orders/{order['order_id']}/transitions",
            headers=ctx["staff"],
            json={"to_status": step},
        )
        assert res.status_code == 200, (step, res.text)
    # AC12.2: personal data gone, order and ledger intact.
    row = admin_sql(
        "select o.customer_name, o.delivery_address, o.total, c.name, c.phone, c.is_anonymized"
        " from app.orders o join app.customers c on c.id = o.customer_id where o.id = %s",
        (order["order_id"],),
    )[0]
    assert row == (None, None, order["total"], None, None, True)
    status = _status(client, ctx, order).json()  # readable for one more hour
    assert status["status"] == "completed" and status["delivery_address"] is None
    # AC12.3: no personal data in the ledger.
    leaked = admin_sql(
        "select count(*) from app.ledger_entries where tenant_id = %s"
        " and (to_jsonb(ledger_entries)::text like '%%6281111111111%%'"
        "      or to_jsonb(ledger_entries)::text like '%%Sari%%')",
        (ctx["tenant"],),
    )
    assert leaked == [(0,)]


# C6 · C7 · Pesanan Saya ---------------------------------------------------------------------


def test_orders_are_readable_only_in_their_scope(client, ctx) -> None:
    order = _placed(client, ctx)
    table = client.get(
        f"/api/v1/public/t/{ctx['token']}/orders/{order['order_id']}",
        headers={"X-Order-Key": order["access_key"]},
    )
    assert table.status_code == 404  # same outlet, other entry point
    wrong = client.get(
        f"{_base(ctx)}/orders/{order['order_id']}", headers={"X-Order-Key": "x" * 32}
    )
    assert wrong.status_code == 404


def test_pesanan_saya_lists_only_known_keys(client, ctx) -> None:
    a = _placed(client, ctx)
    b = _placed(client, ctx)
    res = client.post(
        f"{_base(ctx)}/orders/status",
        json={
            "orders": [
                {"order_id": a["order_id"], "key": a["access_key"]},
                {"order_id": b["order_id"], "key": "wrong-key-" * 3},
                {"order_id": str(uuid4()), "key": "unknown-key-0001"},
            ]
        },
    )
    assert res.status_code == 200, res.text
    assert [r["order_id"] for r in res.json()] == [a["order_id"]]
    assert res.json()[0]["fulfillment"] == "pickup"
    # AC2.20: hidden one hour after it is finished.
    client.post(
        f"{_base(ctx)}/orders/{a['order_id']}/cancel", headers={"X-Order-Key": a["access_key"]}
    )
    with psycopg.connect(ADMIN_URL) as conn:  # skip the updated_at touch trigger
        conn.execute("set local session_replication_role = replica")
        conn.execute(
            "update app.orders set updated_at = now() - interval '61 minutes' where id = %s",
            (a["order_id"],),
        )
    res = client.post(
        f"{_base(ctx)}/orders/status",
        json={"orders": [{"order_id": a["order_id"], "key": a["access_key"]}]},
    )
    assert res.json() == []


def test_cancel_is_repeatable_and_anonymizes(client, ctx) -> None:
    order = _placed(client, ctx)
    url = f"{_base(ctx)}/orders/{order['order_id']}/cancel"
    first = client.post(url, headers={"X-Order-Key": order["access_key"]})
    second = client.post(url, headers={"X-Order-Key": order["access_key"]})
    assert first.status_code == second.status_code == 200
    assert second.json()["status"] == "cancelled"
    anon = admin_sql(
        "select c.is_anonymized from app.orders o join app.customers c on c.id = o.customer_id"
        " where o.id = %s",
        (order["order_id"],),
    )
    assert anon == [(True,)]


def test_unpaid_online_order_is_cancelled_after_the_limit(client, ctx) -> None:
    order = _placed(client, ctx)
    admin_sql(
        "update app.orders set created_at = now() - interval '16 minutes' where id = %s",
        (order["order_id"],),
    )
    status = _status(client, ctx, order).json()
    assert status["status"] == "cancelled" and "Batal otomatis" in status["cancel_reason"]


# Chat session (FR6.2) --------------------------------------------------------------------------


def test_chat_session_resumes_and_expires_after_two_hours(client, ctx) -> None:
    url = f"{_base(ctx)}/chat-session"
    assert client.get(url).status_code == 422  # X-Chat-Session required
    fresh = client.get(url, headers=SESSION).json()
    assert fresh["step"] == "main_menu" and fresh["cart"] == {"lines": []}
    americano = _menu(client, ctx)["Americano"]["product_id"]
    cart = {"lines": [{"product_id": americano, "quantity": 2, "addon_option_ids": []}]}
    res = client.put(
        url, headers=SESSION, json={"step": "addons:x", "cart": cart, "fulfillment": "pickup"}
    )
    assert res.status_code == 200, res.text
    again = client.get(url, headers=SESSION).json()
    assert again["step"] == "addons:x" and again["cart"]["lines"][0]["quantity"] == 2
    # Another phone (session) and the table QR of the same outlet start empty.
    other = client.get(url, headers={"X-Chat-Session": "s-" + "b" * 30}).json()
    assert other["cart"] == {"lines": []}
    table = client.get(f"/api/v1/public/t/{ctx['token']}/chat-session", headers=SESSION).json()
    assert table["cart"] == {"lines": []}
    # AC6.5: idle for more than 2 hours → empty cart, flagged once.
    admin_sql(
        "update app.chat_sessions set last_activity_at = now() - interval '121 minutes'"
        " where outlet_id = %s and table_id is null",
        (ctx["outlet"],),
    )
    expired = client.get(url, headers=SESSION).json()
    assert expired["cart_expired"] is True and expired["cart"] == {"lines": []}
    assert client.get(url, headers=SESSION).json()["cart_expired"] is False
    stored = admin_sql(
        "select cart::text from app.chat_sessions where outlet_id = %s", (ctx["outlet"],)
    )
    assert all("Bima" not in r[0] for r in stored)  # no personal data in sessions


# C9 recommendations ------------------------------------------------------------------------------


def test_recommendation_cards_skip_sold_out_and_mark_picks(client, ctx) -> None:
    res = client.get(f"{_base(ctx)}/recommendations")
    assert res.status_code == 200, res.text
    cards = res.json()
    assert len(cards) <= 30
    assert {c["badge"] for c in cards} <= {"owner_pick", "best_seller"}
    menu = _menu(client, ctx)
    sold_out = {m["product_id"] for m in menu.values() if m["sold_out"]}
    assert not sold_out & {c["product_id"] for c in cards}
    picks = [c for c in cards if c["badge"] == "owner_pick"]
    assert picks == cards[: len(picks)]  # owner's picks first


def test_too_large_cart_is_a_validation_error(client, ctx) -> None:
    line = {
        "product_id": str(uuid4()),
        "quantity": 1,
        "addon_option_ids": [str(uuid4()) for _ in range(30)],
        "note": "x" * 200,
    }
    res = client.put(
        f"{_base(ctx)}/chat-session",
        headers=SESSION,
        json={"step": "cart", "cart": {"lines": [line] * 50}},
    )
    assert res.status_code == 422 and res.json()["error"]["details"]["field"] == "cart"


def test_idle_sessions_are_removed(client, ctx) -> None:
    other = {"X-Chat-Session": "s-" + "c" * 30}
    assert (
        client.put(f"{_base(ctx)}/chat-session", headers=other, json={"step": "menu"}).status_code
        == 200
    )
    admin_sql(
        "update app.chat_sessions set last_activity_at = now() - interval '3 hours'"
        " where outlet_id = %s",
        (ctx["outlet"],),
    )
    assert (
        client.put(f"{_base(ctx)}/chat-session", headers=SESSION, json={"step": "menu"}).status_code
        == 200
    )
    left = admin_sql(
        "select count(*) from app.chat_sessions where outlet_id = %s", (ctx["outlet"],)
    )
    assert left == [(1,)]  # only the session just saved


def test_default_slug_grows_its_suffix_on_a_collision(client, ctx) -> None:
    rows = admin_sql(
        "select app.default_outlet_slug('Senja Dago', id),"
        " app.unique_outlet_slug('Senja Dago', id),"
        " app.default_outlet_slug(repeat('panjang ', 20), id, 32)"
        " from app.outlets where id = %s",
        (ctx["outlet"],),
    )
    short, unique, longest = rows[0]
    assert unique == short  # nobody else has it
    assert len(longest) <= 40
    admin_sql("update app.outlets set public_slug = %s where id = %s", (short, ctx["outlet"]))
    try:
        other = admin_sql("select app.unique_outlet_slug('Senja Dago', %s)", (ctx["outlet"],))
        assert other == [(short,)]  # its own slug does not count as taken
        twin = admin_sql(
            "select app.unique_outlet_slug('Senja Dago', (left(%s::text, 8)"
            " || '-0000-4000-8000-000000000000')::uuid)",
            (ctx["outlet"],),
        )[0][0]
        assert twin != short and twin.startswith(short)  # longer suffix
    finally:
        admin_sql(
            "update app.outlets set public_slug = %s where id = %s", (ctx["slug"], ctx["outlet"])
        )
