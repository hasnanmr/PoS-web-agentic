"""Wave 4 API tests (T-037 to T-044) against Postgres through RLS: QRIS proof review (S4),
blind-count shift close (S8), expenses and reversal (O9), cashflow and cash count reports
(O9, O10), and the financial integrity rules (ledger only at confirmed payment, append-only,
owner-only expenses enforced by the database too).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "w4.test"
OWNER = UUID("50000000-0000-0000-0000-0000000000f0")
STAFF = UUID("50000000-0000-0000-0000-0000000000f1")


def _today() -> date:
    """Business dates are outlet-local (WIB here), not the test machine's date."""
    return datetime.now(ZoneInfo("Asia/Jakarta")).date()


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
        json={"business": {"name": "Kopi Empat", "type": "cafe"}, "outlet": {"name": "Dago"}},
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
    staff = _bearer(STAFF, tenant, "staff")
    menu = client.get(f"/api/v1/ops/outlets/{outlet}/menu", headers=staff).json()
    americano = next(m for m in menu if m["name"] == "Americano")
    drawers = client.get(f"/api/v1/ops/outlets/{outlet}/drawers", headers=staff).json()
    return {
        "tenant": tenant,
        "outlet": outlet,
        "owner": _bearer(OWNER, tenant, "owner"),
        "staff": staff,
        "americano": americano,
        "drawer": drawers[0]["drawer"]["id"],
    }


def _stock(product_id: str, outlet: str) -> tuple[str, Decimal, Decimal]:
    """(stock item, recipe quantity per portion, on hand) of the product's first ingredient."""
    sid, qty = admin_sql(
        "select stock_item_id, quantity from app.recipe_items where product_id = %s"
        " order by stock_item_id limit 1",
        (product_id,),
    )[0]
    on_hand = admin_sql(
        "select on_hand from app.outlet_stock where outlet_id = %s and stock_item_id = %s",
        (outlet, sid),
    )
    return str(sid), qty, on_hand[0][0] if on_hand else Decimal(0)


def _whatsapp_order_with_proof(ctx: dict[str, Any], total: int = 30000) -> dict[str, str]:
    """A WhatsApp pickup order waiting for payment with a screenshot received (T-036 makes
    these; here they are written directly). Its sale movement takes one portion of stock."""
    product = ctx["americano"]["product_id"]
    contact = admin_sql(
        "insert into app.whatsapp_contacts (tenant_id, phone)"
        " values (%s, '+62812' || (1000 + floor(random() * 9000))::int || '221') returning id",
        (ctx["tenant"],),
    )[0][0]
    number = admin_sql(
        "select coalesce(max(order_no), 1000) + 1 from app.orders where outlet_id = %s",
        (ctx["outlet"],),
    )[0][0]
    order = admin_sql(
        "insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode,"
        " status, payment_status, contact_id, subtotal, total, created_by_actor)"
        " values (%s, %s, %s, 'whatsapp_online', 'pickup', 'pay_first', 'pending_payment',"
        " 'proof_submitted', %s, %s, %s, 'system') returning id",
        (ctx["tenant"], ctx["outlet"], number, contact, total, total),
    )[0][0]
    admin_sql(
        "insert into app.order_items (tenant_id, outlet_id, order_id, product_id, name,"
        " unit_price, quantity, line_total) values (%s, %s, %s, %s, 'Americano', %s, 1, %s)",
        (ctx["tenant"], ctx["outlet"], order, product, total, total),
    )
    sid, qty, _ = _stock(product, ctx["outlet"])
    admin_sql(
        "insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity,"
        " order_id, actor_type) values (%s, %s, %s, 'sale', %s, %s, 'system')",
        (ctx["tenant"], ctx["outlet"], sid, -qty, order),
    )
    proof = admin_sql(
        "insert into app.payment_proofs (tenant_id, outlet_id, order_id, storage_path)"
        " values (%s, %s, %s, 'proofs/test.jpg') returning id",
        (ctx["tenant"], ctx["outlet"], order),
    )[0][0]
    return {"order": str(order), "proof": str(proof), "order_no": f"#A-{number}"}


def _ledger(order_id: str) -> list[tuple[str, int, str | None]]:
    return admin_sql(
        "select type::text, amount, payment_method::text from app.ledger_entries"
        " where order_id = %s order by id",
        (order_id,),
    )


def _cash_order(client: TestClient, ctx: dict[str, Any], cash: int = 100000) -> dict[str, Any]:
    res = client.post(
        f"/api/v1/ops/outlets/{ctx['outlet']}/orders",
        headers=ctx["staff"],
        json={
            "type": "takeaway",
            "items": [{"product_id": ctx["americano"]["product_id"], "quantity": 1}],
            "payment": {"method": "cash", "cash_received": cash},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _open_shift(client: TestClient, ctx: dict[str, Any], starting: int) -> str:
    res = client.post(
        f"/api/v1/ops/drawers/{ctx['drawer']}/shifts",
        headers=ctx["staff"],
        json={"starting_cash": starting},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# S4 · Review Pembayaran QRIS -----------------------------------------------------------------


def test_proof_queue_and_accept_posts_qris_ledger(client, ctx) -> None:
    made = _whatsapp_order_with_proof(ctx)
    queue = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/payment-proofs?status=pending", headers=ctx["staff"]
    ).json()
    item = next(q for q in queue if q["proof_id"] == made["proof"])
    assert item["order_no"] == made["order_no"] and item["order_type"] == "pickup"
    assert item["total"] == 30000

    detail = client.get(f"/api/v1/ops/payment-proofs/{made['proof']}", headers=ctx["staff"]).json()
    assert detail["customer_phone_masked"] == "+62 812-xxxx-221"
    assert detail["timer_stopped"] is True and detail["image_url"] is None
    assert detail["channel"] == "whatsapp_online"

    url = f"/api/v1/ops/payment-proofs/{made['proof']}/accept"
    res = client.post(url, headers=ctx["staff"], json={"merchant_account_checked": False})
    assert res.status_code == 422, res.text
    assert res.json()["error"]["details"]["field"] == "merchant_account_checked"
    assert _ledger(made["order"]) == []

    res = client.post(url, headers=ctx["staff"], json={"merchant_account_checked": True})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "accepted" and body["reviewed_by"] == "Rina"
    assert body["order_status"] == "confirmed" and body["payment_status"] == "paid"
    assert _ledger(made["order"]) == [("revenue", 30000, "qris")]
    checked = admin_sql(
        "select reviewed_by, merchant_checked_at is not null from app.payment_proofs where id = %s",
        (made["proof"],),
    )
    assert checked == [(STAFF, True)]

    order = client.get(f"/api/v1/ops/orders/{made['order']}", headers=ctx["staff"]).json()
    kinds = [(e["kind"], e["from_payment"], e["to_payment"], e["to"]) for e in order["events"]]
    assert ("payment_changed", "proof_submitted", "paid", None) in kinds
    assert ("status_changed", None, None, "confirmed") in kinds
    assert all(e["actor"]["name"] == "Rina" for e in order["events"])

    res = client.post(url, headers=ctx["staff"], json={"merchant_account_checked": True})
    assert res.status_code == 409 and res.json()["error"]["code"] == "proof_not_pending"
    assert _ledger(made["order"]) == [("revenue", 30000, "qris")]


def test_proof_reject_cancels_returns_stock_and_posts_nothing(client, ctx) -> None:
    made = _whatsapp_order_with_proof(ctx)
    sid, qty, before = _stock(ctx["americano"]["product_id"], ctx["outlet"])
    url = f"/api/v1/ops/payment-proofs/{made['proof']}/reject"
    res = client.post(url, headers=ctx["staff"], json={"reason": "  "})
    assert res.status_code == 422 and res.json()["error"]["code"] == "reason_required"

    res = client.post(url, headers=ctx["staff"], json={"reason": "Dana tidak masuk"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "rejected" and body["rejection_reason"] == "Dana tidak masuk"
    assert body["order_status"] == "cancelled" and body["payment_status"] == "unpaid"
    assert _ledger(made["order"]) == []
    assert _stock(ctx["americano"]["product_id"], ctx["outlet"])[2] == before + qty
    movements = admin_sql(
        "select type::text from app.stock_movements where order_id = %s order by id",
        (made["order"],),
    )
    assert movements == [("sale",), ("sale_reversal",)]
    event = admin_sql(
        "select reason, actor_id from app.order_events where order_id = %s"
        " and event = 'proof_rejected'",
        (made["order"],),
    )
    assert event == [("Dana tidak masuk", STAFF)]
    queue = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/payment-proofs", headers=ctx["staff"]
    ).json()
    assert made["proof"] not in [q["proof_id"] for q in queue]
    assert sid  # the first ingredient exists


# S8 · blind count ----------------------------------------------------------------------------


def test_blind_count_close_posts_surplus_and_is_idempotent(client, ctx) -> None:
    shift = _open_shift(client, ctx, 500000)
    order = _cash_order(client, ctx)
    cards = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/drawers", headers=ctx["staff"]).json()
    card = next(c for c in cards if c["drawer"]["id"] == ctx["drawer"])
    assert "expected_cash" not in card["shift"]  # blind: nothing to compare with yet

    url = f"/api/v1/ops/shifts/{shift}/close"
    res = client.post(url, headers=ctx["staff"], json={"count_breakdown": {"500": 3}})
    assert res.status_code == 422, res.text
    res = client.post(url, headers=ctx["staff"], json={"count_breakdown": {"100000": -1}})
    assert res.status_code == 422, res.text

    count = {"100000": 5, "coins": order["total"] + 2000}
    headers = {**ctx["staff"], "Idempotency-Key": f"close-{shift}"}
    res = client.post(url, headers=headers, json={"count_breakdown": count})
    assert res.status_code == 200, res.text
    closed = res.json()
    assert closed["expected_cash"] == 500000 + order["total"]
    assert closed["counted_cash"] == 500000 + order["total"] + 2000
    assert closed["difference"] == 2000 and closed["kind"] == "surplus"
    assert closed["counted_by"] == "Rina" and closed["cash_in"] == order["total"]
    assert admin_sql(
        "select type::text, amount, payment_method::text from app.ledger_entries"
        " where shift_id = %s and type in ('cash_shortage', 'cash_surplus')",
        (shift,),
    ) == [("cash_surplus", 2000, "cash")]

    replay = client.post(url, headers=headers, json={"count_breakdown": count})
    assert replay.status_code == 200 and replay.json() == closed
    again = client.post(url, headers=ctx["staff"], json={"count_breakdown": count})
    assert again.status_code == 409 and again.json()["error"]["code"] == "shift_closed"

    # No open shift any more: cash is refused.
    res = client.post(
        f"/api/v1/ops/outlets/{ctx['outlet']}/orders",
        headers=ctx["staff"],
        json={
            "type": "takeaway",
            "items": [{"product_id": ctx["americano"]["product_id"], "quantity": 1}],
            "payment": {"method": "cash", "cash_received": 100000},
        },
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "shift_not_open"


def test_blind_count_with_refund_posts_shortage_and_cash_count_report(client, ctx) -> None:
    shift = _open_shift(client, ctx, 300000)
    order = _cash_order(client, ctx)
    res = client.post(
        f"/api/v1/ops/orders/{order['id']}/reversal",
        headers=ctx["staff"],
        json={"reason": "Salah pesan", "ingredients": "return"},
    )
    assert res.status_code == 200, res.text
    # Expected = 300.000 + total - refund(total) = 300.000; 1.000 is missing.
    res = client.post(
        f"/api/v1/ops/shifts/{shift}/close",
        headers=ctx["staff"],
        json={"count_breakdown": {"100000": 2, "50000": 1, "20000": 2, "5000": 1, "2000": 2}},
    )
    assert res.status_code == 200, res.text
    closed = res.json()
    assert closed["cash_refunds"] == order["total"] and closed["expected_cash"] == 300000
    assert closed["difference"] == -1000 and closed["kind"] == "shortage"

    url = f"/api/v1/owner/reports/cash-count?outlet_id={ctx['outlet']}&drawer_id={ctx['drawer']}"
    assert client.get(url, headers=ctx["staff"]).status_code == 403
    report = client.get(url, headers=ctx["owner"]).json()
    assert report["summary"]["shifts"] == 2
    assert report["summary"]["shifts_with_difference"] == 2
    assert report["summary"]["total_shortage"] == -1000
    assert report["summary"]["total_surplus"] == 2000
    row = report["rows"][0]
    assert row["shift_id"] == shift and row["drawer"]["number"] == 1
    assert row["outlet"]["name"] == "Dago" and row["counted_by"] == "Rina"

    csv = client.get(url + "&format=csv", headers=ctx["owner"])
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    lines = csv.text.strip().splitlines()
    assert lines[0].startswith("tanggal,buka,tutup,zona,outlet,drawer") and len(lines) == 3
    assert ",-1000,shortage,Rina" in lines[1]


# O9 · expenses, reversal, cashflow -----------------------------------------------------------


def test_expenses_are_owner_only_append_only_and_reversible(client, ctx) -> None:
    today = _today().isoformat()
    body = {
        "outlet_id": ctx["outlet"],
        "amount": 350000,
        "business_date": today,
        "description": "Beli es batu & gas",
    }
    assert client.post("/api/v1/owner/expenses", headers=ctx["staff"], json=body).status_code == 403
    future = (_today() + timedelta(days=3)).isoformat()
    res = client.post(
        "/api/v1/owner/expenses", headers=ctx["owner"], json={**body, "business_date": future}
    )
    assert res.status_code == 422 and res.json()["error"]["details"]["field"] == "business_date"
    res = client.post(
        "/api/v1/owner/expenses", headers=ctx["owner"], json={**body, "description": "   "}
    )
    assert res.status_code == 422, res.text

    res = client.post("/api/v1/owner/expenses", headers=ctx["owner"], json=body)
    assert res.status_code == 201, res.text
    first = res.json()
    assert first["amount"] == 350000 and first["recorded_by"] and not first["reversed"]
    assert admin_sql(
        "select type::text, amount from app.ledger_entries where id = %s", (first["id"],)
    ) == [("expense", -350000)]
    for desc, amount in (("Servis mesin espresso", 1200000), ("Kemasan takeaway", 880000)):
        res = client.post(
            "/api/v1/owner/expenses",
            headers=ctx["owner"],
            json={**body, "description": desc, "amount": amount},
        )
        assert res.status_code == 201, res.text

    page = client.get("/api/v1/owner/expenses?limit=2", headers=ctx["owner"]).json()
    assert [e["description"] for e in page["items"]] == [
        "Kemasan takeaway",
        "Servis mesin espresso",
    ]
    rest = client.get(
        f"/api/v1/owner/expenses?limit=2&cursor={page['next_cursor']}", headers=ctx["owner"]
    ).json()
    assert [e["description"] for e in rest["items"]] == ["Beli es batu & gas"]
    assert rest["next_cursor"] is None

    url = f"/api/v1/owner/ledger-entries/{first['id']}/reversal"
    assert client.post(url, headers=ctx["owner"], json={"reason": ""}).status_code == 422
    assert client.post(url, headers=ctx["staff"], json={"reason": "x"}).status_code == 403
    res = client.post(url, headers=ctx["owner"], json={"reason": "Salah input nominal"})
    assert res.status_code == 201, res.text
    assert res.json()["expense"]["reversed"] is True
    again = client.post(url, headers=ctx["owner"], json={"reason": "lagi"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_reversed"
    revenue = admin_sql(
        "select id from app.ledger_entries where outlet_id = %s and type = 'revenue' limit 1",
        (ctx["outlet"],),
    )[0][0]
    res = client.post(
        f"/api/v1/owner/ledger-entries/{revenue}/reversal",
        headers=ctx["owner"],
        json={"reason": "coba"},
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "not_reversible"


def test_cashflow_report_adds_up_from_the_ledger(client, ctx) -> None:
    today = _today()
    url = f"/api/v1/owner/reports/cashflow?from={today.replace(day=1)}&to={today}"
    assert client.get(url, headers=ctx["staff"]).status_code == 403
    report = client.get(url, headers=ctx["owner"]).json()
    rows = admin_sql(
        "select l.type::text, coalesce(r.type::text, ''), l.payment_method::text,"
        " sum(l.amount)::bigint, sum(l.pb1_portion)::bigint from app.ledger_entries l"
        " left join app.ledger_entries r on r.id = l.reverses_entry_id"
        " where l.tenant_id = %s group by 1, 2, 3",
        (ctx["tenant"],),
    )
    by: dict[str, int] = {}
    for kind, reversed_kind, method, amount, _ in rows:
        key = reversed_kind or kind
        by[key] = by.get(key, 0) + amount
        if key in ("revenue", "pb1", "delivery_fee"):
            by[method] = by.get(method, 0) + amount
    cash_in = by.get("revenue", 0) + by.get("pb1", 0) + by.get("delivery_fee", 0)
    refunds = -by.get("refund", 0)
    expenses = -by.get("expense", 0)
    difference = by.get("cash_shortage", 0) + by.get("cash_surplus", 0)
    b = report["breakdown"]
    assert b["revenue_excl_pb1"] == by.get("revenue", 0)
    assert b["cash"] == by.get("cash", 0) and b["qris"] == by.get("qris", 0)
    assert b["refunds"] == refunds and b["expenses"] == expenses == 1200000 + 880000
    assert b["cash_difference"] == difference == 1000
    t = report["totals"]
    assert t["cash_in"]["amount"] == cash_in
    assert t["cash_out"]["amount"] == refunds + expenses
    assert t["net"]["amount"] == cash_in - refunds - expenses + difference
    assert t["cash_in"]["change_pct"] is None  # nothing in the previous period
    assert report["expenses_by_outlet"] == [
        {"outlet_id": ctx["outlet"], "outlet": "Dago", "amount": expenses, "count": 2}
    ]
    assert report["expenses_count"] == 2
    days = [p["date"] for p in report["series"]]
    assert days[0] == today.replace(day=1).isoformat() and days[-1] == today.isoformat()
    assert sum(p["cash_in"] for p in report["series"]) == cash_in

    weekly = client.get(url + "&granularity=weekly", headers=ctx["owner"]).json()
    assert sum(p["cash_out"] for p in weekly["series"]) == refunds + expenses
    bad = client.get(
        f"/api/v1/owner/reports/cashflow?from={today}&to={today - timedelta(days=1)}",
        headers=ctx["owner"],
    )
    assert bad.status_code == 422


def test_database_refuses_staff_expenses_and_ledger_edits(ctx) -> None:
    """Defense in depth: even a staff session that bypasses the API cannot post an expense,
    and nobody can edit or delete a ledger row (T-044)."""
    assert APP_URL

    def session(user: UUID) -> psycopg.Connection:
        conn = psycopg.connect(APP_URL)
        conn.execute(
            "select set_config('app.tenant_id', %s, true), set_config('app.user_id', %s, true),"
            " set_config('app.actor', 'user', true)",
            (ctx["tenant"], str(user)),
        )
        return conn

    insert = (
        "insert into app.ledger_entries (tenant_id, outlet_id, type, amount, description,"
        " business_date, actor_type, actor_id) values (%s, %s, 'expense', -1000, 'x',"
        " current_date, 'user', %s)"
    )
    with session(STAFF) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(insert, (ctx["tenant"], ctx["outlet"], STAFF))
    with session(OWNER) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "update app.ledger_entries set amount = 1 where tenant_id = %s", (ctx["tenant"],)
            )
        conn.rollback()
        conn.execute(
            "select set_config('app.tenant_id', %s, true), set_config('app.user_id', %s, true),"
            " set_config('app.actor', 'user', true)",
            (ctx["tenant"], str(OWNER)),
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("delete from app.ledger_entries where tenant_id = %s", (ctx["tenant"],))
