"""Wave 7c attendance tablet tests (T-116, T-120, T-121, T-122) against Postgres through RLS:
O3 pairing codes and device list, K0 pairing (one-time, expiring), K1 staff list scoped to the
outlet, K2/K3 selfie upload and the required selfie, clock in / clock out decided by the server,
one open record per staff member, revocation, and what a tablet or staff session cannot reach.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.v1 import device as device_api
from app.config import Settings
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "w7c.test"
OWNER = UUID("7c000000-0000-0000-0000-0000000000f0")
RINA = UUID("7c000000-0000-0000-0000-0000000000f1")  # Dago
DODI = UUID("7c000000-0000-0000-0000-0000000000f2")  # Dago + Riau
MAYA = UUID("7c000000-0000-0000-0000-0000000000f3")  # Riau only
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32


def _bearer(sub: UUID, tenant: str | None, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=str(sub), tenant_id=tenant, app_role=role)}"}


def _dev(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    cleanup_domain(DOMAIN)
    invite_owner(OWNER, f"owner@{DOMAIN}")
    with TestClient(
        create_app(Settings(database_url=APP_URL), token_verifier=make_verifier())
    ) as c:
        yield c
    cleanup_domain(DOMAIN)


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> None:
    device_api._failed.clear()


def _add_staff(tenant: str, user: UUID, name: str, outlets: list[str]) -> None:
    email = f"{name.lower()}@{DOMAIN}"
    admin_sql("insert into auth.users (id, email) values (%s, %s)", (user, email))
    admin_sql(
        "insert into app.users (id, tenant_id, email, display_name, role,"
        " invitation_accepted_at) values (%s, %s, %s, %s, 'staff', now())",
        (user, tenant, email, name),
    )
    for o in outlets:
        admin_sql(
            "insert into app.staff_outlets (user_id, outlet_id, tenant_id) values (%s, %s, %s)",
            (user, o, tenant),
        )


@pytest.fixture(scope="module")
def ctx(client: TestClient) -> dict[str, Any]:
    res = client.post(
        "/api/v1/owner/onboarding",
        headers=_bearer(OWNER, None, "owner_pending"),
        json={"business": {"name": "Kopi Senja", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, dago = res.json()["tenant_id"], res.json()["outlet_id"]
    owner = _bearer(OWNER, tenant, "owner")
    res = client.post(
        "/api/v1/owner/outlets", headers=owner, json={"name": "Riau", "timezone": "Asia/Makassar"}
    )
    assert res.status_code == 201, res.text
    riau = res.json()["id"]
    _add_staff(tenant, RINA, "Rina", [dago])
    _add_staff(tenant, DODI, "Dodi", [dago, riau])
    _add_staff(tenant, MAYA, "Maya", [riau])
    return {
        "tenant": tenant,
        "dago": dago,
        "riau": riau,
        "owner": owner,
        "rina": _bearer(RINA, tenant, "staff"),
    }


def _pair(client: TestClient, ctx: dict[str, Any], outlet: str) -> tuple[str, dict[str, Any]]:
    res = client.post(
        f"/api/v1/owner/outlets/{outlet}/attendance-pairing-codes", headers=ctx["owner"]
    )
    assert res.status_code == 201, res.text
    code = res.json()["code"]
    res = client.post("/api/v1/device/pair", json={"code": code})
    assert res.status_code == 201, res.text
    return res.json()["device_token"], res.json()


def _selfie(client: TestClient, token: str, body: bytes = JPEG, kind: str = "image/jpeg") -> str:
    res = client.post(
        "/api/v1/device/selfies", headers={**_dev(token), "Content-Type": kind}, content=body
    )
    assert res.status_code == 201, res.text
    return res.json()["selfie_id"]


def _tap(client: TestClient, token: str, user: UUID, selfie: str | None = None) -> Any:
    return client.post(
        "/api/v1/device/attendance",
        headers=_dev(token),
        json={"user_id": str(user), "selfie_id": selfie or _selfie(client, token)},
    )


# O3 / K0 · pairing -------------------------------------------------------------------------


def test_pairing_code_is_owner_only_and_one_time(client: TestClient, ctx: dict[str, Any]) -> None:
    res = client.post(
        f"/api/v1/owner/outlets/{ctx['dago']}/attendance-pairing-codes", headers=ctx["rina"]
    )
    assert res.status_code == 403

    res = client.post(
        f"/api/v1/owner/outlets/{ctx['dago']}/attendance-pairing-codes", headers=ctx["owner"]
    )
    assert res.status_code == 201, res.text
    code = res.json()["code"]
    assert len(code) == 6 and code.isdigit()

    first = client.post("/api/v1/device/pair", json={"code": code})
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["device_token"].startswith("dev_")
    assert body["outlet"] == {"name": "Dago", "timezone": "Asia/Jakarta"}
    assert body["device_name"].startswith("Tablet ")

    again = client.post("/api/v1/device/pair", json={"code": code})
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "pairing_code_invalid"

    # Only the hash is stored, never the code or the token.
    stored = admin_sql(
        "select count(*) from app.attendance_pairing_codes where code_hash = %s", (code,)
    )
    assert stored[0][0] == 0
    stored = admin_sql(
        "select count(*) from app.attendance_devices where token_hash = %s",
        (body["device_token"],),
    )
    assert stored[0][0] == 0


def test_expired_code_is_refused(client: TestClient, ctx: dict[str, Any]) -> None:
    res = client.post(
        f"/api/v1/owner/outlets/{ctx['dago']}/attendance-pairing-codes", headers=ctx["owner"]
    )
    code = res.json()["code"]
    admin_sql(
        "update app.attendance_pairing_codes set expires_at = now() - interval '1 second'"
        " where outlet_id = %s and used_at is null",
        (ctx["dago"],),
    )
    res = client.post("/api/v1/device/pair", json={"code": code})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "pairing_code_invalid"


def test_wrong_codes_are_rate_limited(client: TestClient) -> None:
    for _ in range(10):
        res = client.post("/api/v1/device/pair", json={"code": "000000"})
        assert res.status_code in (400, 201)
    res = client.post("/api/v1/device/pair", json={"code": "000000"})
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "too_many_attempts"


def test_device_list_shows_last_activity(client: TestClient, ctx: dict[str, Any]) -> None:
    token, paired = _pair(client, ctx, ctx["dago"])
    assert client.get("/api/v1/device/staff", headers=_dev(token)).status_code == 200
    res = client.get(
        f"/api/v1/owner/outlets/{ctx['dago']}/attendance-devices", headers=ctx["owner"]
    )
    assert res.status_code == 200, res.text
    names = {d["name"]: d for d in res.json()}
    assert names[paired["device_name"]]["last_seen_at"] is not None
    assert names[paired["device_name"]]["revoked_at"] is None
    staff = client.get(
        f"/api/v1/owner/outlets/{ctx['dago']}/attendance-devices", headers=ctx["rina"]
    )
    assert staff.status_code == 403


# K1-K4 · clock in / clock out -------------------------------------------------------------


def test_staff_list_is_scoped_to_the_outlet(client: TestClient, ctx: dict[str, Any]) -> None:
    token, _ = _pair(client, ctx, ctx["riau"])
    res = client.get("/api/v1/device/staff", headers=_dev(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["outlet"] == {"name": "Riau", "timezone": "Asia/Makassar"}
    assert [s["display_name"] for s in body["staff"]] == ["Dodi", "Maya"]
    assert all(s["status"] == "not_clocked_in" and s["since"] is None for s in body["staff"])
    assert body["server_time"]


def test_clock_in_then_out_with_required_selfie(client: TestClient, ctx: dict[str, Any]) -> None:
    token, _ = _pair(client, ctx, ctx["dago"])

    res = client.post(
        "/api/v1/device/attendance",
        headers=_dev(token),
        json={"user_id": str(RINA), "selfie_id": str(uuid4())},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "selfie_required"

    rina = next(
        s
        for s in client.get("/api/v1/device/staff", headers=_dev(token)).json()["staff"]
        if s["display_name"] == "Rina"
    )
    assert rina["first_time"] is True

    selfie = _selfie(client, token)
    res = _tap(client, token, RINA, selfie)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["action"] == "clock_in"
    assert body["first_time_notice"] is True
    assert body["duration_minutes"] is None
    assert body["display_name"] == "Rina"

    staff = client.get("/api/v1/device/staff", headers=_dev(token)).json()["staff"]
    rina = next(s for s in staff if s["display_name"] == "Rina")
    assert rina["status"] == "working" and rina["since"] and rina["first_time"] is False

    # A selfie is used once.
    res = _tap(client, token, RINA, selfie)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "selfie_required"

    admin_sql(
        "update app.attendance_records set clock_in_at = now() - interval '8 hours 32 minutes'"
        " where user_id = %s and status = 'open'",
        (RINA,),
    )
    res = _tap(client, token, RINA)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["action"] == "clock_out"
    assert body["duration_minutes"] == 512
    assert body["first_time_notice"] is False

    rows = admin_sql(
        "select status::text, clock_in_selfie_id is not null, clock_out_selfie_id is not null"
        " from app.attendance_records where user_id = %s",
        (RINA,),
    )
    assert rows == [("closed", True, True)]
    events = admin_sql(
        "select type::text, actor_type::text from app.attendance_events e"
        " join app.attendance_records r on r.id = e.record_id where r.user_id = %s order by e.id",
        (RINA,),
    )
    assert events == [("clock_in", "device"), ("clock_out", "device")]


def test_selfie_type_and_size_are_checked(client: TestClient, ctx: dict[str, Any]) -> None:
    token, _ = _pair(client, ctx, ctx["dago"])
    res = client.post(
        "/api/v1/device/selfies",
        headers={**_dev(token), "Content-Type": "image/png"},
        content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 10,
    )
    assert res.status_code == 422
    res = client.post(
        "/api/v1/device/selfies",
        headers={**_dev(token), "Content-Type": "image/jpeg"},
        content=b"not a jpeg",
    )
    assert res.status_code == 422
    res = client.post(
        "/api/v1/device/selfies",
        headers={**_dev(token), "Content-Type": "image/jpeg"},
        content=JPEG + b"\x00" * (2 * 1024 * 1024),
    )
    assert res.status_code == 422
    assert _selfie(client, token, WEBP, "image/webp")


def test_selfie_from_another_tablet_is_refused(client: TestClient, ctx: dict[str, Any]) -> None:
    one, _ = _pair(client, ctx, ctx["dago"])
    two, _ = _pair(client, ctx, ctx["dago"])
    selfie = _selfie(client, one)
    res = _tap(client, two, RINA, selfie)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "selfie_required"


def test_unassigned_staff_and_open_elsewhere(client: TestClient, ctx: dict[str, Any]) -> None:
    dago, _ = _pair(client, ctx, ctx["dago"])
    riau, _ = _pair(client, ctx, ctx["riau"])

    res = _tap(client, dago, MAYA)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "not_assigned"

    res = _tap(client, dago, DODI)
    assert res.status_code == 201 and res.json()["action"] == "clock_in"
    # One open record per staff member: Dodi cannot clock in at Riau while working at Dago.
    res = _tap(client, riau, DODI)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "open_elsewhere"
    res = _tap(client, dago, DODI)
    assert res.status_code == 201 and res.json()["action"] == "clock_out"


def test_revoked_tablet_is_refused(client: TestClient, ctx: dict[str, Any]) -> None:
    token, paired = _pair(client, ctx, ctx["dago"])
    devices = client.get(
        f"/api/v1/owner/outlets/{ctx['dago']}/attendance-devices", headers=ctx["owner"]
    ).json()
    device_id = next(d["id"] for d in devices if d["name"] == paired["device_name"])
    res = client.post(f"/api/v1/owner/attendance-devices/{device_id}/revoke", headers=ctx["rina"])
    assert res.status_code == 403
    res = client.post(f"/api/v1/owner/attendance-devices/{device_id}/revoke", headers=ctx["owner"])
    assert res.status_code == 200, res.text
    assert res.json()["revoked_at"]
    res = client.get("/api/v1/device/staff", headers=_dev(token))
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "device_revoked"


def test_tokens_do_not_cross(client: TestClient, ctx: dict[str, Any]) -> None:
    token, _ = _pair(client, ctx, ctx["dago"])
    # A staff (or owner) token is not a tablet session: no clock in from phones or the admin app.
    res = client.post(
        "/api/v1/device/attendance",
        headers=ctx["rina"],
        json={"user_id": str(RINA), "selfie_id": str(uuid4())},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "device_unpaired"
    res = client.get("/api/v1/device/staff", headers=_dev("dev_unknown"))
    assert res.status_code == 401
    # A tablet token opens nothing else.
    for path in ("/api/v1/me", f"/api/v1/owner/outlets/{ctx['dago']}"):
        assert client.get(path, headers=_dev(token)).status_code == 401


# RLS · the database refuses what the API never offers ----------------------------------------


def _as(
    conn: psycopg.Connection[Any],
    tenant: str,
    *,
    user: UUID | None = None,
    device: tuple[str, str] | None = None,
) -> None:
    conn.execute(
        "select set_config('app.tenant_id', %s, true), set_config('app.user_id', %s, true),"
        " set_config('app.actor', %s, true), set_config('app.device_outlet_id', %s, true),"
        " set_config('app.device_id', %s, true)",
        (
            tenant,
            str(user) if user else "",
            "device" if device else "user",
            device[1] if device else "",
            device[0] if device else "",
        ),
    )


def test_rls_scopes_tablets_and_staff(client: TestClient, ctx: dict[str, Any]) -> None:
    token, paired = _pair(client, ctx, ctx["dago"])
    assert _tap(client, token, RINA).status_code == 201  # Rina works at Dago now
    device_id = admin_sql(
        "select id from app.attendance_devices where outlet_id = %s and name = %s",
        (ctx["dago"], paired["device_name"]),
    )[0][0]
    assert APP_URL
    with psycopg.connect(APP_URL) as conn:
        _as(conn, ctx["tenant"], device=(str(device_id), ctx["dago"]))
        for table in ("users", "orders", "products", "ledger_entries", "attendance_devices"):
            n = conn.execute(f"select count(*) from app.{table}").fetchone()
            assert n == (0,), f"tablet reads app.{table}"
        conn.rollback()

        # Staff see only their own records and cannot write attendance.
        _as(conn, ctx["tenant"], user=DODI)
        users = conn.execute("select distinct user_id from app.attendance_records").fetchall()
        assert {u[0] for u in users} <= {DODI}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "insert into app.attendance_records (tenant_id, outlet_id, user_id, clock_in_at,"
                " clock_in_device_id) values (%s, %s, %s, now(), %s)",
                (ctx["tenant"], ctx["dago"], DODI, device_id),
            )
        conn.rollback()

        _as(conn, ctx["tenant"], user=RINA)
        mine = conn.execute(
            "select count(*) from app.attendance_selfies s join app.attendance_records r"
            " on s.id = r.clock_in_selfie_id where r.user_id = %s",
            (RINA,),
        ).fetchone()
        assert mine is not None and mine[0] >= 1
        others = conn.execute(
            "select count(*) from app.attendance_selfies s"
            " where not exists (select 1 from app.attendance_records r where r.user_id = %s"
            " and s.id in (r.clock_in_selfie_id, r.clock_out_selfie_id))",
            (RINA,),
        ).fetchone()
        assert others == (0,)
        conn.rollback()
