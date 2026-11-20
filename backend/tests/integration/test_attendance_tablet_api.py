"""Wave 7c attendance tablet tests (T-116, T-120, T-121, T-122) against Postgres through RLS:
O3 pairing codes and device list, K0 pairing (one-time, expiring), K1 staff list scoped to the
outlet, K2/K3 selfie upload and the required selfie, clock in / clock out decided by the server,
one open record per staff member, one active tablet per outlet ("Lupakan perangkat" before a new
pairing), revocation, and what a tablet or staff session cannot reach.
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
    device_api._attempts.clear()


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


def _forget_all(client: TestClient, ctx: dict[str, Any], outlet: str) -> None:
    """O3 "Lupakan perangkat" for every active tablet of the outlet."""
    res = client.get(f"/api/v1/owner/outlets/{outlet}/attendance-devices", headers=ctx["owner"])
    assert res.status_code == 200, res.text
    for d in res.json():
        if d["revoked_at"] is None:
            res = client.post(
                f"/api/v1/owner/attendance-devices/{d['id']}/revoke", headers=ctx["owner"]
            )
            assert res.status_code == 200, res.text


def _pair(client: TestClient, ctx: dict[str, Any], outlet: str) -> tuple[str, dict[str, Any]]:
    """Pair a new tablet to the outlet, forgetting its current one first (one per outlet)."""
    _forget_all(client, ctx, outlet)
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


def _tap(client: TestClient, token: str, user: UUID, action: str, selfie: str | None = None) -> Any:
    return client.post(
        "/api/v1/device/attendance",
        headers=_dev(token),
        json={
            "user_id": str(user),
            "selfie_id": selfie or _selfie(client, token),
            "action": action,
        },
    )


# O3 / K0 · pairing -------------------------------------------------------------------------


def test_pairing_code_is_owner_only_and_one_time(client: TestClient, ctx: dict[str, Any]) -> None:
    _forget_all(client, ctx, ctx["dago"])
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
    _forget_all(client, ctx, ctx["dago"])
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


def test_one_active_tablet_per_outlet(client: TestClient, ctx: dict[str, Any]) -> None:
    old, _ = _pair(client, ctx, ctx["dago"])
    url = f"/api/v1/owner/outlets/{ctx['dago']}/attendance-pairing-codes"
    # While Dago has a tablet, no new code (O3 hides "+ Pairing tablet baru").
    res = client.post(url, headers=ctx["owner"])
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "tablet_already_paired"
    # Another outlet is not affected.
    _forget_all(client, ctx, ctx["riau"])
    assert (
        client.post(
            f"/api/v1/owner/outlets/{ctx['riau']}/attendance-pairing-codes", headers=ctx["owner"]
        ).status_code
        == 201
    )

    # "Lupakan perangkat" → the old tablet is refused and a new one can pair.
    _forget_all(client, ctx, ctx["dago"])
    res = client.get("/api/v1/device/staff", headers=_dev(old))
    assert res.status_code == 401 and res.json()["error"]["code"] == "device_revoked"
    new, _ = _pair(client, ctx, ctx["dago"])
    assert client.get("/api/v1/device/staff", headers=_dev(new)).status_code == 200
    active = [
        d
        for d in client.get(
            f"/api/v1/owner/outlets/{ctx['dago']}/attendance-devices", headers=ctx["owner"]
        ).json()
        if d["revoked_at"] is None
    ]
    assert len(active) == 1


def test_second_code_cannot_pair_a_second_tablet(client: TestClient, ctx: dict[str, Any]) -> None:
    _forget_all(client, ctx, ctx["dago"])
    url = f"/api/v1/owner/outlets/{ctx['dago']}/attendance-pairing-codes"
    first = client.post(url, headers=ctx["owner"]).json()["code"]
    second = client.post(url, headers=ctx["owner"]).json()["code"]
    assert client.post("/api/v1/device/pair", json={"code": first}).status_code == 201
    res = client.post("/api/v1/device/pair", json={"code": second})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "tablet_already_paired"
    # A right code does not count against the rate limit, and it stays usable (10 minutes).
    assert not device_api._attempts
    _forget_all(client, ctx, ctx["dago"])
    assert client.post("/api/v1/device/pair", json={"code": second}).status_code == 201


def test_replacement_tablet_keeps_the_name_tablet_1(
    client: TestClient, ctx: dict[str, Any]
) -> None:
    # Note 2 of the PR #35 review: a forgotten tablet must not push the number up, so the
    # replacement of "Tablet 1" is named "Tablet 1" too (names repeat across generations).
    _, first = _pair(client, ctx, ctx["dago"])
    assert first["device_name"] == "Tablet 1"
    _forget_all(client, ctx, ctx["dago"])
    _, second = _pair(client, ctx, ctx["dago"])
    assert second["device_name"] == "Tablet 1"


def test_outlet_with_several_old_tablets_keeps_them(
    client: TestClient, ctx: dict[str, Any]
) -> None:
    # Tablets paired before the one-tablet rule keep working; pairing waits until all are gone.
    token, paired = _pair(client, ctx, ctx["dago"])
    admin_sql(
        "insert into app.attendance_devices (tenant_id, outlet_id, name, paired_by)"
        " values (%s, %s, 'Tablet lama', %s)",
        (ctx["tenant"], ctx["dago"], OWNER),
    )
    assert client.get("/api/v1/device/staff", headers=_dev(token)).status_code == 200
    url = f"/api/v1/owner/outlets/{ctx['dago']}/attendance-pairing-codes"
    devices = client.get(
        f"/api/v1/owner/outlets/{ctx['dago']}/attendance-devices", headers=ctx["owner"]
    ).json()
    mine = next(d["id"] for d in devices if d["name"] == paired["device_name"])
    client.post(f"/api/v1/owner/attendance-devices/{mine}/revoke", headers=ctx["owner"])
    res = client.post(url, headers=ctx["owner"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "tablet_already_paired"
    _forget_all(client, ctx, ctx["dago"])
    assert client.post(url, headers=ctx["owner"]).status_code == 201


def test_wrong_codes_are_rate_limited(client: TestClient, ctx: dict[str, Any]) -> None:
    # Right codes do not count against the client.
    for _ in range(3):
        _pair(client, ctx, ctx["dago"])
    for _ in range(10):
        res = client.post("/api/v1/device/pair", json={"code": "000000"})
        assert res.status_code == 400
    res = client.post("/api/v1/device/pair", json={"code": "000000"})
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "too_many_attempts"
    # Only that client is limited (the last X-Forwarded-For entry is the one the proxy added).
    other = {"X-Forwarded-For": "203.0.113.9, 198.51.100.7"}
    res = client.post("/api/v1/device/pair", json={"code": "000000"}, headers=other)
    assert res.status_code == 400
    # An attempt is counted before the database call, so a burst cannot get past the limit.
    device_api._attempts.clear()
    for _ in range(10):
        device_api._reserve_attempt("burst")
    with pytest.raises(device_api.ApiError):
        device_api._reserve_attempt("burst")


def test_device_list_shows_last_activity(client: TestClient, ctx: dict[str, Any]) -> None:
    token, paired = _pair(client, ctx, ctx["dago"])
    assert client.get("/api/v1/device/staff", headers=_dev(token)).status_code == 200
    res = client.get(
        f"/api/v1/owner/outlets/{ctx['dago']}/attendance-devices", headers=ctx["owner"]
    )
    assert res.status_code == 200, res.text
    # Names are not unique: a forgotten tablet and its replacement are both "Tablet 1"
    # (the list returns active ones first), so pick the active device by name.
    active = [
        d for d in res.json() if d["revoked_at"] is None and d["name"] == paired["device_name"]
    ]
    assert len(active) == 1
    assert active[0]["last_seen_at"] is not None
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


def test_clock_in_then_out_with_required_selfie(client: TestClient, ctx: dict[str, Any]) -> None:
    token, _ = _pair(client, ctx, ctx["dago"])

    res = client.post(
        "/api/v1/device/attendance",
        headers=_dev(token),
        json={"user_id": str(RINA), "selfie_id": str(uuid4()), "action": "clock_in"},
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
    res = _tap(client, token, RINA, "clock_in", selfie)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["action"] == "clock_in"
    assert body["duration_minutes"] is None
    assert body["display_name"] == "Rina"

    staff = client.get("/api/v1/device/staff", headers=_dev(token)).json()["staff"]
    rina = next(s for s in staff if s["display_name"] == "Rina")
    assert rina["status"] == "working" and rina["since"] and rina["first_time"] is False

    # A retried "Simpan" (same selfie) returns the stored clock in instead of clocking out.
    again = _tap(client, token, RINA, "clock_in", selfie)
    assert again.status_code == 201, again.text
    assert again.json()["action"] == "clock_in" and again.json()["at"] == body["at"]
    assert admin_sql("select count(*) from app.attendance_records where user_id = %s", (RINA,)) == [
        (1,)
    ]
    # A stale K1 ("Belum masuk" on another tablet) is refused instead of clocking out.
    res = _tap(client, token, RINA, "clock_in")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "state_changed"

    # Long hours and the longest grace, so an 8.5-hour shift is never flagged as forgotten
    # (whatever the time of day the test runs).
    admin_sql("update app.outlets set attendance_grace_minutes = 720 where id = %s", (ctx["dago"],))
    admin_sql(
        "insert into app.outlet_opening_hours (outlet_id, tenant_id, weekday, opens_at, closes_at)"
        " select %s, %s, d, '00:00', '23:59' from generate_series(1, 7) d"
        " on conflict (outlet_id, weekday) do update set opens_at = '00:00', closes_at = '23:59'",
        (ctx["dago"], ctx["tenant"]),
    )
    admin_sql(
        "update app.attendance_records set clock_in_at = now() - interval '8 hours 32 minutes'"
        " where user_id = %s and status = 'open'",
        (RINA,),
    )
    out_selfie = _selfie(client, token)
    res = _tap(client, token, RINA, "clock_out", out_selfie)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["action"] == "clock_out"
    assert body["duration_minutes"] == 512
    # Retrying the clock out does not start a new shift.
    again = _tap(client, token, RINA, "clock_out", out_selfie)
    assert again.status_code == 201 and again.json()["action"] == "clock_out"
    res = _tap(client, token, RINA, "clock_out")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "state_changed"

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

    # A chunked body (no Content-Length) is cut off at 2 MB too.
    def chunks() -> Iterator[bytes]:
        yield JPEG
        for _ in range(40):
            yield b"\x00" * 65536

    res = client.post(
        "/api/v1/device/selfies",
        headers={**_dev(token), "Content-Type": "image/jpeg"},
        content=chunks(),
    )
    assert res.status_code == 422


def test_unassigned_while_working_can_still_clock_out(
    client: TestClient, ctx: dict[str, Any]
) -> None:
    token, _ = _pair(client, ctx, ctx["dago"])
    assert _tap(client, token, RINA, "clock_in").status_code == 201
    admin_sql(
        "delete from app.staff_outlets where user_id = %s and outlet_id = %s", (RINA, ctx["dago"])
    )
    try:
        staff = client.get("/api/v1/device/staff", headers=_dev(token)).json()["staff"]
        rina = next(s for s in staff if s["display_name"] == "Rina")
        assert rina["status"] == "working"
        res = _tap(client, token, RINA, "clock_out")
        assert res.status_code == 201, res.text
        staff = client.get("/api/v1/device/staff", headers=_dev(token)).json()["staff"]
        assert "Rina" not in {s["display_name"] for s in staff}
        res = _tap(client, token, RINA, "clock_in")
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "not_assigned"
    finally:
        admin_sql(
            "insert into app.staff_outlets (user_id, outlet_id, tenant_id) values (%s, %s, %s)",
            (RINA, ctx["dago"], ctx["tenant"]),
        )


def test_selfie_from_another_tablet_is_refused(client: TestClient, ctx: dict[str, Any]) -> None:
    one, _ = _pair(client, ctx, ctx["dago"])
    selfie = _selfie(client, one)
    two, _ = _pair(client, ctx, ctx["dago"])  # forgets tablet one (one tablet per outlet)
    res = _tap(client, two, RINA, "clock_in", selfie)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "selfie_required"


def test_unassigned_staff_and_open_elsewhere(client: TestClient, ctx: dict[str, Any]) -> None:
    dago, _ = _pair(client, ctx, ctx["dago"])
    riau, _ = _pair(client, ctx, ctx["riau"])

    res = _tap(client, dago, MAYA, "clock_in")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "not_assigned"

    res = _tap(client, dago, DODI, "clock_in")
    assert res.status_code == 201 and res.json()["action"] == "clock_in"
    # One open record per staff member: Dodi cannot clock in at Riau while working at Dago.
    res = _tap(client, riau, DODI, "clock_in")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "open_elsewhere"
    res = _tap(client, dago, DODI, "clock_out")
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
    assert _tap(client, token, RINA, "clock_in").status_code == 201  # Rina works at Dago now
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
