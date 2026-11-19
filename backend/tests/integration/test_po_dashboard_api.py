"""Dashboard tab "PO & Supplier" — O17 cards and the O15 drill-down filters (T-128).

Modeled on AC3.12 (Pembayaran supplier, debt, overdue first), AC3.14 (Ringkasan PO for one
outlet and month, "partly paid" lists only that PO), AC3.9 (goods paid for but not received)
and AC4.10 (PO ada selisih with the shortfall). The month filters Ringkasan PO only; the
payment and difference cards list every PO that needs action (FR3.11, FR3.12).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
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

DOMAIN = "podash.test"
OWNER = UUID("61000000-0000-0000-0000-0000000000f0")
STAFF = UUID("61000000-0000-0000-0000-0000000000f1")

TODAY = datetime.now(ZoneInfo("Asia/Jakarta")).date()
THIS_MONTH = TODAY.strftime("%Y-%m")
PREV_START = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)
PREV_MONTH = PREV_START.strftime("%Y-%m")


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


class Book:
    """Opens, receives, closes, pays and cancels POs for one tenant as the owner."""

    def __init__(self, client: TestClient, owner: dict[str, str], outlet: str, supplier: str):
        self.c, self.owner, self.outlet, self.supplier = client, owner, outlet, supplier

    def open(
        self,
        price: int,
        *,
        qty: str = "10",
        term: str = "pay_later",
        ordered_on: date = TODAY,
        due: date | None = None,
    ) -> dict[str, Any]:
        dates = (
            {"due_date": str(due or TODAY + timedelta(days=14))}
            if term == "pay_later"
            else {"expected_date": str(due or ordered_on)}
        )
        res = self.c.post(
            f"/api/v1/ops/outlets/{self.outlet}/purchase-orders",
            headers={**self.owner, **_key()},
            json={
                "supplier_id": self.supplier,
                "ordered_on": str(ordered_on),
                "payment_term": term,
                "lines": [
                    {"item_name": "Gelas", "quantity": qty, "unit": "pak", "unit_price": price}
                ],
                **dates,
            },
        )
        assert res.status_code == 201, res.text
        return res.json()

    def receive(self, po: dict[str, Any], qty: str, on: date = TODAY) -> dict[str, Any]:
        res = self.c.post(
            f"/api/v1/ops/purchase-orders/{po['id']}/receipts",
            headers={**self.owner, **_key()},
            json={
                "received_on": str(on),
                "lines": [{"line_id": po["lines"][0]["id"], "quantity": qty}],
            },
        )
        assert res.status_code == 201, res.text
        return res.json()

    def close(self, po: dict[str, Any]) -> None:
        res = self.c.post(f"/api/v1/ops/purchase-orders/{po['id']}/close", headers=self.owner)
        assert res.status_code == 200, res.text

    def pay(self, po: dict[str, Any], amount: int, on: date = TODAY) -> None:
        res = self.c.post(
            f"/api/v1/owner/purchase-orders/{po['id']}/payments",
            headers={**self.owner, **_key()},
            json={"paid_on": str(on), "amount": amount, "method": "transfer"},
        )
        assert res.status_code == 201, res.text

    def cancel(self, po: dict[str, Any]) -> None:
        res = self.c.post(
            f"/api/v1/owner/purchase-orders/{po['id']}/cancel",
            headers=self.owner,
            json={"reason": "salah supplier"},
        )
        assert res.status_code == 200, res.text


@pytest.fixture(scope="module")
def ctx(client: TestClient) -> dict[str, Any]:
    res = client.post(
        "/api/v1/owner/onboarding",
        headers=_bearer(OWNER, None, "owner_pending"),
        json={"business": {"name": "Kopi Dash", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, outlet = res.json()["tenant_id"], res.json()["outlet_id"]
    other = admin_sql(
        "insert into app.outlets (tenant_id, name, order_prefix) values (%s, 'Riau', 'R')"
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
    owner = _bearer(OWNER, tenant, "owner")
    supplier = client.post(
        "/api/v1/owner/suppliers", headers=owner, json={"name": "Toko Susu Segar"}
    ).json()["id"]
    book = Book(client, owner, outlet, supplier)

    # This month (AC3.14): 2 open with nothing, 1 with a difference, 3 closed (pay in advance
    # paid, pay later paid in full, pay later Rp160.000 of Rp360.000 paid), 1 cancelled.
    pos: dict[str, dict[str, Any]] = {}
    pos["open1"] = book.open(10_000)
    pos["open2"] = book.open(10_000)
    pos["short"] = book.open(10_000)
    book.receive(pos["short"], "4")
    pos["advance_closed"] = book.open(20_000, term="pay_in_advance")
    book.pay(pos["advance_closed"], 200_000)
    book.receive(pos["advance_closed"], "10")
    book.close(pos["advance_closed"])
    pos["later_paid"] = book.open(10_000)
    book.receive(pos["later_paid"], "10")
    book.close(pos["later_paid"])
    book.pay(pos["later_paid"], 100_000)
    pos["later_part"] = book.open(36_000, due=TODAY + timedelta(days=5))
    book.receive(pos["later_part"], "10")
    book.close(pos["later_part"])
    book.pay(pos["later_part"], 200_000)
    pos["cancelled"] = book.open(99_000)
    book.cancel(pos["cancelled"])

    # Last month: an overdue closed pay-later PO, an unpaid pay-in-advance PO, and a paid
    # pay-in-advance PO still waiting for its goods.
    pos["overdue"] = book.open(10_000, qty="5", ordered_on=PREV_START, due=PREV_START)
    book.receive(pos["overdue"], "5", on=PREV_START)
    book.close(pos["overdue"])
    pos["advance_unpaid"] = book.open(
        7_000, term="pay_in_advance", ordered_on=PREV_START, due=PREV_START + timedelta(days=1)
    )
    pos["advance_waiting"] = book.open(8_000, term="pay_in_advance", ordered_on=PREV_START)
    book.pay(pos["advance_waiting"], 80_000, on=PREV_START)
    # Past its due date but not closed: no reminder yet, so not overdue anywhere (FR3.7).
    pos["open_late"] = book.open(3_000, ordered_on=PREV_START, due=PREV_START)
    return {
        "outlet": outlet,
        "other_outlet": str(other),
        "owner": owner,
        "staff": _bearer(STAFF, tenant, "staff"),
        "pos": pos,
    }


def _dashboard(client: TestClient, ctx: dict[str, Any], **params: str) -> dict[str, Any]:
    res = client.get(
        "/api/v1/owner/dashboard/purchase-orders",
        headers=ctx["owner"],
        params={"outlet_id": ctx["outlet"], **params},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _list(client: TestClient, ctx: dict[str, Any], **params: str) -> set[str]:
    res = client.get(
        "/api/v1/owner/purchase-orders",
        headers=ctx["owner"],
        params={"outlet_id": ctx["outlet"], **params},
    )
    assert res.status_code == 200, res.text
    return {r["id"] for r in res.json()["items"]}


def b(count: int, amount: int) -> dict[str, int]:
    return {"count": count, "amount": amount}


def test_ringkasan_po_counts_this_month_by_open_date(client, ctx) -> None:
    summary = _dashboard(client, ctx)["po_summary"]  # default month = this month (WIB)
    assert summary == {
        "month": THIS_MONTH,
        "total": b(6, 960_000),
        "status": {"open": b(3, 300_000), "closed": b(3, 660_000)},
        "goods": {
            "not_arrived": b(2, 200_000),
            "partly_arrived": b(1, 100_000),
            "arrived": b(3, 660_000),
        },
        # unpaid: still owed; partly paid: the rest still owed; paid: amount paid.
        "payment": {
            "unpaid": b(3, 300_000),
            "partially_paid": b(1, 160_000),
            "paid": b(2, 300_000),
        },
        "by_term": {"pay_later": b(5, 760_000), "pay_in_advance": b(1, 200_000)},
    }
    last = _dashboard(client, ctx, month=PREV_MONTH)["po_summary"]
    assert last["total"] == b(4, 50_000 + 70_000 + 80_000 + 30_000)


def test_pembayaran_supplier_ignores_the_month(client, ctx) -> None:
    pos = ctx["pos"]
    for month in (THIS_MONTH, PREV_MONTH):
        card = _dashboard(client, ctx, month=month)["supplier_payments"]
        # Overdue first, then the nearest due / expected date.
        assert [i["po_id"] for i in card["items"]] == [
            pos["overdue"]["id"],
            pos["advance_unpaid"]["id"],
            pos["later_part"]["id"],
        ]
        assert [i["reason"] for i in card["items"]] == ["overdue", "pay_in_advance", "due"]
        assert card["items"][0]["days_overdue"] == (TODAY - PREV_START).days
        assert card["items"][2]["amount_owed"] == 160_000
        # Debt = closed pay-later POs still owed (AC3.12); unpaid pay-in-advance isn't debt.
        assert card["debt_total"] == 160_000 + 50_000
        assert card["overdue_count"] == 1
        assert (card["due_7d_amount"], card["due_7d_count"]) == (160_000, 1)
        # Paid for, not received (AC3.9): the closed pay-in-advance PO no longer counts.
        assert (card["prepaid_not_received"], card["prepaid_not_received_count"]) == (80_000, 1)


def test_po_ada_selisih_lists_the_shortfall(client, ctx) -> None:
    diffs = _dashboard(client, ctx, month=PREV_MONTH)["po_differences"]
    assert len(diffs) == 1
    diff = diffs[0]
    assert diff["po_id"] == ctx["pos"]["short"]["id"]
    assert diff["number"] == ctx["pos"]["short"]["number"]
    assert diff["short_lines"] == [
        {"item": "Gelas", "ordered": "10.000", "received": "4.000", "short": "6.000", "unit": "pak"}
    ]
    assert diff["last_received_on"] == str(TODAY)
    assert diff["days_since_last_received"] == 0


def test_each_ringkasan_figure_lists_exactly_its_pos(client, ctx) -> None:
    pos = {k: v["id"] for k, v in ctx["pos"].items()}
    m = {"month": THIS_MONTH}
    assert _list(client, ctx, **m, payment="partially_paid") == {pos["later_part"]}  # AC3.14
    assert _list(client, ctx, **m, state="open") == {pos["open1"], pos["open2"], pos["short"]}
    assert _list(client, ctx, **m, state="closed") == {
        pos["advance_closed"],
        pos["later_paid"],
        pos["later_part"],
    }
    assert _list(client, ctx, **m, goods="partly_arrived") == {pos["short"]}
    assert _list(client, ctx, **m, goods="not_arrived") == {pos["open1"], pos["open2"]}
    assert _list(client, ctx, **m, term="pay_in_advance") == {pos["advance_closed"]}
    assert _list(client, ctx, **m, payment="unpaid") == {pos["open1"], pos["open2"], pos["short"]}
    # Like the report, the drill-down leaves cancelled POs out; "Semua" still shows them.
    assert pos["cancelled"] not in _list(client, ctx, **m)
    assert pos["cancelled"] in _list(client, ctx)
    assert _list(client, ctx, month=PREV_MONTH) == {
        pos["overdue"],
        pos["advance_unpaid"],
        pos["advance_waiting"],
        pos["open_late"],
    }


def _rows(client: TestClient, ctx: dict[str, Any], **params: str) -> list[dict[str, Any]]:
    res = client.get(
        "/api/v1/owner/purchase-orders",
        headers=ctx["owner"],
        params={"outlet_id": ctx["outlet"], "limit": "100", **params},
    )
    assert res.status_code == 200, res.text
    return res.json()["items"]


def test_every_ringkasan_bucket_matches_its_drill_down(client, ctx) -> None:
    """The report (SQL aggregate) and the list (row filters + Python goods_status) must never
    disagree: each bucket's count equals its drill-down list, and the rows carry that value."""
    for month in (THIS_MONTH, PREV_MONTH):
        summary = _dashboard(client, ctx, month=month)["po_summary"]
        for param, group, field in (
            ("state", "status", None),
            ("goods", "goods", "goods_status"),
            ("payment", "payment", "payment_status"),
            ("term", "by_term", "payment_term"),
        ):
            for value, bucket in summary[group].items():
                rows = _rows(client, ctx, month=month, **{param: value})
                assert len(rows) == bucket["count"], (month, param, value)
                if field:
                    assert {r[field] for r in rows} <= {value}, (month, param, value)
                if group != "payment":  # payment amounts are owed/paid, not the PO total
                    assert sum(r["total"] for r in rows) == bucket["amount"], (month, param, value)


def test_overdue_chip_badge_and_card_agree(client, ctx) -> None:
    pos = ctx["pos"]
    card = _dashboard(client, ctx)["supplier_payments"]
    chip = _rows(client, ctx, status="overdue")
    assert [r["id"] for r in chip] == [pos["overdue"]["id"]]
    assert card["overdue_count"] == len(chip)
    flags = {r["id"]: r["overdue"] for r in _rows(client, ctx)}
    assert flags[pos["overdue"]["id"]] is True
    assert flags[pos["open_late"]["id"]] is False  # open: no reminder yet


def test_outlet_filter_validation_and_staff_refused(client, ctx) -> None:
    other = client.get(
        "/api/v1/owner/dashboard/purchase-orders",
        headers=ctx["owner"],
        params={"outlet_id": ctx["other_outlet"]},
    ).json()
    assert other["po_summary"]["total"] == b(0, 0)
    assert other["supplier_payments"]["items"] == [] and other["po_differences"] == []
    everywhere = client.get("/api/v1/owner/dashboard/purchase-orders", headers=ctx["owner"])
    assert everywhere.json()["po_summary"]["total"] == b(6, 960_000)

    for bad in ("2026-13", "2026-1", "nov", "9999-12", "0000-01"):
        res = client.get(
            "/api/v1/owner/dashboard/purchase-orders",
            headers=ctx["owner"],
            params={"month": bad},
        )
        assert res.status_code == 422, bad
        listed = client.get(
            "/api/v1/owner/purchase-orders", headers=ctx["owner"], params={"month": bad}
        )
        assert listed.status_code == 422, bad
    for path in ("/api/v1/owner/dashboard/purchase-orders", "/api/v1/owner/purchase-orders"):
        assert client.get(path, headers=ctx["staff"]).status_code == 403
