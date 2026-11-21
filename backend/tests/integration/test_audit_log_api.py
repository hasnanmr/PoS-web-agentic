"""O11 audit log `GET /owner/audit-log` (T-101) against Postgres through RLS: order
reversals, status and payment changes, newest first, with outlet / staff / kind / date
filters, cursor paging, owner only.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timedelta
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

DOMAIN = "o11audit.test"
OWNER = UUID("50000000-0000-0000-0000-000000001100")
RINA = UUID("50000000-0000-0000-0000-000000001101")
KETUT = UUID("50000000-0000-0000-0000-000000001102")
URL = "/api/v1/owner/audit-log"


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


def _staff(tenant: str, user: UUID, name: str, outlet: str) -> None:
    email = f"{name.lower()}@{DOMAIN}"
    admin_sql("insert into auth.users (id, email) values (%s, %s)", (user, email))
    admin_sql(
        "insert into app.users (id, tenant_id, email, display_name, role,"
        " invitation_accepted_at) values (%s, %s, %s, %s, 'staff', now())",
        (user, tenant, email, name),
    )
    admin_sql(
        "insert into app.staff_outlets (user_id, outlet_id, tenant_id) values (%s, %s, %s)",
        (user, outlet, tenant),
    )


@pytest.fixture(scope="module")
def ctx(client: TestClient) -> dict[str, Any]:
    res = client.post(
        "/api/v1/owner/onboarding",
        headers=_bearer(OWNER, None, "owner_pending"),
        json={"business": {"name": "Kopi Audit", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, dago = res.json()["tenant_id"], res.json()["outlet_id"]
    owner = _bearer(OWNER, tenant, "owner")
    res = client.post(
        "/api/v1/owner/outlets",
        headers=owner,
        json={"name": "Canggu", "timezone": "Asia/Makassar"},
    )
    assert res.status_code == 201, res.text
    canggu = res.json()["id"]
    _staff(tenant, RINA, "Rina", dago)
    _staff(tenant, KETUT, "Ketut", canggu)
    return {"tenant": tenant, "dago": dago, "canggu": canggu, "owner": owner,
            "staff": _bearer(RINA, tenant, "staff")}  # fmt: skip


def _order(ctx: dict[str, Any], outlet: str) -> tuple[str, str]:
    prefix, number = admin_sql(
        "select o.order_prefix, coalesce(max(r.order_no), 1000) + 1 from app.outlets o"
        " left join app.orders r on r.outlet_id = o.id where o.id = %s group by o.order_prefix",
        (outlet,),
    )[0]
    order = admin_sql(
        "insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode,"
        " status, payment_status, subtotal, total, created_by_actor)"
        " values (%s, %s, %s, 'counter', 'takeaway', 'pay_first', 'completed', 'paid', 1, 1,"
        " 'system') returning id",
        (ctx["tenant"], outlet, number),
    )[0][0]
    return str(order), f"#{prefix}-{number}"


def _event(ctx: dict[str, Any], outlet: str, order: str, event: str, at: str, **kw: Any) -> None:
    actor = kw.get("actor")
    admin_sql(
        "insert into app.order_events (tenant_id, outlet_id, order_id, event, from_status,"
        " to_status, from_payment, to_payment, reason, data, actor_type, actor_id, created_at)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            ctx["tenant"], outlet, order, event, kw.get("from_status"), kw.get("to_status"),
            kw.get("from_payment"), kw.get("to_payment"), kw.get("reason"),
            json.dumps(kw.get("data", {})), "user" if actor else "system", actor, at,
        ),
    )  # fmt: skip


def _today_at(hour: int, minute: int, tz: str = "Asia/Jakarta", days: int = 0) -> str:
    # The calendar day is always Jakarta's (what the API's default range uses), so the
    # result does not depend on which timezone is already past midnight when CI runs.
    day = datetime.now(ZoneInfo("Asia/Jakarta")).date() - timedelta(days=days)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(tz)).isoformat()


@pytest.fixture(scope="module")
def seeded(ctx: dict[str, Any]) -> dict[str, Any]:
    d1, n1 = _order(ctx, ctx["dago"])
    d2, n2 = _order(ctx, ctx["dago"])
    c1, n3 = _order(ctx, ctx["canggu"])
    _event(ctx, ctx["dago"], d1, "created", _today_at(9, 0), to_status="confirmed", actor=RINA)
    _event(ctx, ctx["dago"], d1, "status_changed", _today_at(9, 30), from_status="confirmed",
           to_status="preparing", actor=RINA)  # fmt: skip
    _event(ctx, ctx["dago"], d1, "payment_changed", _today_at(9, 31), from_payment="unpaid",
           to_payment="paid", data={"method": "qris"}, actor=RINA)  # fmt: skip
    _event(ctx, ctx["dago"], d2, "proof_rejected", _today_at(10, 22), from_status="pending_payment",
           to_status="cancelled", from_payment="proof_submitted", to_payment="unpaid",
           reason="Dana tidak ditemukan di merchant", actor=RINA)  # fmt: skip
    _event(ctx, ctx["dago"], d2, "status_changed", _today_at(9, 55), from_status="pending_payment",
           to_status="cancelled", reason="Tidak ada bukti bayar 15 mnt")  # fmt: skip
    _event(ctx, ctx["dago"], d1, "reversed", _today_at(10, 40), from_status="completed",
           to_status="cancelled", from_payment="paid", to_payment="refunded",
           reason="Salah input item, tamu batal", data={"ingredients": "waste"},
           actor=OWNER)  # fmt: skip
    _event(ctx, ctx["canggu"], c1, "reversed", _today_at(21, 12, "Asia/Makassar", days=1),
           from_status="completed", to_status="cancelled", from_payment="paid",
           to_payment="refunded", reason="Pelanggan komplain rasa", actor=KETUT)  # fmt: skip
    return {"dago_1": n1, "dago_2": n2, "canggu_1": n3}


def _get(client: TestClient, ctx: dict[str, Any], **params: Any) -> dict[str, Any]:
    res = client.get(URL, headers=ctx["owner"], params=params)
    assert res.status_code == 200, res.text
    return res.json()


def test_lists_changes_newest_first_with_change_text_and_actor(client, ctx, seeded) -> None:
    today = datetime.now(ZoneInfo("Asia/Jakarta")).date()
    yesterday = today - timedelta(days=1)
    body = _get(client, ctx, **{"from": yesterday.isoformat(), "to": today.isoformat()})
    rows = body["items"]
    assert [(r["order_no"], r["kind"], r["change"]) for r in rows] == [
        (seeded["dago_1"], "reversal", "paid → refunded · bahan → waste"),
        (seeded["dago_2"], "payment", "proof rejected"),
        (seeded["dago_2"], "status", "pending_payment → cancelled"),
        (seeded["dago_1"], "payment", "marked paid (QRIS)"),
        (seeded["dago_1"], "status", "confirmed → preparing"),
        (seeded["canggu_1"], "reversal", "paid → refunded"),
    ]  # "created" is history, not a change
    top = rows[0]
    assert top["actor"] == {"type": "user", "id": str(OWNER), "name": top["actor"]["name"],
                            "role": "owner"}  # fmt: skip
    assert top["reason"] == "Salah input item, tamu batal"
    assert top["timezone"] == "Asia/Jakarta"
    assert rows[2]["actor"] == {"type": "system", "id": None, "name": None, "role": None}
    assert rows[5]["actor"]["name"] == "Ketut" and rows[5]["timezone"] == "Asia/Makassar"
    assert body["next_cursor"] is None


def test_filters_by_outlet_staff_kind_and_date(client, ctx, seeded) -> None:
    today = datetime.now(ZoneInfo("Asia/Jakarta")).date()
    span = {"from": (today - timedelta(days=1)).isoformat(), "to": today.isoformat()}
    canggu = _get(client, ctx, outlet_id=ctx["canggu"], **span)["items"]
    assert [r["order_no"] for r in canggu] == [seeded["canggu_1"]]
    rina = _get(client, ctx, actor_id=str(RINA), **span)["items"]
    assert {r["actor"]["name"] for r in rina} == {"Rina"} and len(rina) == 3
    kinds = _get(client, ctx, kind="reversal,payment", **span)["items"]
    assert {r["kind"] for r in kinds} == {"reversal", "payment"} and len(kinds) == 4
    # Default range is month to date; yesterday's Canggu row drops out on the 1st only.
    default = _get(client, ctx)
    assert default["date_from"] == today.replace(day=1).isoformat()
    assert len(default["items"]) == (5 if today.day == 1 else 6)
    only_today = _get(client, ctx, **{"from": today.isoformat(), "to": today.isoformat()})
    assert seeded["canggu_1"] not in [r["order_no"] for r in only_today["items"]]


def test_cursor_pages_of_50_without_gaps(client, ctx, seeded) -> None:
    order, _ = _order(ctx, ctx["dago"])
    day = datetime.now(ZoneInfo("Asia/Jakarta")).date() - timedelta(days=40)
    admin_sql(
        "insert into app.order_events (tenant_id, outlet_id, order_id, event, from_status,"
        " to_status, actor_type, actor_id, created_at)"
        " select %s, %s, %s, 'status_changed', 'confirmed', 'preparing', 'user', %s,"
        " (%s::date + time '09:00') at time zone 'Asia/Jakarta' + g * interval '1 minute'"
        " from generate_series(1, 55) g",
        (ctx["tenant"], ctx["dago"], order, RINA, day),
    )
    span = {"from": day.isoformat(), "to": day.isoformat()}
    first = _get(client, ctx, **span)
    assert len(first["items"]) == 50 and first["next_cursor"]
    second = _get(client, ctx, cursor=first["next_cursor"], **span)
    assert len(second["items"]) == 5 and second["next_cursor"] is None
    ids = [r["id"] for r in first["items"] + second["items"]]
    assert len(set(ids)) == 55 and ids == sorted(ids, reverse=True)
    assert client.get(URL, headers=ctx["owner"], params={"limit": 2}).json()["items"] != []


def test_owner_only_and_validation(client, ctx, seeded) -> None:
    assert client.get(URL, headers=ctx["staff"]).status_code == 403
    assert client.get(URL, headers=ctx["owner"], params={"kind": "created"}).status_code == 422
    assert client.get(URL, headers=ctx["owner"], params={"cursor": "nope"}).status_code == 422
    bad = client.get(URL, headers=ctx["owner"], params={"from": "2026-11-10", "to": "2026-11-01"})
    assert bad.status_code == 422
    other = "00000000-0000-0000-0000-000000000099"
    assert client.get(URL, headers=ctx["owner"], params={"outlet_id": other}).status_code == 404
