"""Wave 7c-2 attendance tests (T-118, T-119, T-120, T-122) against Postgres through RLS: the
missing clock-out flag at closing + grace (no invented time, a new clock-in afterwards), the O14
report with outlet-local day boundaries (WIB/WITA) and totals without flagged records,
corrections with a required reason that keep the original values, CSV export, selfies for the
owner and the person only, the 30-day selfie purge, and S9 own status and history.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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

DOMAIN = "w7c2.test"
OWNER = UUID("7c200000-0000-0000-0000-0000000000f0")
RINA = UUID("7c200000-0000-0000-0000-0000000000f1")  # Dago (WIB)
DODI = UUID("7c200000-0000-0000-0000-0000000000f2")  # Dago
MAYA = UUID("7c200000-0000-0000-0000-0000000000f3")  # Canggu (WITA)
SARI = UUID("7c200000-0000-0000-0000-0000000000f4")  # Dago, only in the grace test
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WIB = ZoneInfo("Asia/Jakarta")
WITA = ZoneInfo("Asia/Makassar")
HOURS = [{"weekday": d, "opens_at": "08:00", "closes_at": "22:00"} for d in range(1, 8)]


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


def _add_staff(tenant: str, user: UUID, name: str, outlet: str) -> None:
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


def _pair(client: TestClient, owner: dict[str, str], outlet: str) -> str:
    res = client.post(f"/api/v1/owner/outlets/{outlet}/attendance-pairing-codes", headers=owner)
    res = client.post("/api/v1/device/pair", json={"code": res.json()["code"]})
    assert res.status_code == 201, res.text
    return res.json()["device_token"]


def _tap(client: TestClient, token: str, user: UUID) -> dict[str, Any]:
    res = client.post(
        "/api/v1/device/selfies",
        headers={**_dev(token), "Content-Type": "image/jpeg"},
        content=JPEG,
    )
    res = client.post(
        "/api/v1/device/attendance",
        headers=_dev(token),
        json={"user_id": str(user), "selfie_id": res.json()["selfie_id"]},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _move(record_id: str, clock_in: datetime, clock_out: datetime | None = None) -> None:
    """Shift a record (and its event times) into the past, as if it happened then."""
    admin_sql(
        "update app.attendance_records set clock_in_at = %s, clock_out_at = %s where id = %s",
        (clock_in, clock_out, record_id),
    )
    assert ADMIN_URL
    with psycopg.connect(ADMIN_URL) as conn:  # events are append-only: bypass the trigger
        conn.execute("set local session_replication_role = replica")
        for kind, at in (("clock_in", clock_in), ("clock_out", clock_out)):
            if at:
                conn.execute(
                    "update app.attendance_events"
                    " set data = data || jsonb_build_object('at', %s::text)"
                    " where record_id = %s and type = %s",
                    (at.isoformat(), record_id, kind),
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
        "/api/v1/owner/outlets",
        headers=owner,
        json={"name": "Canggu", "timezone": "Asia/Makassar"},
    )
    canggu = res.json()["id"]
    for o in (dago, canggu):
        res = client.put(f"/api/v1/owner/outlets/{o}/opening-hours", headers=owner, json=HOURS)
        assert res.status_code in (200, 204), res.text
    _add_staff(tenant, RINA, "Rina", dago)
    _add_staff(tenant, DODI, "Dodi", dago)
    _add_staff(tenant, MAYA, "Maya", canggu)
    _add_staff(tenant, SARI, "Sari", dago)
    dago_tab = _pair(client, owner, dago)
    canggu_tab = _pair(client, owner, canggu)

    yesterday = datetime.now(WIB).date() - timedelta(days=1)
    day_before = yesterday - timedelta(days=1)

    # Rina: a closed shift the day before yesterday, 08:00-16:30 WIB (8 j 30 m).
    r1 = _tap(client, dago_tab, RINA)["record_id"]
    _tap(client, dago_tab, RINA)
    _move(
        r1,
        datetime(day_before.year, day_before.month, day_before.day, 8, 0, tzinfo=WIB),
        datetime(day_before.year, day_before.month, day_before.day, 16, 30, tzinfo=WIB),
    )
    # Dodi: clocked in yesterday 14:00 WIB and forgot to clock out (closes 22:00 + 1 h).
    r2 = _tap(client, dago_tab, DODI)["record_id"]
    _move(r2, datetime(yesterday.year, yesterday.month, yesterday.day, 14, 0, tzinfo=WIB))
    # Maya: yesterday 09:00-17:10 WITA.
    r3 = _tap(client, canggu_tab, MAYA)["record_id"]
    _tap(client, canggu_tab, MAYA)
    _move(
        r3,
        datetime(yesterday.year, yesterday.month, yesterday.day, 9, 0, tzinfo=WITA),
        datetime(yesterday.year, yesterday.month, yesterday.day, 17, 10, tzinfo=WITA),
    )
    return {
        "tenant": tenant,
        "dago": dago,
        "canggu": canggu,
        "owner": owner,
        "rina": _bearer(RINA, tenant, "staff"),
        "dodi": _bearer(DODI, tenant, "staff"),
        "dago_tab": dago_tab,
        "rina_closed": r1,
        "dodi_open": r2,
        "maya_closed": r3,
        "yesterday": yesterday,
        "day_before": day_before,
    }


def _range(ctx: dict[str, Any]) -> str:
    return f"from={ctx['day_before']}&to={datetime.now(WIB).date()}"


def test_forgotten_clock_out_is_flagged(client: TestClient, ctx: dict[str, Any]) -> None:
    res = client.get(f"/api/v1/owner/attendance?{_range(ctx)}", headers=ctx["owner"])
    assert res.status_code == 200, res.text
    body = res.json()
    dodi = next(r for r in body["records"] if r["id"] == ctx["dodi_open"])
    assert dodi["status"] == "needs_correction"
    assert dodi["clock_out_at"] is None  # no invented clock-out
    assert body["needs_correction_count"] == 1

    detail = client.get(f"/api/v1/owner/attendance/{ctx['dodi_open']}", headers=ctx["owner"])
    assert detail.status_code == 200, detail.text
    flag = detail.json()["flag"]
    y = ctx["yesterday"]
    assert datetime.fromisoformat(flag["at"]) == datetime(y.year, y.month, y.day, 23, 0, tzinfo=WIB)
    assert flag["closes_at"] == "22:00" and flag["grace_minutes"] == 60
    events = admin_sql(
        "select type::text, actor_type::text from app.attendance_events where record_id = %s"
        " order by id",
        (ctx["dodi_open"],),
    )
    assert events == [("clock_in", "device"), ("flag", "system")]

    # The flagged record no longer blocks a new day: the next tap is a clock in.
    assert _tap(client, ctx["dago_tab"], DODI)["action"] == "clock_in"
    assert _tap(client, ctx["dago_tab"], DODI)["action"] == "clock_out"


def test_open_record_within_grace_is_not_flagged(client: TestClient, ctx: dict[str, Any]) -> None:
    rec = _tap(client, ctx["dago_tab"], SARI)
    today = datetime.now(WIB)
    _move(rec["record_id"], today - timedelta(minutes=30))
    client.get(f"/api/v1/owner/attendance?{_range(ctx)}", headers=ctx["owner"])
    status = admin_sql(
        "select status::text from app.attendance_records where id = %s", (rec["record_id"],)
    )
    # 30 minutes ago is before today's 22:00 + 1 h (or the clock-in + grace after closing).
    assert status == [("open",)]
    assert _tap(client, ctx["dago_tab"], SARI)["action"] == "clock_out"


def test_report_totals_and_local_days(client: TestClient, ctx: dict[str, Any]) -> None:
    res = client.get(
        f"/api/v1/owner/attendance?from={ctx['day_before']}&to={ctx['yesterday']}",
        headers=ctx["owner"],
    )
    body = res.json()
    totals = {s["user"]["name"]: s for s in body["summary"]}
    assert totals["Rina"]["worked_minutes"] == 510 and totals["Rina"]["days"] == 1
    assert totals["Maya"]["worked_minutes"] == 490 and totals["Maya"]["outlets"] == ["Canggu"]
    assert totals["Dodi"]["worked_minutes"] == 0  # flagged: not counted
    maya = next(r for r in body["records"] if r["id"] == ctx["maya_closed"])
    assert maya["date"] == ctx["yesterday"].isoformat()
    assert maya["timezone"] == "Asia/Makassar"
    assert maya["has_selfie_in"] and maya["has_selfie_out"]

    # Outlet and staff filters.
    res = client.get(
        f"/api/v1/owner/attendance?{_range(ctx)}&outlet_id={ctx['canggu']}", headers=ctx["owner"]
    )
    assert {r["user"]["name"] for r in res.json()["records"]} == {"Maya"}
    res = client.get(f"/api/v1/owner/attendance?{_range(ctx)}&user_id={RINA}", headers=ctx["owner"])
    assert {r["user"]["name"] for r in res.json()["records"]} == {"Rina"}

    # A WITA clock-in at 23:30 local is still that local day (15:30 UTC).
    y = ctx["yesterday"]
    late = _tap(client, _pair(client, ctx["owner"], ctx["canggu"]), MAYA)["record_id"]
    _move(
        late,
        datetime(y.year, y.month, y.day, 23, 30, tzinfo=WITA),
        datetime(y.year, y.month, y.day, 23, 55, tzinfo=WITA),
    )
    admin_sql("update app.attendance_records set status = 'closed' where id = %s", (late,))
    res = client.get(f"/api/v1/owner/attendance?from={y}&to={y}", headers=ctx["owner"])
    assert late in {r["id"] for r in res.json()["records"]}


def test_staff_cannot_open_the_owner_report(client: TestClient, ctx: dict[str, Any]) -> None:
    for path in (
        "/api/v1/owner/attendance",
        f"/api/v1/owner/attendance/{ctx['rina_closed']}",
        f"/api/v1/owner/attendance/{ctx['rina_closed']}/selfies/in",
    ):
        assert client.get(path, headers=ctx["rina"]).status_code == 403
    res = client.post(
        f"/api/v1/owner/attendance/{ctx['rina_closed']}/corrections",
        headers=ctx["rina"],
        json={"clock_out_at": datetime.now(UTC).isoformat(), "reason": "x"},
    )
    assert res.status_code == 403


def test_correction_needs_a_reason_and_keeps_the_original(
    client: TestClient, ctx: dict[str, Any]
) -> None:
    rid = ctx["dodi_open"]
    y = ctx["yesterday"]
    out = datetime(y.year, y.month, y.day, 22, 15, tzinfo=WIB)
    res = client.post(
        f"/api/v1/owner/attendance/{rid}/corrections",
        headers=ctx["owner"],
        json={"clock_out_at": out.isoformat(), "reason": "   "},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "reason_required"
    res = client.post(
        f"/api/v1/owner/attendance/{rid}/corrections",
        headers=ctx["owner"],
        json={"clock_out_at": (out - timedelta(hours=12)).isoformat(), "reason": "salah"},
    )
    assert res.status_code == 422

    res = client.post(
        f"/api/v1/owner/attendance/{rid}/corrections",
        headers=ctx["owner"],
        json={"clock_out_at": out.isoformat(), "reason": "Lupa clock out, dikonfirmasi via chat"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "corrected"
    assert datetime.fromisoformat(body["clock_out_at"]) == out
    assert body["duration_minutes"] == 495
    assert body["original"]["clock_out_at"] is None
    assert body["flag"] is not None
    [c] = body["corrections"]
    assert c["reason"] == "Lupa clock out, dikonfirmasi via chat"
    assert c["from"]["clock_out_at"] is None
    assert datetime.fromisoformat(c["to"]["clock_out_at"]) == out
    assert c["by"] == "Owner" or c["by"]

    # Now counted in the totals, and no longer flagged.
    res = client.get(f"/api/v1/owner/attendance?from={y}&to={y}", headers=ctx["owner"])
    totals = {s["user"]["name"]: s for s in res.json()["summary"]}
    assert totals["Dodi"]["worked_minutes"] >= 495
    assert res.json()["needs_correction_count"] == 0


def test_open_record_cannot_be_corrected(client: TestClient, ctx: dict[str, Any]) -> None:
    rec = _tap(client, ctx["dago_tab"], RINA)
    res = client.post(
        f"/api/v1/owner/attendance/{rec['record_id']}/corrections",
        headers=ctx["owner"],
        json={"clock_out_at": datetime.now(UTC).isoformat(), "reason": "x"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "record_open"
    _tap(client, ctx["dago_tab"], RINA)


def test_csv_export(client: TestClient, ctx: dict[str, Any]) -> None:
    res = client.get(f"/api/v1/owner/attendance?{_range(ctx)}&format=csv", headers=ctx["owner"])
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0] == "tanggal,staf,outlet,zona,masuk,pulang,durasi_menit,status"
    assert any(",Maya,Canggu,WITA,09:00,17:10,490,closed" in line for line in lines)


def test_selfies_for_owner_and_the_person_only(client: TestClient, ctx: dict[str, Any]) -> None:
    rid = ctx["rina_closed"]
    res = client.get(f"/api/v1/owner/attendance/{rid}/selfies/in", headers=ctx["owner"])
    assert res.status_code == 200 and res.content == JPEG
    assert res.headers["cache-control"] == "private, no-store"
    res = client.get(f"/api/v1/ops/me/attendance/{rid}/selfies/out", headers=ctx["rina"])
    assert res.status_code == 200 and res.content == JPEG
    res = client.get(f"/api/v1/ops/me/attendance/{rid}/selfies/in", headers=ctx["dodi"])
    assert res.status_code == 404


def test_my_attendance_today_and_history(client: TestClient, ctx: dict[str, Any]) -> None:
    res = client.get("/api/v1/ops/me/attendance/today", headers=ctx["rina"])
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "not_clocked_in"

    rec = _tap(client, ctx["dago_tab"], RINA)
    res = client.get("/api/v1/ops/me/attendance/today", headers=ctx["rina"])
    body = res.json()
    assert body["status"] == "working"
    assert body["device_name"].startswith("Tablet ")
    assert body["outlet"] == {"name": "Dago", "timezone": "Asia/Jakarta"}
    assert body["flagged_records"] == []

    # Rina forgets to clock out: tomorrow's banner lists the flagged record.
    admin_sql(
        "update app.attendance_records set clock_in_at = now() - interval '3 days' where id = %s",
        (rec["record_id"],),
    )
    res = client.get("/api/v1/ops/me/attendance/today", headers=ctx["rina"])
    body = res.json()
    assert body["status"] == "not_clocked_in"
    assert [f["id"] for f in body["flagged_records"]] == [rec["record_id"]]

    res = client.get(f"/api/v1/ops/me/attendance?{_range(ctx)}", headers=ctx["rina"])
    assert res.status_code == 200, res.text
    hist = res.json()
    assert {r["user"]["name"] for r in hist["records"]} == {"Rina"}
    counted = sum(
        r["duration_minutes"] or 0
        for r in hist["records"]
        if r["status"] in ("closed", "corrected")
    )
    assert hist["total_minutes"] == counted
    assert hist["total_minutes"] >= 510


def test_selfies_are_purged_after_30_days(client: TestClient, ctx: dict[str, Any]) -> None:
    rid = ctx["maya_closed"]
    admin_sql(
        "update app.attendance_selfies set created_at = now() - interval '31 days'"
        " where id = (select clock_in_selfie_id from app.attendance_records where id = %s)",
        (rid,),
    )
    res = client.get(f"/api/v1/owner/attendance?{_range(ctx)}", headers=ctx["owner"])
    maya = next(r for r in res.json()["records"] if r["id"] == rid)
    assert maya["has_selfie_in"] is False  # photo gone, record kept
    assert maya["has_selfie_out"] is True
    assert maya["duration_minutes"] == 490
    res = client.get(f"/api/v1/owner/attendance/{rid}/selfies/in", headers=ctx["owner"])
    assert res.status_code == 404
