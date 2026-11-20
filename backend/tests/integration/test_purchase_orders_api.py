"""Purchase order API tests (T-131) against Postgres through RLS: scheme 1 (pay later) and
scheme 2 (pay in advance), partial delivery and difference found, owner close with a note,
over-receipt, restock in base units, cash from a drawer lowering expected cash, cancellation,
cash basis, and staff limits (own outlets only; no payments, cancel, suppliers) at the API and
in the database.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
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

DOMAIN = "po.test"
OWNER = UUID("60000000-0000-0000-0000-0000000000f0")
STAFF = UUID("60000000-0000-0000-0000-0000000000f1")


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Jakarta")).date()


def _bearer(sub: UUID, tenant: str | None, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=str(sub), tenant_id=tenant, app_role=role)}"}


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid4().hex}


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
        json={"business": {"name": "Kopi PO", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, outlet = res.json()["tenant_id"], res.json()["outlet_id"]
    other = admin_sql(
        "insert into app.outlets (tenant_id, name, order_prefix) values (%s, 'Riau', 'Z')"
        " returning id",
        (tenant,),
    )[0][0]
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
    milk = admin_sql(
        "insert into app.stock_items (tenant_id, name, unit, display_unit)"
        " values (%s, 'Susu UHT PO', 'ml', 'L') returning id",
        (tenant,),
    )[0][0]
    owner = _bearer(OWNER, tenant, "owner")
    supplier = client.post(
        "/api/v1/owner/suppliers",
        headers=owner,
        json={"name": "CV Susu Segar", "phone": "0812 1111 2222"},
    )
    assert supplier.status_code == 201, supplier.text
    drawers = client.get(f"/api/v1/ops/outlets/{outlet}/drawers", headers=owner).json()
    return {
        "tenant": tenant,
        "outlet": outlet,
        "other_outlet": str(other),
        "owner": owner,
        "staff": _bearer(STAFF, tenant, "staff"),
        "supplier": supplier.json()["id"],
        "milk": str(milk),
        "drawer": drawers[0]["drawer"]["id"],
    }


def _on_hand(outlet: str, item: str) -> Decimal:
    rows = admin_sql(
        "select on_hand from app.outlet_stock where outlet_id = %s and stock_item_id = %s",
        (outlet, item),
    )
    return rows[0][0] if rows else Decimal(0)


def _ledger_count(po_id: str) -> int:
    return admin_sql(
        "select count(*) from app.ledger_entries where purchase_order_id = %s", (po_id,)
    )[0][0]


def _open(client: TestClient, ctx: dict[str, Any], who: str = "staff", **over: Any) -> dict:
    outlet = over.pop("outlet", ctx["outlet"])
    body = {
        "supplier_id": ctx["supplier"],
        "ordered_on": str(_today()),
        "payment_term": "pay_later",
        "due_date": str(_today() + timedelta(days=14)),
        "lines": [
            {"stock_item_id": ctx["milk"], "quantity": "20", "unit": "L", "unit_price": 18000},
            {
                "item_name": "Gelas plastik 16oz",
                "quantity": "2",
                "unit": "pak",
                "unit_price": 45000,
            },
        ],
        "note": "Antar pagi",
        **over,
    }
    res = client.post(
        f"/api/v1/ops/outlets/{outlet}/purchase-orders",
        headers={**ctx[who], **_key()},
        json=body,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_scheme_1_pay_later_check_close_then_instalments(client, ctx) -> None:
    before = _on_hand(ctx["outlet"], ctx["milk"])
    po = _open(client, ctx)
    assert po["number"] == "PO-A-0001"
    assert po["total"] == 20 * 18000 + 2 * 45000
    assert po["status"] == "open" and po["goods_status"] == "not_arrived"
    assert po["created_by"] == "Rina"
    assert "amount_owed" not in po or po["amount_owed"] is None  # staff see no debt
    assert po["allowed_actions"] == ["receive"]
    assert _ledger_count(po["id"]) == 0  # cash basis: no entry at open
    assert _on_hand(ctx["outlet"], ctx["milk"]) == before  # no stock at open

    # The owner sees the staff-opened PO in the list, with debt.
    rows = client.get(
        "/api/v1/owner/purchase-orders", headers=ctx["owner"], params={"status": "open"}
    ).json()["items"]
    row = next(r for r in rows if r["id"] == po["id"])
    assert row["amount_owed"] == po["total"] and row["amount_paid"] == 0

    # Paying before goods is allowed for pay later, but the reminder appears only after close.
    waiting = client.get(
        "/api/v1/owner/purchase-orders",
        headers=ctx["owner"],
        params={"status": "awaiting_payment"},
    ).json()["items"]
    assert po["id"] not in {r["id"] for r in waiting}

    milk_line, cups_line = po["lines"]
    res = client.post(
        f"/api/v1/ops/purchase-orders/{po['id']}/receipts",
        headers={**ctx["staff"], **_key()},
        json={
            "received_on": str(_today()),
            "lines": [
                {"line_id": milk_line["id"], "quantity": "20"},
                {"line_id": cups_line["id"], "quantity": "2"},
            ],
        },
    )
    assert res.status_code == 201, res.text
    got = res.json()
    assert got["status"] == "open" and got["goods_status"] == "arrived"
    assert all(line["check"] == "match" for line in got["lines"])
    assert got["allowed_actions"] == ["receive", "close"]
    # 20 L in base units (ml), referencing the PO; the free-text line adds no stock.
    assert _on_hand(ctx["outlet"], ctx["milk"]) == before + 20000
    moved = admin_sql(
        "select quantity, type::text, note from app.stock_movements where purchase_order_id = %s",
        (po["id"],),
    )
    assert moved == [(Decimal("20000.000"), "restock", "PO-A-0001")]

    res = client.post(f"/api/v1/ops/purchase-orders/{po['id']}/close", headers=ctx["staff"])
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "closed"
    assert _ledger_count(po["id"]) == 0  # still nothing at check or close

    waiting = client.get(
        "/api/v1/owner/purchase-orders",
        headers=ctx["owner"],
        params={"status": "awaiting_payment"},
    ).json()["items"]
    assert po["id"] in {r["id"] for r in waiting}

    pay_url = f"/api/v1/owner/purchase-orders/{po['id']}/payments"
    first = {"paid_on": str(_today()), "amount": 200000, "method": "transfer"}
    key = _key()
    res = client.post(pay_url, headers={**ctx["owner"], **key}, json=first)
    assert res.status_code == 201, res.text
    assert res.json()["payment_status"] == "partially_paid"
    assert res.json()["amount_owed"] == po["total"] - 200000
    replay = client.post(pay_url, headers={**ctx["owner"], **key}, json=first)
    assert replay.status_code == 200 and replay.headers["Idempotent-Replay"] == "true"
    assert _ledger_count(po["id"]) == 1

    over = client.post(
        pay_url,
        headers={**ctx["owner"], **_key()},
        json={"paid_on": str(_today()), "amount": po["total"], "method": "cash"},
    )
    assert over.status_code == 409 and over.json()["error"]["code"] == "overpayment"

    rest = client.post(
        pay_url,
        headers={**ctx["owner"], **_key()},
        json={"paid_on": str(_today()), "amount": po["total"] - 200000, "method": "cash"},
    )
    assert rest.status_code == 201, rest.text
    done = rest.json()
    assert done["payment_status"] == "paid" and done["amount_owed"] == 0
    assert done["allowed_actions"] == []
    assert [e["kind"] for e in done["events"]] == ["opened", "received", "closed", "paid", "paid"]
    entries = admin_sql(
        "select amount, type::text, payment_method::text, description, business_date"
        " from app.ledger_entries where purchase_order_id = %s order by id",
        (po["id"],),
    )
    assert entries == [
        (-200000, "expense", "transfer", "PO-A-0001 · CV Susu Segar", _today()),
        (-(po["total"] - 200000), "expense", "cash", "PO-A-0001 · CV Susu Segar", _today()),
    ]
    # Supplier payments cannot be reversed from O9.
    entry_id = admin_sql(
        "select id from app.ledger_entries where purchase_order_id = %s limit 1", (po["id"],)
    )[0][0]
    res = client.post(
        f"/api/v1/owner/ledger-entries/{entry_id}/reversal",
        headers=ctx["owner"],
        json={"reason": "salah"},
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "not_reversible"
    # Staff see the PO without payment rows or debt.
    staff_view = client.get(f"/api/v1/ops/purchase-orders/{po['id']}", headers=ctx["staff"])
    assert staff_view.json()["payment_status"] == "paid"
    assert "paid" not in [e["kind"] for e in staff_view.json()["events"]]
    assert staff_view.json()["amount_owed"] is None


def test_pengeluaran_lists_payments_of_staff_opened_pos(client, ctx) -> None:
    """O9b: a PO opened by staff reaches Pengeluaran only when the owner pays it, as a "po" row
    with the PO, supplier and the staff member who opened it; the summary adds up."""
    po = _open(client, ctx, "staff", note=None)
    assert client.get("/api/v1/owner/expenses", headers=ctx["owner"]).status_code == 200
    assert client.get("/api/v1/owner/expenses/summary", headers=ctx["staff"]).status_code == 403
    by_po = [
        e
        for e in client.get(
            "/api/v1/owner/expenses", headers=ctx["owner"], params={"source": "po", "limit": 100}
        ).json()["items"]
        if e["purchase_order"]["id"] == po["id"]
    ]
    assert by_po == []  # opening a PO posts nothing

    pay = {"paid_on": str(_today()), "amount": 150000, "method": "transfer"}
    res = client.post(
        f"/api/v1/owner/purchase-orders/{po['id']}/payments",
        headers={**ctx["owner"], **_key()},
        json=pay,
    )
    assert res.status_code == 201, res.text

    items = client.get(
        "/api/v1/owner/expenses", headers=ctx["owner"], params={"source": "po", "limit": 100}
    ).json()["items"]
    row = next(e for e in items if e["purchase_order"]["id"] == po["id"])
    assert row["source"] == "po" and row["amount"] == 150000 and row["payment_method"] == "transfer"
    assert row["purchase_order"]["number"] == po["number"]
    assert row["purchase_order"]["supplier"]["name"] == po["supplier"]["name"]
    assert row["purchase_order"]["created_by"] == po["created_by"]
    direct = client.get(
        "/api/v1/owner/expenses", headers=ctx["owner"], params={"source": "direct", "limit": 100}
    ).json()["items"]
    assert all(e["source"] == "direct" and e["purchase_order"] is None for e in direct)

    summary = client.get(
        "/api/v1/owner/expenses/summary",
        headers=ctx["owner"],
        params={"from": str(_today()), "to": str(_today())},
    ).json()
    assert summary["total"]["amount"] == summary["po"]["amount"] + summary["direct"]["amount"]
    assert summary["po"]["amount"] >= 150000
    spend = next(x for x in summary["by_supplier"] if x["supplier"]["id"] == ctx["supplier"])
    assert spend["amount"] >= 150000
    assert set(summary["po_owed"]) == {"amount", "count", "overdue_count"}


def test_scheme_2_pay_in_advance_must_be_paid_before_close(client, ctx) -> None:
    po = _open(
        client,
        ctx,
        who="owner",
        payment_term="pay_in_advance",
        due_date=None,
        expected_date=str(_today() + timedelta(days=3)),
        lines=[
            {"item_name": "Biji kopi Gayo", "quantity": "5", "unit": "kg", "unit_price": 190000}
        ],
    )
    assert po["amount_owed"] == 950000
    assert set(po["allowed_actions"]) == {"receive", "record_payment", "cancel"}
    waiting = client.get(
        "/api/v1/owner/purchase-orders",
        headers=ctx["owner"],
        params={"status": "awaiting_payment"},
    ).json()["items"]
    assert po["id"] in {r["id"] for r in waiting}  # payment request right after open

    line = po["lines"][0]
    res = client.post(
        f"/api/v1/ops/purchase-orders/{po['id']}/receipts",
        headers={**ctx["staff"], **_key()},
        json={"received_on": str(_today()), "lines": [{"line_id": line["id"], "quantity": "5"}]},
    )
    assert res.status_code == 201
    res = client.post(f"/api/v1/ops/purchase-orders/{po['id']}/close", headers=ctx["staff"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "payment_required"

    url = f"/api/v1/owner/purchase-orders/{po['id']}/payments"
    part = client.post(
        url,
        headers={**ctx["owner"], **_key()},
        json={"paid_on": str(_today()), "amount": 500000, "method": "transfer"},
    )
    assert part.status_code == 422  # pay in advance is paid in full
    full = client.post(
        url,
        headers={**ctx["owner"], **_key()},
        json={"paid_on": str(_today()), "amount": 950000, "method": "transfer"},
    )
    assert full.status_code == 201, full.text
    res = client.post(f"/api/v1/ops/purchase-orders/{po['id']}/close", headers=ctx["staff"])
    assert res.status_code == 200 and res.json()["status"] == "closed"


def test_difference_found_staff_refused_owner_closes_with_note(client, ctx) -> None:
    po = _open(client, ctx)
    milk = po["lines"][0]
    url = f"/api/v1/ops/purchase-orders/{po['id']}/receipts"
    res = client.post(
        url,
        headers={**ctx["staff"], **_key()},
        json={
            "received_on": str(_today()),
            "note": "Gelas belum ada",
            "lines": [{"line_id": milk["id"], "quantity": "15"}],
        },
    )
    assert res.status_code == 201
    got = res.json()
    assert got["status"] == "difference_found" and got["goods_status"] == "partly_arrived"
    assert [line["check"] for line in got["lines"]] == ["short", "short"]
    assert got["lines"][0]["remaining_quantity"] == "5.000"

    over = client.post(
        url,
        headers={**ctx["staff"], **_key()},
        json={"received_on": str(_today()), "lines": [{"line_id": milk["id"], "quantity": "6"}]},
    )
    assert over.status_code == 409 and over.json()["error"]["code"] == "over_receipt"

    res = client.post(f"/api/v1/ops/purchase-orders/{po['id']}/close", headers=ctx["staff"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "difference_found"
    res = client.post(
        f"/api/v1/owner/purchase-orders/{po['id']}/close",
        headers=ctx["staff"],
        json={"note": "kurang"},
    )
    assert res.status_code == 403

    listed = client.get(
        "/api/v1/owner/purchase-orders",
        headers=ctx["owner"],
        params={"status": "difference_found"},
    ).json()["items"]
    assert po["id"] in {r["id"] for r in listed}
    detail = client.get(f"/api/v1/owner/purchase-orders/{po['id']}", headers=ctx["owner"]).json()
    assert "close_with_note" in detail["allowed_actions"]
    assert "cancel" not in detail["allowed_actions"]  # goods were received

    res = client.post(
        f"/api/v1/owner/purchase-orders/{po['id']}/close",
        headers=ctx["owner"],
        json={"note": "Supplier tidak kirim sisa susu dan gelas"},
    )
    assert res.status_code == 200, res.text
    closed = res.json()
    assert closed["status"] == "closed"
    assert closed["amount_owed"] == 15 * 18000  # pay later owes received x unit price
    assert closed["events"][-1]["kind"] == "closed"
    assert closed["events"][-1]["data"]["note"].startswith("Supplier")
    res = client.post(
        url,
        headers={**ctx["staff"], **_key()},
        json={"received_on": str(_today()), "lines": [{"line_id": milk["id"], "quantity": "1"}]},
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "po_not_open"


def test_cash_from_drawer_lowers_expected_cash(client, ctx) -> None:
    res = client.post(
        f"/api/v1/ops/drawers/{ctx['drawer']}/shifts",
        headers=ctx["staff"],
        json={"starting_cash": 500000},
    )
    assert res.status_code == 201, res.text
    shift = res.json()["id"]
    po = _open(
        client,
        ctx,
        lines=[{"item_name": "Es batu", "quantity": "3", "unit": "karung", "unit_price": 20000}],
    )
    res = client.post(
        f"/api/v1/owner/purchase-orders/{po['id']}/payments",
        headers={**ctx["owner"], **_key()},
        json={
            "paid_on": str(_today()),
            "amount": 60000,
            "method": "transfer",
            "drawer_id": ctx["drawer"],
        },
    )
    assert res.status_code == 422  # only cash comes out of a drawer
    res = client.post(
        f"/api/v1/owner/purchase-orders/{po['id']}/payments",
        headers={**ctx["owner"], **_key()},
        json={
            "paid_on": str(_today()),
            "amount": 60000,
            "method": "cash",
            "drawer_id": ctx["drawer"],
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["events"][-1]["data"]["from_drawer"] is True
    res = client.post(
        f"/api/v1/ops/shifts/{shift}/close",
        headers={**ctx["staff"], **_key()},
        json={"count_breakdown": {"100000": 4, "20000": 2}},
    )
    assert res.status_code == 200, res.text
    closed = res.json()
    assert closed["cash_paid_out"] == 60000
    assert closed["expected_cash"] == 500000 - 60000
    assert closed["difference"] == 0


def test_cancel_rules(client, ctx) -> None:
    po = _open(client, ctx)
    url = f"/api/v1/owner/purchase-orders/{po['id']}/cancel"
    assert client.post(url, headers=ctx["staff"], json={"reason": "x"}).status_code == 403
    assert client.post(url, headers=ctx["owner"], json={"reason": " "}).status_code == 422
    res = client.post(url, headers=ctx["owner"], json={"reason": "Salah supplier"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled" and res.json()["allowed_actions"] == []
    assert res.json()["amount_owed"] == 0
    again = client.post(url, headers=ctx["owner"], json={"reason": "lagi"})
    assert again.status_code == 409

    paid = _open(client, ctx)
    client.post(
        f"/api/v1/owner/purchase-orders/{paid['id']}/payments",
        headers={**ctx["owner"], **_key()},
        json={"paid_on": str(_today()), "amount": 1000, "method": "transfer"},
    )
    res = client.post(
        f"/api/v1/owner/purchase-orders/{paid['id']}/cancel",
        headers=ctx["owner"],
        json={"reason": "batal"},
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "not_cancellable"


def test_validation(client, ctx) -> None:
    url = f"/api/v1/ops/outlets/{ctx['outlet']}/purchase-orders"
    base = {
        "supplier_id": ctx["supplier"],
        "ordered_on": str(_today()),
        "payment_term": "pay_later",
        "due_date": str(_today() + timedelta(days=7)),
        "lines": [{"stock_item_id": ctx["milk"], "quantity": "1", "unit": "kg", "unit_price": 1}],
    }
    res = client.post(url, headers=ctx["owner"], json=base)
    assert res.status_code == 422 and res.json()["error"]["details"]["field"] == "lines.0.unit"
    no_due = {**base, "due_date": None, "lines": [{**base["lines"][0], "unit": "L"}]}
    res = client.post(url, headers=ctx["owner"], json=no_due)
    assert res.status_code == 422 and res.json()["error"]["details"]["field"] == "due_date"
    future = {**no_due, "due_date": base["due_date"], "ordered_on": str(_today() + timedelta(1))}
    res = client.post(url, headers=ctx["owner"], json=future)
    assert res.status_code == 422


def test_staff_limits_at_the_api(client, ctx) -> None:
    other = client.post(
        f"/api/v1/ops/outlets/{ctx['other_outlet']}/purchase-orders",
        headers=ctx["staff"],
        json={
            "supplier_id": ctx["supplier"],
            "ordered_on": str(_today()),
            "payment_term": "pay_later",
            "due_date": str(_today()),
            "lines": [{"item_name": "X", "quantity": "1", "unit": "pcs", "unit_price": 1000}],
        },
    )
    assert other.status_code == 404  # not an assigned outlet
    owner_po = _open(client, ctx, who="owner", outlet=ctx["other_outlet"])
    assert owner_po["number"] == "PO-Z-0001"  # numbered per outlet
    assert (
        client.get(
            f"/api/v1/ops/purchase-orders/{owner_po['id']}", headers=ctx["staff"]
        ).status_code
        == 404
    )
    for method, path, body in (
        ("get", "/api/v1/owner/suppliers", None),
        ("post", "/api/v1/owner/suppliers", {"name": "Nope"}),
        ("get", "/api/v1/owner/purchase-orders", None),
        (
            "post",
            f"/api/v1/owner/purchase-orders/{owner_po['id']}/payments",
            {"paid_on": str(_today()), "amount": 1, "method": "cash"},
        ),
    ):
        res = client.request(method, path, headers=ctx["staff"], json=body)
        assert res.status_code == 403, (path, res.text)
    options = client.get("/api/v1/ops/suppliers", headers=ctx["staff"])
    assert options.status_code == 200
    assert {"id": ctx["supplier"], "name": "CV Susu Segar"} in options.json()


def test_database_refuses_staff_money_changes(client, ctx) -> None:
    po = _open(client, ctx)

    def as_staff(sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        assert APP_URL
        with psycopg.connect(APP_URL) as conn, conn.transaction():
            conn.execute(
                "select set_config('app.tenant_id', %s, true), set_config('app.user_id', %s, true),"
                " set_config('app.actor', 'user', true)",
                (ctx["tenant"], str(STAFF)),
            )
            cur = conn.execute(sql, params)
            return cur.fetchall() if cur.description else []

    for sql in (
        "update app.purchase_orders set amount_paid = 1, payment_status = 'partially_paid'"
        " where id = %s",
        "update app.purchase_orders set status = 'cancelled', cancelled_at = now(),"
        " cancelled_by = created_by, cancel_reason = 'x' where id = %s",
        "update app.purchase_order_lines set unit_price = 1 where purchase_order_id = %s",
    ):
        with pytest.raises(psycopg.Error):
            as_staff(sql, (po["id"],))
    # RLS hides supplier payments from staff (debt is owner-only).
    client.post(
        f"/api/v1/owner/purchase-orders/{po['id']}/payments",
        headers={**ctx["owner"], **_key()},
        json={"paid_on": str(_today()), "amount": 1000, "method": "transfer"},
    )
    assert as_staff(
        "select count(*) from app.purchase_order_payments where purchase_order_id = %s",
        (po["id"],),
    ) == [(0,)]
    with pytest.raises(psycopg.Error):
        as_staff(
            "insert into app.suppliers (tenant_id, name) values (%s, 'Staff supplier')",
            (ctx["tenant"],),
        )
