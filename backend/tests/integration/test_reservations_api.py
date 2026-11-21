"""Wave 6 API tests (T-057 to T-059, T-062 to T-065) against Postgres through RLS: tables and
reservation rules (O8), staff bookings with smallest-fit assignment, party and time rules
in the outlet time zone, double-booking refused by the database (also for concurrent
writes), walk-ins, reassignment, status actions with actor history, and the 15-minute
no-show release.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.core import reservations as core
from app.core.actor import ActorContext
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "w6.test"
OWNER = UUID("60000000-0000-0000-0000-0000000000f0")
STAFF = UUID("60000000-0000-0000-0000-0000000000f1")
WIB = ZoneInfo("Asia/Jakarta")
WITA = ZoneInfo("Asia/Makassar")

OPEN_ALL_DAY = {
    "is_enabled": True,
    "bookable_from": "00:00",
    "bookable_until": "23:59",
    "default_duration_minutes": 90,
    "booking_window_days": 14,
    "max_party_size": 8,
    "reminder_offset_minutes": 120,
    "cancellation_cutoff_minutes": 180,
}


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
        json={"business": {"name": "Kopi Enam", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, outlet = res.json()["tenant_id"], res.json()["outlet_id"]
    owner = _bearer(OWNER, tenant, "owner")
    res = client.post(
        "/api/v1/owner/outlets",
        headers=owner,
        json={"name": "Makassar", "timezone": "Asia/Makassar"},
    )
    assert res.status_code == 201, res.text
    other = res.json()["id"]
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
    tables: dict[str, str] = {}
    for name, cap, bookable in (
        ("M01", 2, True),
        ("M05", 4, True),
        ("M07", 4, True),
        ("M09", 6, True),
        ("M12", 4, False),
    ):
        res = client.post(
            f"/api/v1/owner/outlets/{outlet}/tables",
            headers=owner,
            json={"name": name, "capacity": cap, "area": "Indoor", "is_bookable": bookable},
        )
        assert res.status_code == 201, res.text
        tables[name] = res.json()["id"]
    for o in (outlet, other):
        res = client.put(
            f"/api/v1/owner/outlets/{o}/reservation-settings", headers=owner, json=OPEN_ALL_DAY
        )
        assert res.status_code == 200, res.text
    return {
        "tenant": tenant,
        "outlet": outlet,
        "other": other,
        "owner": owner,
        "staff": _bearer(STAFF, tenant, "staff"),
        "tables": tables,
    }


def _tomorrow(hour: int, minute: int = 0, tz: ZoneInfo = WIB) -> datetime:
    day = datetime.now(tz).date() + timedelta(days=1)
    return datetime.combine(day, time(hour, minute), tzinfo=tz)


def _book(client: TestClient, ctx: dict[str, Any], **body: Any):
    payload = {"guest_name": "Dewi", "party_size": 2, "source": "phone", **body}
    if isinstance(payload.get("starts_at"), datetime):
        payload["starts_at"] = payload["starts_at"].isoformat()
    outlet = payload.pop("outlet", ctx["outlet"])
    return client.post(
        f"/api/v1/ops/outlets/{outlet}/reservations", headers=ctx["staff"], json=payload
    )


def _clear(ctx: dict[str, Any]) -> None:
    admin_sql(
        "update app.reservations set status = 'cancelled' where tenant_id = %s"
        " and status in ('booked', 'seated')",
        (ctx["tenant"],),
    )


@pytest.fixture(autouse=True)
def fresh(ctx: dict[str, Any]) -> Iterator[None]:
    _clear(ctx)
    yield


def _insert_raw(ctx: dict[str, Any], table: str, starts_at: datetime, *, status: str = "booked"):
    """A booking written directly (bypassing time rules), e.g. one whose start has passed."""
    rows = admin_sql(
        "insert into app.reservations (tenant_id, outlet_id, table_id, guest_name, party_size,"
        " starts_at, ends_at, source, status, created_by_actor, created_by_id)"
        " values (%s, %s, %s, 'Lina', 3, %s, %s, 'phone', %s, 'user', %s) returning id",
        (
            ctx["tenant"],
            ctx["outlet"],
            ctx["tables"][table],
            starts_at,
            starts_at + timedelta(minutes=90),
            status,
            OWNER,
        ),
    )
    return str(rows[0][0])


# O8 · tables and rules (T-057) ------------------------------------------------------------
def test_tables_crud_and_owner_only(client, ctx) -> None:
    url = f"/api/v1/owner/outlets/{ctx['outlet']}/tables"
    names = [t["name"] for t in client.get(url, headers=ctx["owner"]).json()]
    assert names == ["M01", "M05", "M07", "M09", "M12"]
    assert client.get(url, headers=ctx["staff"]).status_code == 403
    assert (
        client.post(url, headers=ctx["staff"], json={"name": "X", "capacity": 2}).status_code == 403
    )

    dup = client.post(url, headers=ctx["owner"], json={"name": "m01", "capacity": 2})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "table_name_taken"

    vip = client.post(
        url, headers=ctx["owner"], json={"name": "VIP", "capacity": 10, "area": " Lantai  2 "}
    )
    assert vip.status_code == 201 and vip.json()["area"] == "Lantai 2"
    vip_id = vip.json()["id"]
    res = client.patch(f"/api/v1/owner/tables/{vip_id}", headers=ctx["owner"], json={"capacity": 8})
    assert res.json()["capacity"] == 8

    # An upcoming booking blocks deletion and shrinking below its party size.
    booking = _book(client, ctx, party_size=8, starts_at=_tomorrow(12), table_id=vip_id)
    assert booking.status_code == 201, booking.text
    res = client.delete(f"/api/v1/owner/tables/{vip_id}", headers=ctx["owner"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "table_in_use"
    res = client.patch(f"/api/v1/owner/tables/{vip_id}", headers=ctx["owner"], json={"capacity": 6})
    assert res.status_code == 409 and res.json()["error"]["code"] == "table_has_reservations"

    _clear(ctx)
    assert client.delete(f"/api/v1/owner/tables/{vip_id}", headers=ctx["owner"]).status_code == 204
    assert "VIP" not in [t["name"] for t in client.get(url, headers=ctx["owner"]).json()]
    # The name can be used again: the deactivated row comes back with the new values.
    again = client.post(url, headers=ctx["owner"], json={"name": "VIP", "capacity": 12})
    assert again.status_code == 201 and again.json()["id"] == vip_id
    assert again.json()["capacity"] == 12
    client.delete(f"/api/v1/owner/tables/{vip_id}", headers=ctx["owner"])


def test_reservation_settings(client, ctx) -> None:
    url = f"/api/v1/owner/outlets/{ctx['outlet']}/reservation-settings"
    body = client.get(url, headers=ctx["owner"]).json()
    assert body["hold_minutes"] == 15 and body["max_party_size"] == 8
    assert client.get(url, headers=ctx["staff"]).status_code == 403
    bad = client.put(
        url,
        headers=ctx["owner"],
        json={**OPEN_ALL_DAY, "bookable_from": "20:00", "bookable_until": "10:00"},
    )
    assert bad.status_code == 422 and bad.json()["error"]["details"]["field"] == "bookable_until"
    audit = admin_sql(
        "select count(*) from app.audit_events where action = 'reservation_settings.updated'"
        " and tenant_id = %s",
        (ctx["tenant"],),
    )
    assert audit[0][0] >= 2


# Bookings (T-058, T-059, T-062) -----------------------------------------------------------
def test_smallest_fitting_table_is_assigned(client, ctx) -> None:
    two = _book(client, ctx, party_size=2, starts_at=_tomorrow(12))
    assert two.status_code == 201, two.text
    assert two.json()["table_name"] == "M01"
    three = _book(client, ctx, party_size=3, starts_at=_tomorrow(12))
    assert (
        three.json()["table_name"] == "M05"
    )  # 4 seats, the smallest that fits; M12 is not bookable
    # M01 taken at 12:00, so another pair gets the next smallest free table.
    again = _book(client, ctx, party_size=2, starts_at=_tomorrow(12, 30))
    assert again.json()["table_name"] == "M07"
    detail = three.json()
    assert detail["status"] == "booked" and detail["source"] == "phone"
    hold = datetime.fromisoformat(detail["hold_until"])
    assert hold == _tomorrow(12) + timedelta(minutes=15)
    assert detail["allowed_actions"] == ["seat", "move", "cancel"]
    assert detail["events"][0]["event"] == "created" and detail["events"][0]["actor_name"] == "Rina"
    job = admin_sql(
        "select status::text, run_at from app.scheduled_jobs where job_key = %s",
        (f"no_show_release:{detail['id']}",),
    )
    assert job[0][0] == "pending" and job[0][1] == _tomorrow(12) + timedelta(minutes=15)


def test_party_and_time_rules(client, ctx) -> None:
    big = _book(client, ctx, party_size=9, starts_at=_tomorrow(12))
    assert big.status_code == 422 and big.json()["error"]["details"]["max_party_size"] == 8
    past = _book(client, ctx, starts_at=datetime.now(UTC) - timedelta(hours=1))
    assert past.status_code == 422 and past.json()["error"]["details"]["field"] == "starts_at"
    far = _book(client, ctx, starts_at=_tomorrow(12) + timedelta(days=20))
    assert far.status_code == 422 and far.json()["error"]["details"]["booking_window_days"] == 14
    small = _book(client, ctx, party_size=3, starts_at=_tomorrow(12), table_id=ctx["tables"]["M01"])
    assert small.status_code == 422 and small.json()["error"]["details"]["capacity"] == 2
    closed = _book(
        client, ctx, party_size=2, starts_at=_tomorrow(12), table_id=ctx["tables"]["M12"]
    )
    assert closed.status_code == 422
    naive = _book(client, ctx, starts_at="2030-01-01T12:00:00")
    assert naive.status_code == 422


def test_bookable_hours_use_outlet_time_zone(client, ctx) -> None:
    url = f"/api/v1/owner/outlets/{ctx['other']}/reservation-settings"
    client.put(
        url,
        headers=ctx["owner"],
        json={**OPEN_ALL_DAY, "bookable_from": "10:00", "bookable_until": "20:00"},
    )
    table = client.post(
        f"/api/v1/owner/outlets/{ctx['other']}/tables",
        headers=ctx["owner"],
        json={"name": "A1", "capacity": 4},
    ).json()
    owner_ctx = {**ctx, "staff": ctx["owner"]}
    # 19:30 WIB is 20:30 WITA: after the Makassar outlet's last booking time.
    late = _book(client, owner_ctx, outlet=ctx["other"], starts_at=_tomorrow(19, 30, WIB))
    assert late.status_code == 422 and late.json()["error"]["details"]["bookable_until"] == "20:00"
    # 19:00 WITA sent with a WIB offset (18:00+07:00) is the same instant and is accepted.
    ok = _book(
        client, owner_ctx, outlet=ctx["other"], starts_at=_tomorrow(19, 0, WITA).astimezone(WIB)
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["timezone"] == "Asia/Makassar"
    # The board groups by the outlet-local day.
    day = _tomorrow(19, 0, WITA).date().isoformat()
    board = client.get(
        f"/api/v1/ops/outlets/{ctx['other']}/reservations?date={day}", headers=ctx["owner"]
    ).json()
    assert board["timezone"] == "Asia/Makassar" and board["date"] == day
    assert [r["id"] for r in board["reservations"]] == [ok.json()["id"]]
    assert board["settings"]["bookable_until"] == "20:00:00"
    client.delete(f"/api/v1/owner/tables/{table['id']}", headers=ctx["owner"])


def test_double_booking_refused(client, ctx) -> None:
    m09 = ctx["tables"]["M09"]
    first = _book(client, ctx, party_size=5, starts_at=_tomorrow(18), table_id=m09)
    assert first.status_code == 201
    clash = _book(client, ctx, party_size=5, starts_at=_tomorrow(19), table_id=m09)
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "conflict"
    # Back-to-back is fine: the range is [start, end).
    after = _book(client, ctx, party_size=5, starts_at=_tomorrow(19, 30), table_id=m09)
    assert after.status_code == 201
    # Auto-assign: M09 is the only table for 6, so a third overlapping party has no table.
    none_left = _book(client, ctx, party_size=6, starts_at=_tomorrow(18, 30))
    assert (
        none_left.status_code == 409 and none_left.json()["error"]["code"] == "no_table_available"
    )
    # A write that skips the application is still refused by the database (US-024).
    with pytest.raises(psycopg.errors.ExclusionViolation):
        _insert_raw(ctx, "M09", _tomorrow(18, 45))


def test_concurrent_writes_cannot_double_book(ctx) -> None:
    starts = _tomorrow(15)
    sql = (
        "insert into app.reservations (tenant_id, outlet_id, table_id, party_size, starts_at,"
        " ends_at, source, created_by_actor) values (%s, %s, %s, 2, %s, %s, 'phone', 'system')"
    )
    params = (
        ctx["tenant"],
        ctx["outlet"],
        ctx["tables"]["M01"],
        starts,
        starts + timedelta(hours=1),
    )
    errors: list[BaseException] = []
    assert ADMIN_URL
    with psycopg.connect(ADMIN_URL) as first:
        first.execute(sql, params)  # not committed yet

        def second() -> None:
            try:
                with psycopg.connect(ADMIN_URL) as conn:
                    conn.execute(sql, params)  # waits for `first`, then fails
            except BaseException as exc:
                errors.append(exc)

        t = threading.Thread(target=second)
        t.start()
        t.join(timeout=0.5)
        assert t.is_alive()  # blocked on the first transaction
        first.commit()
        t.join(timeout=5)
    assert len(errors) == 1 and isinstance(errors[0], psycopg.errors.ExclusionViolation)


# Walk-ins (T-063) ------------------------------------------------------------------------
def test_walk_in_blocks_bookings(client, ctx) -> None:
    url = f"/api/v1/ops/outlets/{ctx['outlet']}/walk-ins"
    m05 = ctx["tables"]["M05"]
    res = client.post(url, headers=ctx["staff"], json={"table_id": m05, "party_size": 3})
    assert res.status_code == 201, res.text
    walk = res.json()
    assert walk["status"] == "seated" and walk["source"] == "walk_in" and walk["guest_name"] is None
    assert walk["allowed_actions"] == ["complete", "move", "cancel"]
    # The occupied table is not offered for an overlapping booking.
    soon = datetime.now(UTC) + timedelta(minutes=30)
    taken = _book(client, ctx, party_size=3, starts_at=soon, table_id=m05)
    assert taken.status_code == 409
    auto = _book(client, ctx, party_size=3, starts_at=soon)
    assert auto.json()["table_name"] == "M07"
    # A second walk-in on the same table is refused; too many guests too.
    again = client.post(url, headers=ctx["staff"], json={"table_id": m05, "party_size": 2})
    assert again.status_code == 409
    crowd = client.post(
        url, headers=ctx["staff"], json={"table_id": ctx["tables"]["M01"], "party_size": 3}
    )
    assert crowd.status_code == 422
    # Non-bookable tables can still be marked occupied.
    m12 = client.post(
        url, headers=ctx["staff"], json={"table_id": ctx["tables"]["M12"], "party_size": 2}
    )
    assert m12.status_code == 201
    # Guests leave: "Selesai" frees the table.
    assert (
        client.post(
            f"/api/v1/ops/reservations/{walk['id']}/complete", headers=ctx["staff"]
        ).status_code
        == 204
    )
    freed = _book(client, ctx, party_size=3, starts_at=soon, table_id=m05)
    assert freed.status_code == 201, freed.text


# Actions, reassignment, history (T-062) ----------------------------------------------------
def test_move_cancel_and_history(client, ctx) -> None:
    res = _book(client, ctx, party_size=4, starts_at=_tomorrow(13))
    rid = res.json()["id"]
    assert res.json()["table_name"] == "M05"
    blocker = _book(
        client, ctx, party_size=4, starts_at=_tomorrow(13), table_id=ctx["tables"]["M07"]
    )
    assert blocker.status_code == 201
    base = f"/api/v1/ops/reservations/{rid}"
    taken = client.post(
        f"{base}/move", headers=ctx["staff"], json={"table_id": ctx["tables"]["M07"]}
    )
    assert taken.status_code == 409
    small = client.post(
        f"{base}/move", headers=ctx["staff"], json={"table_id": ctx["tables"]["M01"]}
    )
    assert small.status_code == 422
    ok = client.post(f"{base}/move", headers=ctx["owner"], json={"table_id": ctx["tables"]["M09"]})
    assert ok.status_code == 204
    # Too early for no-show; cancel works and then nothing else is allowed.
    early = client.post(f"{base}/no-show", headers=ctx["staff"])
    assert early.status_code == 409 and early.json()["error"]["code"] == "too_early"
    assert client.post(f"{base}/cancel", headers=ctx["staff"]).status_code == 204
    again = client.post(f"{base}/seat", headers=ctx["staff"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_transition"
    detail = client.get(base, headers=ctx["staff"]).json()
    assert detail["status"] == "cancelled" and detail["allowed_actions"] == []
    events = [(e["event"], e["to_status"], e["actor_name"]) for e in detail["events"]]
    assert events == [
        ("created", "booked", "Rina"),
        ("table_changed", None, detail["events"][1]["actor_name"]),
        ("status_changed", "cancelled", "Rina"),
    ]
    assert detail["events"][1]["from_table"] == "M05" and detail["events"][1]["to_table"] == "M09"
    assert detail["events"][1]["actor_type"] == "user"
    assert detail["events"][1]["actor_name"] not in (None, "Rina")  # moved by the owner
    job = admin_sql(
        "select status::text from app.scheduled_jobs where job_key = %s",
        (f"no_show_release:{rid}",),
    )
    assert job[0][0] == "cancelled"
    # Events are append-only.
    with pytest.raises(psycopg.errors.RestrictViolation):
        admin_sql("update app.reservation_events set event = 'x' where reservation_id = %s", (rid,))


def test_phone_is_masked_in_detail(client, ctx) -> None:
    res = _book(client, ctx, guest_phone="+62 813 1234 5090", starts_at=_tomorrow(14))
    assert res.json()["phone_masked"] == "+62 813-xxxx-090"
    assert "guest_phone" not in res.json()
    # Stored encrypted (glossary §10); the board and the detail decrypt in the API.
    stored = admin_sql(
        "select guest_name, guest_phone, guest_phone_index from app.reservations where id = %s",
        (res.json()["id"],),
    )[0]
    assert stored[0].startswith("enc:v1:") and stored[1].startswith("enc:v1:")
    assert len(stored[2]) == 64 and "5090" not in stored[1]
    assert res.json()["guest_name"] == "Dewi"


# No-show hold (T-064) --------------------------------------------------------------------
def test_no_show_after_hold_releases_table(client, ctx) -> None:
    now = datetime.now(UTC)
    late = _insert_raw(ctx, "M09", now - timedelta(minutes=16))
    board = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/reservations", headers=ctx["staff"]
    ).json()
    row = next(r for r in board["reservations"] if r["id"] == late)
    assert row["status"] == "no_show" and row["hold_until"] is None and row["no_show_at"]
    event = admin_sql(
        "select actor_type::text, actor_id, data->>'reason' from app.reservation_events"
        " where reservation_id = %s and to_status = 'no_show'",
        (late,),
    )
    assert event == [("system", None, "hold_expired")]
    # The table is free again for the rest of that slot.
    res = _book(
        client,
        ctx,
        party_size=5,
        starts_at=now + timedelta(minutes=10),
        table_id=ctx["tables"]["M09"],
    )
    assert res.status_code == 201, res.text
    seat = client.post(f"/api/v1/ops/reservations/{late}/seat", headers=ctx["staff"])
    assert seat.status_code == 409 and seat.json()["error"]["code"] == "hold_expired"


def test_seated_before_deadline_stays_seated(client, ctx) -> None:
    now = datetime.now(UTC)
    rid = _insert_raw(ctx, "M05", now - timedelta(minutes=10))
    detail = client.get(f"/api/v1/ops/reservations/{rid}", headers=ctx["staff"]).json()
    assert detail["status"] == "booked"
    assert detail["allowed_actions"] == ["seat", "move", "cancel", "no_show"]
    assert (
        client.post(f"/api/v1/ops/reservations/{rid}/seat", headers=ctx["staff"]).status_code == 204
    )
    admin_sql(
        "update app.reservations set starts_at = starts_at - interval '1 hour',"
        " ends_at = ends_at - interval '1 hour' where id = %s",
        (rid,),
    )
    detail = client.get(f"/api/v1/ops/reservations/{rid}", headers=ctx["staff"]).json()
    assert detail["status"] == "seated"


def test_manual_no_show_after_start(client, ctx) -> None:
    rid = _insert_raw(ctx, "M07", datetime.now(UTC) - timedelta(minutes=5))
    assert (
        client.post(f"/api/v1/ops/reservations/{rid}/no-show", headers=ctx["staff"]).status_code
        == 204
    )
    detail = client.get(f"/api/v1/ops/reservations/{rid}", headers=ctx["staff"]).json()
    assert detail["status"] == "no_show" and detail["events"][-1]["actor_name"] == "Rina"


# Access ----------------------------------------------------------------------------------
def test_staff_cannot_reach_unassigned_outlet(client, ctx) -> None:
    url = f"/api/v1/ops/outlets/{ctx['other']}/reservations"
    assert client.get(url, headers=ctx["staff"]).status_code == 404
    res = _book(client, ctx, outlet=ctx["other"], starts_at=_tomorrow(12))
    assert res.status_code == 404
    owner_ctx = {**ctx, "staff": ctx["owner"]}
    table = client.post(
        f"/api/v1/owner/outlets/{ctx['other']}/tables",
        headers=ctx["owner"],
        json={"name": "B1", "capacity": 4},
    ).json()
    theirs = _book(client, owner_ctx, outlet=ctx["other"], starts_at=_tomorrow(12, tz=WITA))
    assert theirs.status_code == 201, theirs.text
    rid = theirs.json()["id"]
    assert client.get(f"/api/v1/ops/reservations/{rid}", headers=ctx["staff"]).status_code == 404
    assert (
        client.post(f"/api/v1/ops/reservations/{rid}/cancel", headers=ctx["staff"]).status_code
        == 404
    )
    # A table from another outlet cannot be used here.
    cross = _book(client, ctx, starts_at=_tomorrow(12), table_id=table["id"])
    assert cross.status_code == 422
    client.post(f"/api/v1/ops/reservations/{rid}/cancel", headers=ctx["owner"])
    client.delete(f"/api/v1/owner/tables/{table['id']}", headers=ctx["owner"])


# Availability for the WhatsApp flow (T-058) ------------------------------------------------
async def test_available_start_times(client, ctx) -> None:
    assert APP_URL
    pool = db.create_pool(APP_URL, min_size=1, max_size=1)
    await pool.open()
    try:
        actor = ActorContext.for_user(UUID(ctx["tenant"]), OWNER)
        day: date = _tomorrow(12).date()
        async with db.transaction(pool, actor) as conn:
            await conn.execute(
                "update app.reservation_settings set bookable_from = '10:00',"
                " bookable_until = '12:00' where outlet_id = %s",
                (ctx["outlet"],),
            )
            # Only M09 seats 6; booking it 10:00-11:30 removes the slots that overlap.
            await core.create_booking(
                conn,
                actor,
                UUID(ctx["outlet"]),
                party_size=6,
                starts_at=_tomorrow(10),
                source="phone",
                guest_name="Ani",
            )
            times = await core.available_start_times(
                conn, UUID(ctx["outlet"]), day, 6, now=datetime.now(UTC)
            )
            local = [t.astimezone(WIB).strftime("%H:%M") for t in times]
            assert local == ["11:30", "12:00"]
            pairs = await core.available_start_times(
                conn, UUID(ctx["outlet"]), day, 2, now=datetime.now(UTC)
            )
            assert len(pairs) == 5  # 10:00 … 12:00 every 30 minutes
            await conn.execute("select 1/0")  # roll back the settings change
    except psycopg.errors.DivisionByZero:
        pass
    finally:
        await pool.close()
