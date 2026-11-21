"""Wave 1 API tests against a migrated Postgres, through RLS as app_backend:
O1 onboarding (T-010), O3 outlets and drawers (T-011), O4 staff (T-012), and the
owner/staff permission split (T-013). Skipped without TEST_DATABASE_URL /
TEST_APP_DATABASE_URL (see test_db_session.py).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.supabase_admin import InvitedUser, SupabaseAdminError
from app.config import Settings
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "w1.test"
OWNER = UUID("20000000-0000-0000-0000-0000000000f0")
OTHER_OWNER = UUID("20000000-0000-0000-0000-0000000000f9")


def _admin(sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    return admin_sql(sql, params)


def _cleanup() -> None:
    cleanup_domain(DOMAIN)


@pytest.fixture(scope="module", autouse=True)
def fixtures() -> Iterator[None]:
    _cleanup()
    for uid, email in ((OWNER, f"olga@{DOMAIN}"), (OTHER_OWNER, f"lain@{DOMAIN}")):
        invite_owner(uid, email)
    yield
    _cleanup()


class FakeAuthAdmin:
    def __init__(self) -> None:
        self.invited: list[str] = []
        self.banned: list[UUID] = []
        self.fail_with: int | None = None

    def invite_user(
        self, email: str, *, data: dict[str, Any] | None = None, redirect_to: str | None = None
    ) -> InvitedUser:
        if self.fail_with:
            raise SupabaseAdminError(self.fail_with, "boom")
        uid = uuid4()
        _admin(
            "insert into auth.users (id, email) values (%s, %s) on conflict do nothing",
            (uid, email),
        )
        self.invited.append(email)
        return InvitedUser(user_id=uid, email=email)

    def ban_user(self, user_id: UUID, duration: str = "876000h") -> None:
        self.banned.append(user_id)


@pytest.fixture(scope="module")
def auth_admin() -> FakeAuthAdmin:
    return FakeAuthAdmin()


@pytest.fixture(scope="module")
def client(auth_admin: FakeAuthAdmin) -> Iterator[TestClient]:
    app = create_app(
        Settings(database_url=APP_URL), token_verifier=make_verifier(), auth_admin=auth_admin
    )
    with TestClient(app) as c:
        yield c


def _h(user: UUID, tenant: UUID | str | None, role: str) -> dict[str, str]:
    token = make_token(sub=str(user), tenant_id=str(tenant) if tenant else None, app_role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def tenant(client: TestClient) -> dict[str, str]:
    """O1: the invited owner creates the business and first outlet."""
    body = {
        "business": {"name": "Kopi Uji", "type": "cafe"},
        "outlet": {
            "name": "Bandung - Dago",
            "address": "Jl. Juanda 12",
            "whatsapp_phone": "+628119990001",
        },
    }
    res = client.post(
        "/api/v1/owner/onboarding", json=body, headers=_h(OWNER, None, "owner_pending")
    )
    assert res.status_code == 201, res.text
    return {k: str(v) for k, v in res.json().items()}


def owner(tenant: dict[str, str]) -> dict[str, str]:
    return _h(OWNER, tenant["tenant_id"], "owner")


# O1 -------------------------------------------------------------------------------


def test_onboarding_creates_tenant_owner_outlet_and_defaults(client, tenant) -> None:
    me = client.get("/api/v1/me", headers=owner(tenant)).json()
    assert me["role"] == "owner" and me["tenant"] == {
        "id": tenant["tenant_id"],
        "name": "Kopi Uji",
        "type": "cafe",
    }
    assert [(o["name"], o["order_prefix"]) for o in me["outlets"]] == [("Bandung - Dago", "A")]

    drawers = client.get(
        f"/api/v1/owner/outlets/{tenant['outlet_id']}/drawers", headers=owner(tenant)
    ).json()
    assert [d["name"] for d in drawers] == ["Kasir depan"]
    rows = _admin(
        "select accepted_at is not null from app.owner_invitations where auth_user_id=%s", (OWNER,)
    )
    assert rows == [(True,)]


def test_onboarding_twice_is_refused(client, tenant) -> None:
    body = {"business": {"name": "Lagi", "type": "cafe"}, "outlet": {"name": "X"}}
    res = client.post(
        "/api/v1/owner/onboarding", json=body, headers=_h(OWNER, None, "owner_pending")
    )
    assert res.status_code == 403  # invitation no longer open
    res = client.post("/api/v1/owner/onboarding", json=body, headers=owner(tenant))
    assert res.json()["error"]["code"] == "already_onboarded"


def test_onboarding_rejects_dropshipper(client) -> None:
    body = {"business": {"name": "D", "type": "dropshipper"}, "outlet": {"name": "X"}}
    res = client.post(
        "/api/v1/owner/onboarding", json=body, headers=_h(OTHER_OWNER, None, "owner_pending")
    )
    assert res.status_code == 422


# O3 -------------------------------------------------------------------------------


def test_new_outlet_gets_next_prefix_drawer_and_hours(client, tenant) -> None:
    res = client.post(
        "/api/v1/owner/outlets",
        headers=owner(tenant),
        json={"name": "Bandung - Riau", "timezone": "Asia/Jakarta"},
    )
    assert res.status_code == 201, res.text
    outlet = res.json()
    assert outlet["order_prefix"] == "B"
    assert len(outlet["opening_hours"]) == 7
    names = [o["name"] for o in client.get("/api/v1/owner/outlets", headers=owner(tenant)).json()]
    assert names == ["Bandung - Dago", "Bandung - Riau"]


def test_patch_outlet_validates_pb1_and_audits(client, tenant) -> None:
    url = f"/api/v1/owner/outlets/{tenant['outlet_id']}"
    res = client.patch(url, headers=owner(tenant), json={"pb1_enabled": True})
    assert res.status_code == 422 and res.json()["error"]["details"]["field"] == "pb1_rate_bps"

    res = client.patch(
        url,
        headers=owner(tenant),
        json={
            "pb1_enabled": True,
            "pb1_rate_bps": 1000,
            "payment_mode": "open_bill",
            "delivery_fee": 10000,
            "unpaid_timeout_minutes": 20,
            "timezone": "Asia/Makassar",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["pb1_rate_bps"], body["payment_mode"], body["timezone"]) == (
        1000,
        "open_bill",
        "Asia/Makassar",
    )
    audit = _admin(
        "select data->'changes' ? 'payment_mode' from app.audit_events"
        " where action = 'outlet.updated' and entity_id = %s",
        (tenant["outlet_id"],),
    )
    assert audit == [(True,)]


def test_opening_hours_replace_and_overnight(client, tenant) -> None:
    url = f"/api/v1/owner/outlets/{tenant['outlet_id']}/opening-hours"
    hours = [{"weekday": d, "opens_at": "08:00", "closes_at": "22:00"} for d in range(1, 6)]
    hours.append({"weekday": 6, "opens_at": "10:00", "closes_at": "01:00"})
    res = client.put(url, headers=owner(tenant), json=hours)
    assert res.status_code == 200
    assert [h["weekday"] for h in res.json()] == [1, 2, 3, 4, 5, 6]
    dup = client.put(url, headers=owner(tenant), json=[*hours, hours[0]])
    assert dup.status_code == 422


def test_drawers_create_rename_delete(client, tenant) -> None:
    base = f"/api/v1/owner/outlets/{tenant['outlet_id']}/drawers"
    created = client.post(base, headers=owner(tenant), json={"name": "Bar"})
    assert created.status_code == 201
    drawer_id = created.json()["id"]
    assert client.post(base, headers=owner(tenant), json={"name": "Bar"}).status_code == 409
    assert (
        client.patch(
            f"/api/v1/owner/drawers/{drawer_id}",
            headers=owner(tenant),
            json={"name": "Bar belakang"},
        ).status_code
        == 204
    )
    assert (
        client.delete(f"/api/v1/owner/drawers/{drawer_id}", headers=owner(tenant)).status_code
        == 204
    )
    remaining = client.get(base, headers=owner(tenant)).json()
    assert [d["name"] for d in remaining] == ["Kasir depan"]
    # S8 keeps each drawer's number after another drawer is deleted (#74).
    again = client.post(base, headers=owner(tenant), json={"name": "Teras"}).json()["id"]
    cards = client.get(
        f"/api/v1/ops/outlets/{tenant['outlet_id']}/drawers", headers=owner(tenant)
    ).json()
    assert [(c["drawer"]["name"], c["drawer"]["number"]) for c in cards] == [
        ("Kasir depan", 1),
        ("Teras", 3),
    ]
    client.delete(f"/api/v1/owner/drawers/{again}", headers=owner(tenant))
    last = client.delete(f"/api/v1/owner/drawers/{remaining[0]['id']}", headers=owner(tenant))
    assert last.json()["error"]["code"] == "last_drawer"


def test_other_tenant_cannot_see_outlet(client, tenant) -> None:
    body = {"business": {"name": "Lain", "type": "restaurant"}, "outlet": {"name": "Lain"}}
    res = client.post(
        "/api/v1/owner/onboarding", json=body, headers=_h(OTHER_OWNER, None, "owner_pending")
    )
    other = res.json()
    headers = _h(OTHER_OWNER, other["tenant_id"], "owner")
    assert (
        client.get(f"/api/v1/owner/outlets/{tenant['outlet_id']}", headers=headers).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/owner/outlets/{tenant['outlet_id']}", headers=headers, json={"name": "hack"}
        ).status_code
        == 404
    )


# O4 + permissions -------------------------------------------------------------------


def test_staff_invite_accept_permissions_and_deactivate(client, tenant, auth_admin) -> None:
    res = client.post(
        "/api/v1/owner/staff/invitations",
        headers=owner(tenant),
        json={
            "display_name": "Rina",
            "email": f"Rina@{DOMAIN}",
            "outlet_ids": [tenant["outlet_id"]],
        },
    )
    assert res.status_code == 201, res.text
    rina = res.json()
    assert rina["status"] == "invited" and rina["email"] == f"rina@{DOMAIN}"
    assert auth_admin.invited[-1] == f"rina@{DOMAIN}"

    dup = client.post(
        "/api/v1/owner/staff/invitations",
        headers=owner(tenant),
        json={
            "display_name": "Rina 2",
            "email": f"rina@{DOMAIN}",
            "outlet_ids": [tenant["outlet_id"]],
        },
    )
    assert dup.json()["error"]["code"] == "email_taken"
    assert auth_admin.invited.count(f"rina@{DOMAIN}") == 1  # no second email sent

    staff_h = _h(UUID(rina["id"]), tenant["tenant_id"], "staff")
    me = client.get("/api/v1/me", headers=staff_h).json()
    assert me["role"] == "staff" and [o["id"] for o in me["outlets"]] == [tenant["outlet_id"]]
    listed = client.get("/api/v1/owner/staff", headers=owner(tenant)).json()
    assert [(s["display_name"], s["status"]) for s in listed] == [("Rina", "active")]

    # Staff calling owner endpoints changes nothing (AC1.6).
    for method, url in (
        ("get", "/api/v1/owner/staff"),
        ("patch", f"/api/v1/owner/outlets/{tenant['outlet_id']}"),
        ("post", "/api/v1/owner/outlets"),
    ):
        r = client.request(method, url, headers=staff_h, json={"name": "x"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"

    assert (
        client.post(
            f"/api/v1/owner/staff/{rina['id']}/invitations/resend", headers=owner(tenant)
        ).json()["error"]["code"]
        == "invitation_accepted"
    )

    res = client.post(f"/api/v1/owner/staff/{rina['id']}/deactivate", headers=owner(tenant))
    assert res.status_code == 204 and auth_admin.banned == [UUID(rina["id"])]
    gone = client.get("/api/v1/me", headers=staff_h)
    assert gone.status_code == 403 and gone.json()["error"]["code"] == "account_inactive"


def test_set_outlets_and_supabase_failure(client, tenant, auth_admin) -> None:
    outlets = client.get("/api/v1/owner/outlets", headers=owner(tenant)).json()
    res = client.post(
        "/api/v1/owner/staff/invitations",
        headers=owner(tenant),
        json={"display_name": "Dodi", "email": f"dodi@{DOMAIN}", "outlet_ids": [outlets[0]["id"]]},
    )
    dodi = res.json()
    res = client.put(
        f"/api/v1/owner/staff/{dodi['id']}/outlets",
        headers=owner(tenant),
        json={"outlet_ids": [o["id"] for o in outlets]},
    )
    assert sorted(o["name"] for o in res.json()["outlets"]) == ["Bandung - Dago", "Bandung - Riau"]
    assert (
        client.put(
            f"/api/v1/owner/staff/{dodi['id']}/outlets",
            headers=owner(tenant),
            json={"outlet_ids": [str(uuid4())]},
        ).status_code
        == 422
    )

    auth_admin.fail_with = 500
    try:
        res = client.post(
            "/api/v1/owner/staff/invitations",
            headers=owner(tenant),
            json={
                "display_name": "Sari",
                "email": f"sari@{DOMAIN}",
                "outlet_ids": [outlets[0]["id"]],
            },
        )
    finally:
        auth_admin.fail_with = None
    assert res.status_code == 502
    names = [
        s["display_name"] for s in client.get("/api/v1/owner/staff", headers=owner(tenant)).json()
    ]
    assert "Sari" not in names
