"""PoC demo QRIS against Postgres through RLS: the outlet's static QRIS (O3 upload, shown in
S1/S5) and the staff cross-check of QRIS payments from the Order Board (S2 "Cek →").
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

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

DOMAIN = "qris.test"
OWNER = UUID("60000000-0000-0000-0000-0000000000a0")
STAFF = UUID("60000000-0000-0000-0000-0000000000a1")
OTHER_OWNER = UUID("60000000-0000-0000-0000-0000000000b0")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _bearer(sub: UUID, tenant: str | None, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=str(sub), tenant_id=tenant, app_role=role)}"}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    cleanup_domain(DOMAIN)
    invite_owner(OWNER, f"owner@{DOMAIN}")
    invite_owner(OTHER_OWNER, f"other@{DOMAIN}")
    with TestClient(
        create_app(Settings(database_url=APP_URL), token_verifier=make_verifier())
    ) as c:
        yield c
    cleanup_domain(DOMAIN)


def _onboard(client: TestClient, owner: UUID, name: str) -> tuple[str, str]:
    res = client.post(
        "/api/v1/owner/onboarding",
        headers=_bearer(owner, None, "owner_pending"),
        json={"business": {"name": name, "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    return res.json()["tenant_id"], res.json()["outlet_id"]


@pytest.fixture(scope="module")
def ctx(client: TestClient) -> dict[str, Any]:
    tenant, outlet = _onboard(client, OWNER, "Kopi QRIS")
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
    admin_sql(
        "insert into app.tables (tenant_id, outlet_id, name, capacity, area)"
        " values (%s, %s, 'M01', 4, 'Indoor')",
        (tenant, outlet),
    )
    owner = _bearer(OWNER, tenant, "owner")
    res = client.patch(
        f"/api/v1/owner/outlets/{outlet}", headers=owner, json={"payment_mode": "open_bill"}
    )
    assert res.status_code == 200, res.text
    staff = _bearer(STAFF, tenant, "staff")
    menu = client.get(f"/api/v1/ops/outlets/{outlet}/menu", headers=staff).json()
    tables = client.get(f"/api/v1/ops/outlets/{outlet}/tables", headers=staff).json()
    other_tenant, other_outlet = _onboard(client, OTHER_OWNER, "Kopi Lain")
    return {
        "tenant": tenant,
        "outlet": outlet,
        "owner": owner,
        "staff": staff,
        "product": next(m for m in menu if m["name"] == "Americano")["product_id"],
        "table": tables[0]["id"],
        "other_owner": _bearer(OTHER_OWNER, other_tenant, "owner"),
        "other_outlet": other_outlet,
    }


def _upload(client, headers, outlet, data, content_type, filename="qris-dago.png"):
    return client.put(
        f"/api/v1/owner/outlets/{outlet}/qris?filename={filename}",
        headers={**headers, "Content-Type": content_type},
        content=data,
    )


def _qris_order(client: TestClient, ctx: dict[str, Any]) -> dict[str, Any]:
    res = client.post(
        f"/api/v1/ops/outlets/{ctx['outlet']}/orders",
        headers=ctx["staff"],
        json={
            "type": "takeaway",
            "items": [{"product_id": ctx["product"], "quantity": 1}],
            "payment": {"method": "qris"},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _card(client: TestClient, ctx: dict[str, Any], order_id: str) -> dict[str, Any]:
    board = client.get(f"/api/v1/ops/outlets/{ctx['outlet']}/orders/board", headers=ctx["staff"])
    assert board.status_code == 200, board.text
    return next(c for col in board.json().values() for c in col if c["id"] == order_id)


# O3 · QRIS statis outlet ---------------------------------------------------------------------


def test_owner_uploads_static_qris_and_staff_can_show_it(client, ctx) -> None:
    url = f"/api/v1/owner/outlets/{ctx['outlet']}/qris"
    assert client.get(url, headers=ctx["owner"]).json() == {"image": None}
    image_url = f"/api/v1/ops/outlets/{ctx['outlet']}/qris/image"
    assert client.get(image_url, headers=ctx["staff"]).status_code == 404

    assert _upload(client, ctx["staff"], ctx["outlet"], PNG, "image/png").status_code == 403
    bad = _upload(client, ctx["owner"], ctx["outlet"], b"GIF89a....", "image/png")
    assert bad.status_code == 422 and bad.json()["error"]["details"]["field"] == "image"
    big = _upload(
        client, ctx["owner"], ctx["outlet"], PNG + b"\x00" * (2 * 1024 * 1024), "image/png"
    )
    assert big.status_code == 422, big.text

    res = _upload(client, ctx["owner"], ctx["outlet"], PNG, "image/png")
    assert res.status_code == 200, res.text
    image = res.json()["image"]
    assert image["filename"] == "qris-dago.png" and image["size"] == len(PNG)
    assert client.get(url, headers=ctx["owner"]).json()["image"]["filename"] == "qris-dago.png"
    shown = client.get(image_url, headers=ctx["staff"])
    assert shown.status_code == 200 and shown.headers["content-type"] == "image/png"
    assert shown.content == PNG

    # "Ganti gambar" replaces it.
    res = _upload(client, ctx["owner"], ctx["outlet"], JPG, "image/jpeg", "baru.jpg")
    assert res.status_code == 200 and res.json()["image"]["content_type"] == "image/jpeg"
    assert client.get(image_url, headers=ctx["staff"]).content == JPG

    # Another tenant can neither read nor replace it.
    other = client.get(image_url, headers=ctx["other_owner"])
    assert other.status_code in (403, 404)
    assert _upload(client, ctx["other_owner"], ctx["outlet"], PNG, "image/png").status_code in (
        403,
        404,
    )


def test_database_refuses_staff_writing_the_qris(ctx) -> None:
    assert APP_URL
    with psycopg.connect(APP_URL) as conn:
        conn.execute(
            "select set_config('app.tenant_id', %s, true), set_config('app.user_id', %s, true),"
            " set_config('app.actor', 'user', true)",
            (ctx["tenant"], str(STAFF)),
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "insert into app.outlet_qris (outlet_id, tenant_id, filename, content_type,"
                " image, uploaded_by) values (%s, %s, 'x.png', 'image/png', %s, %s)"
                " on conflict (outlet_id) do update set filename = excluded.filename",
                (ctx["outlet"], ctx["tenant"], PNG, str(STAFF)),
            )


# S2 · Cek QRIS terhadap rekening penerima ----------------------------------------------------


def test_counter_qris_goes_to_kitchen_and_is_checked_later(client, ctx) -> None:
    order = _qris_order(client, ctx)
    card = _card(client, ctx, order["id"])
    assert card["payment_status"] == "paid" and card["payment_method"] == "qris"
    assert card["status"] == "confirmed"  # straight to the kitchen
    assert card["qris_checked"] is False and "qris_check" in card["allowed_actions"]

    url = f"/api/v1/ops/orders/{order['id']}/qris-check"
    res = client.post(url, headers=ctx["staff"], json={"merchant_account_checked": False})
    assert res.status_code == 422, res.text
    res = client.post(url, headers=ctx["staff"], json={"merchant_account_checked": True})
    assert res.status_code == 200, res.text
    assert res.json()["qris_checked"] is True and "qris_check" not in res.json()["allowed_actions"]
    again = client.post(url, headers=ctx["staff"], json={"merchant_account_checked": True})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_checked"

    audit = admin_sql(
        "select action, data->>'order_id' from app.audit_events"
        " where tenant_id = %s and action = 'payment.qris_checked'",
        (ctx["tenant"],),
    )
    assert audit == [("payment.qris_checked", order["id"])]


def test_bill_closed_with_qris_is_checked_once_for_all_its_orders(client, ctx) -> None:
    ids = []
    for _ in range(2):
        res = client.post(
            f"/api/v1/ops/outlets/{ctx['outlet']}/orders",
            headers=ctx["staff"],
            json={
                "type": "dine_in",
                "table_id": ctx["table"],
                "items": [{"product_id": ctx["product"], "quantity": 1}],
                "payment": {"to_open_bill": True},
            },
        )
        assert res.status_code == 201, res.text
        ids.append(res.json()["id"])
    first = _card(client, ctx, ids[0])
    assert first["qris_checked"] is None and "qris_check" not in first["allowed_actions"]

    res = client.post(
        f"/api/v1/ops/bills/{first['bill_id']}/close",
        headers={**ctx["staff"], "Idempotency-Key": f"close-{first['bill_id']}"},
        json={"method": "qris"},
    )
    assert res.status_code == 200, res.text
    cards = [_card(client, ctx, i) for i in ids]
    assert all(c["qris_checked"] is False and "qris_check" in c["allowed_actions"] for c in cards)

    res = client.post(
        f"/api/v1/ops/orders/{ids[1]}/qris-check",
        headers=ctx["staff"],
        json={"merchant_account_checked": True},
    )
    assert res.status_code == 200, res.text
    assert all(_card(client, ctx, i)["qris_checked"] is True for i in ids)


def test_only_paid_qris_orders_can_be_checked(client, ctx) -> None:
    res = client.post(
        f"/api/v1/ops/outlets/{ctx['outlet']}/orders",
        headers=ctx["staff"],
        json={
            "type": "dine_in",
            "table_id": ctx["table"],
            "items": [{"product_id": ctx["product"], "quantity": 1}],
            "payment": {"to_open_bill": True},
        },
    )
    assert res.status_code == 201, res.text
    res = client.post(
        f"/api/v1/ops/orders/{res.json()['id']}/qris-check",
        headers=ctx["staff"],
        json={"merchant_account_checked": True},
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "not_checkable"

    # A reversed QRIS order no longer offers the check.
    order = _qris_order(client, ctx)
    res = client.post(
        f"/api/v1/ops/orders/{order['id']}/reversal",
        headers=ctx["staff"],
        json={"reason": "Salah pesan", "ingredients": "return"},
    )
    assert res.status_code == 200, res.text
    card = _card(client, ctx, order["id"])
    assert card["qris_checked"] is None and "qris_check" not in card["allowed_actions"]
