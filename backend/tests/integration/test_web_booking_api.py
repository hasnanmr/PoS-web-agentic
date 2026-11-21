"""Reservations in the customer web chat (T-060, T-061) against Postgres through RLS.

Wireframes C10-C12 on page 07; PRD FR9.2, FR9.4, FR9.5, FR12.2; AC9.1-AC9.3, AC9.5, AC9.6,
AC9.9, AC9.11, AC9.12, AC12.2.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import public_outlet
from app.config import Settings
from app.core.web_chat import PRIVACY_NOTICE_VERSION
from app.main import create_app

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "webbooking.test"
OWNER = UUID("72000000-0000-0000-0000-0000000000a0")
WITA = ZoneInfo("Asia/Makassar")
SETTINGS = {
    "is_enabled": True,
    "bookable_from": "00:00",
    "bookable_until": "23:59",
    "default_duration_minutes": 90,
    "booking_window_days": 14,
    "max_party_size": 6,
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
        json={
            "business": {"name": "Kopi Booking", "type": "cafe"},
            "outlet": {"name": "Losari"},
        },
    )
    assert res.status_code == 201, res.text
    tenant, outlet = res.json()["tenant_id"], res.json()["outlet_id"]
    owner = _bearer(OWNER, tenant, "owner")
    admin_sql("update app.outlets set timezone = 'Asia/Makassar' where id = %s", (outlet,))
    tables = {}
    for name, cap in (("M01", 2), ("M05", 4), ("M09", 6)):
        res = client.post(
            f"/api/v1/owner/outlets/{outlet}/tables",
            headers=owner,
            json={"name": name, "capacity": cap, "area": "Indoor"},
        )
        assert res.status_code == 201, res.text
        tables[name] = res.json()["id"]
    slug = f"losari-{uuid4().hex[:6]}"
    admin_sql("update app.outlets set public_slug = %s where id = %s", (slug, outlet))
    return {"tenant": tenant, "outlet": outlet, "owner": owner, "slug": slug, "tables": tables}


@pytest.fixture(scope="module")
def enabled(client: TestClient, ctx: dict[str, Any]) -> dict[str, Any]:
    res = client.put(
        f"/api/v1/owner/outlets/{ctx['outlet']}/reservation-settings",
        headers=ctx["owner"],
        json=SETTINGS,
    )
    assert res.status_code == 200, res.text
    return ctx


def _base(ctx: dict[str, Any]) -> str:
    return f"/api/v1/public/o/{ctx['slug']}"


def _tomorrow_at(hour: int, minute: int = 0) -> datetime:
    day = datetime.now(WITA).date() + timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=WITA)


def _book(
    client: TestClient,
    ctx: dict[str, Any],
    start: datetime,
    *,
    party: int = 4,
    phone: str = "0811-1111-1111",
    name: str = "Dewi",
    key: str | None = None,
    booking_key: str | None = None,
) -> Any:
    return client.post(
        f"{_base(ctx)}/reservations",
        headers={"Idempotency-Key": key or uuid4().hex, "X-Booking-Key": booking_key or _new_key()},
        json={
            "party_size": party,
            "start_at": start.isoformat(),
            "customer": {"name": name, "phone": phone},
            "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        },
    )


def _new_key() -> str:
    return "b-" + uuid4().hex + uuid4().hex


def _booked(client: TestClient, ctx: dict[str, Any], start: datetime, **kw: Any) -> dict[str, Any]:
    res = _book(client, ctx, start, **kw)
    assert res.status_code == 201, res.text
    return res.json()


def _cancel(client: TestClient, ctx: dict[str, Any], b: dict[str, Any]) -> Any:
    return client.post(
        f"{_base(ctx)}/reservations/{b['reservation_id']}/cancel",
        headers={"X-Booking-Key": b["access_key"]},
    )  # without Idempotency-Key: cancel is idempotent by itself


def test_disabled_outlet_takes_no_bookings(client, ctx) -> None:
    res = client.get(f"{_base(ctx)}/availability", params={"party_size": 2, "date": "2030-01-01"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "reservations_unavailable"
    table = admin_sql("select qr_token from app.tables where outlet_id = %s", (ctx["outlet"],))
    assert client.get(f"/api/v1/public/t/{table[0][0]}/availability").status_code == 404


def test_availability_respects_party_limit_and_local_time(client, enabled) -> None:
    ctx = enabled
    day = _tomorrow_at(0).date().isoformat()
    res = client.get(f"{_base(ctx)}/availability", params={"party_size": 7, "date": day})
    assert res.status_code == 422  # AC9.1
    assert res.json()["error"]["code"] == "party_too_large"
    assert res.json()["error"]["details"]["max"] == 6
    res = client.get(f"{_base(ctx)}/availability", params={"party_size": 4, "date": day})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["timezone"] == "Asia/Makassar" and out["max_party_size"] == 6
    labels = [t["label"] for t in out["times"]]
    assert "19:00" in labels  # AC9.9: outlet-local labels
    slot = next(t for t in out["times"] if t["label"] == "19:00")
    assert datetime.fromisoformat(slot["start_at"]) == _tomorrow_at(19)


def test_booking_gets_smallest_table_code_and_staff_view(client, enabled) -> None:
    ctx = enabled
    key, booking_key = uuid4().hex, _new_key()
    b = _booked(
        client, ctx, _tomorrow_at(12), key=key, booking_key=booking_key, phone="0812 2222 0001"
    )
    assert re.fullmatch(r"[A-HJKMNP-Z2-9]{6}", b["booking_code"])
    assert b["label"] == "12:00" and b["party_size"] == 4 and b["can_change"] is True
    assert b["access_key"] == booking_key  # the page's own key, echoed
    again = _book(
        client, ctx, _tomorrow_at(12), key=key, booking_key=booking_key, phone="0812 2222 0001"
    )
    assert again.status_code == 200 and again.json()["reservation_id"] == b["reservation_id"]
    assert again.json()["access_key"] == booking_key
    other = _book(client, ctx, _tomorrow_at(12), key=key, phone="0812 2222 0001")
    assert other.status_code == 409  # same Idempotency-Key, another booking key
    stored = admin_sql(
        "select count(*) from app.idempotency_keys where response::text like %s",
        (f"%{booking_key}%",),
    )
    assert stored == [(0,)]  # never in plaintext
    missing = client.post(
        f"{_base(ctx)}/reservations",
        headers={"Idempotency-Key": uuid4().hex},
        json={
            "party_size": 2,
            "start_at": _tomorrow_at(11).isoformat(),
            "customer": {"name": "Dewi", "phone": "081222220009"},
            "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        },
    )
    assert missing.status_code == 422
    row = admin_sql(
        "select r.table_id::text, r.source::text, r.guest_phone, c.name, a.notice_version"
        " from app.reservations r join app.customers c on c.id = r.customer_id"
        " join app.privacy_notice_acknowledgements a on a.customer_id = c.id where r.id = %s",
        (b["reservation_id"],),
    )
    assert row == [
        (ctx["tables"]["M05"], "web_chat", "081222220001", "Dewi", PRIVACY_NOTICE_VERSION)
    ]
    board = client.get(
        f"/api/v1/ops/outlets/{ctx['outlet']}/reservations",
        headers=ctx["owner"],
        params={"date": _tomorrow_at(12).date().isoformat()},
    )
    if board.status_code == 200:
        mine = [r for r in board.json()["reservations"] if r["id"] == b["reservation_id"]]
        assert mine and mine[0]["source"] == "web_chat" and mine[0]["guest_name"] == "Dewi"


def test_two_upcoming_bookings_per_phone(client, enabled) -> None:
    ctx = enabled
    phone = "0813-3333-0002"
    _booked(client, ctx, _tomorrow_at(9), phone=phone, party=2)
    _booked(client, ctx, _tomorrow_at(10), phone=phone, party=2)
    before = admin_sql(
        "select count(*) from app.reservations where outlet_id = %s", (ctx["outlet"],)
    )
    res = _book(client, ctx, _tomorrow_at(15), phone="081333330002")  # same number, other format
    assert res.status_code == 409 and res.json()["error"]["code"] == "booking_limit_reached"
    after = admin_sql(
        "select count(*) from app.reservations where outlet_id = %s", (ctx["outlet"],)
    )
    assert after == before  # AC9.11: no table held
    assert _book(client, ctx, _tomorrow_at(15), phone="0813-3333-0003", party=2).status_code == 201


def test_full_time_is_slot_unavailable(client, enabled) -> None:
    ctx = enabled
    start = _tomorrow_at(20)
    _booked(client, ctx, start, party=6, phone="0814-0000-0001")  # M09
    _booked(client, ctx, start, party=4, phone="0814-0000-0002")  # M05
    res = _book(client, ctx, start, party=4, phone="0814-0000-0003")
    assert res.status_code == 409 and res.json()["error"]["code"] == "slot_unavailable"
    day = start.date().isoformat()
    times = client.get(f"{_base(ctx)}/availability", params={"party_size": 4, "date": day}).json()
    assert "20:00" not in [t["label"] for t in times["times"]]


def test_reservasi_saya_and_lookup_from_another_phone(client, enabled) -> None:
    ctx = enabled
    b = _booked(client, ctx, _tomorrow_at(13), party=2, phone="0815-5555-0001")
    url = f"{_base(ctx)}/reservations/{b['reservation_id']}"
    assert client.get(url, headers={"X-Booking-Key": b["access_key"]}).status_code == 200
    assert client.get(url, headers={"X-Booking-Key": "x" * 32}).status_code == 404
    assert client.get(url).status_code == 404
    listed = client.post(
        f"{_base(ctx)}/reservations/status",
        json={
            "reservations": [
                {"id": b["reservation_id"], "key": b["access_key"]},
                {"id": str(uuid4()), "key": "unknown-key-0001"},
            ]
        },
    )
    assert [r["reservation_id"] for r in listed.json()] == [b["reservation_id"]]
    # AC9.12: code + phone on phone 2 → its own key; phone 1's key still works.
    found = client.post(
        f"{_base(ctx)}/reservations/lookup",
        json={"booking_code": b["booking_code"].lower(), "phone": "081555550001"},
    )
    assert found.status_code == 200, found.text
    assert found.json()["reservation_id"] == b["reservation_id"]
    key2 = found.json()["access_key"]
    assert client.get(url, headers={"X-Booking-Key": key2}).status_code == 200
    assert client.get(url, headers={"X-Booking-Key": b["access_key"]}).status_code == 200
    for wrong in (
        {"booking_code": b["booking_code"], "phone": "081555550009"},
        {"booking_code": "ZZZZZZ", "phone": "081555550001"},
    ):
        res = client.post(f"{_base(ctx)}/reservations/lookup", json=wrong)
        assert res.status_code == 404 and res.json()["error"]["code"] == "booking_not_found"


def test_cancel_until_cutoff_then_closed(client, enabled) -> None:
    ctx = enabled
    b = _booked(client, ctx, _tomorrow_at(14), party=2, phone="0816-6666-0001")
    res = _cancel(client, ctx, b)
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert _cancel(client, ctx, b).status_code == 200  # repeat is harmless
    anon = admin_sql(
        "select r.guest_name, r.guest_phone, c.is_anonymized from app.reservations r"
        " join app.customers c on c.id = r.customer_id where r.id = %s",
        (b["reservation_id"],),
    )
    assert anon == [(None, None, True)]  # AC12.2
    # AC9.6: inside the 3-hour cutoff → refused.
    soon = (datetime.now(UTC) + timedelta(hours=2)).replace(second=0, microsecond=0)
    near = _booked(client, ctx, soon, party=2, phone="0816-6666-0002")
    assert near["can_change"] is False
    res = _cancel(client, ctx, near)
    assert res.status_code == 409 and res.json()["error"]["code"] == "change_window_closed"


def test_reschedule_to_a_free_time(client, enabled) -> None:
    ctx = enabled
    b = _booked(client, ctx, _tomorrow_at(16), party=2, phone="0817-7777-0001")
    url = f"{_base(ctx)}/reservations/{b['reservation_id']}/reschedule"
    headers = {"X-Booking-Key": b["access_key"], "Idempotency-Key": uuid4().hex}
    res = client.post(url, headers=headers, json={"start_at": _tomorrow_at(17).isoformat()})
    assert res.status_code == 200, res.text
    assert res.json()["label"] == "17:00" and res.json()["booking_code"] == b["booking_code"]
    job = admin_sql(
        "select run_at from app.scheduled_jobs where job_key = %s",
        (f"no_show_release:{b['reservation_id']}",),
    )
    assert job[0][0] == _tomorrow_at(17, 15)
    # A time with no table left for the party.
    _booked(client, ctx, _tomorrow_at(22, 30), party=6, phone="0817-7777-0002")
    _booked(client, ctx, _tomorrow_at(22, 30), party=4, phone="0817-7777-0003")
    _booked(client, ctx, _tomorrow_at(22, 30), party=2, phone="0817-7777-0004")
    res = client.post(
        url,
        headers={"X-Booking-Key": b["access_key"], "Idempotency-Key": uuid4().hex},
        json={"start_at": _tomorrow_at(22, 30).isoformat()},
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "slot_unavailable"


def test_calendar_file_has_alert_at_reminder_time(client, enabled) -> None:
    ctx = enabled
    b = _booked(client, ctx, _tomorrow_at(18, 30), party=2, phone="0818-8888-0001")
    url = f"{_base(ctx)}/reservations/{b['reservation_id']}/calendar.ics"
    assert client.get(url, params={"key": "x" * 32}).status_code == 404
    res = client.get(url, params={"key": b["access_key"]})
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/calendar")
    text = res.text
    start = _tomorrow_at(18, 30).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    assert f"DTSTART:{start}" in text and "TRIGGER:-PT120M" in text  # AC9.5
    assert b["booking_code"] in text and "Losari" in text


def test_repeated_wrong_lookups_are_limited(client, enabled) -> None:
    ctx = enabled
    public_outlet._misses.clear()
    try:
        codes = []
        for _ in range(6):
            res = client.post(
                f"{_base(ctx)}/reservations/lookup",
                json={"booking_code": "QQQQQQ", "phone": "081900000000"},
            )
            codes.append(res.status_code)
        assert codes[:5] == [404] * 5 and codes[5] == 429
    finally:
        public_outlet._misses.clear()


def test_reschedule_leaves_a_table_that_is_no_longer_bookable(client, enabled) -> None:
    ctx = enabled
    b = _booked(client, ctx, _tomorrow_at(8), party=2, phone="0819-1000-0001")
    table = admin_sql(
        "select table_id::text from app.reservations where id = %s", (b["reservation_id"],)
    )[0][0]
    admin_sql("update app.tables set is_bookable = false where id = %s", (table,))
    try:
        res = client.post(
            f"{_base(ctx)}/reservations/{b['reservation_id']}/reschedule",
            headers={"X-Booking-Key": b["access_key"], "Idempotency-Key": uuid4().hex},
            json={"start_at": _tomorrow_at(8, 30).isoformat()},
        )
        assert res.status_code == 200, res.text
        moved = admin_sql(
            "select table_id::text from app.reservations where id = %s", (b["reservation_id"],)
        )[0][0]
        assert moved != table
    finally:
        admin_sql("update app.tables set is_bookable = true where id = %s", (table,))


def test_replays_need_the_key_and_cache_no_personal_data(client, enabled) -> None:
    ctx = enabled
    key, booking_key = uuid4().hex, _new_key()
    b = _booked(
        client,
        ctx,
        _tomorrow_at(7),
        key=key,
        booking_key=booking_key,
        party=2,
        phone="0819-2000-0001",
        name="Laras",
    )
    cached = admin_sql("select response::text from app.idempotency_keys where key = %s", (key,))[0][
        0
    ]
    assert "Laras" not in cached and booking_key not in cached  # only the reservation id
    url = f"{_base(ctx)}/reservations/{b['reservation_id']}/reschedule"
    body = {"start_at": _tomorrow_at(7, 30).isoformat()}
    idem = uuid4().hex
    ok = client.post(
        url, headers={"X-Booking-Key": booking_key, "Idempotency-Key": idem}, json=body
    )
    assert ok.status_code == 200, ok.text
    stolen = client.post(
        url, headers={"X-Booking-Key": "x" * 40, "Idempotency-Key": idem}, json=body
    )
    assert stolen.status_code in (404, 409) and "Laras" not in stolen.text
    again = client.post(
        url, headers={"X-Booking-Key": booking_key, "Idempotency-Key": idem}, json=body
    )
    assert again.status_code == 200 and again.json()["label"] == "07:30"


def test_cancel_records_the_customer_reason_and_hides_the_calendar(client, enabled) -> None:
    ctx = enabled
    b = _booked(client, ctx, _tomorrow_at(11, 30), party=2, phone="0819-3000-0001")
    res = client.post(
        f"{_base(ctx)}/reservations/{b['reservation_id']}/cancel",
        headers={"X-Booking-Key": b["access_key"], "Idempotency-Key": uuid4().hex},
    )
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    reason = admin_sql(
        "select data->>'reason' from app.reservation_events where reservation_id = %s"
        " and to_status = 'cancelled'",
        (b["reservation_id"],),
    )
    assert reason == [("Dibatalkan pelanggan dari web chat",)]
    ics = client.get(
        f"{_base(ctx)}/reservations/{b['reservation_id']}/calendar.ics",
        params={"key": b["access_key"]},
    )
    assert ics.status_code == 404


def test_calendar_lines_are_folded(client, enabled) -> None:
    ctx = enabled
    long_name = "Kopi Losari Pantai Makassar Cabang Utama Dekat Anjungan"
    admin_sql("update app.outlets set name = %s where id = %s", (long_name, ctx["outlet"]))
    try:
        b = _booked(client, ctx, _tomorrow_at(12, 30), party=2, phone="0819-4000-0001")
        text = client.get(
            f"{_base(ctx)}/reservations/{b['reservation_id']}/calendar.ics",
            params={"key": b["access_key"]},
        ).text
        assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
        unfolded = text.replace("\r\n ", "")
        assert f"LOCATION:{long_name}" in unfolded and "15 menit" in unfolded
    finally:
        admin_sql("update app.outlets set name = 'Losari' where id = %s", (ctx["outlet"],))


def test_lookup_keys_are_capped_per_booking(client, enabled) -> None:
    ctx = enabled
    b = _booked(client, ctx, _tomorrow_at(13, 30), party=2, phone="0819-5000-0001")
    keys = []
    for _ in range(7):
        res = client.post(
            f"{_base(ctx)}/reservations/lookup",
            json={"booking_code": b["booking_code"], "phone": "081950000001"},
        )
        assert res.status_code == 200
        keys.append(res.json()["access_key"])
    count = admin_sql(
        "select count(*) from app.reservation_access_keys where reservation_id = %s",
        (b["reservation_id"],),
    )
    assert count == [(5,)]
    url = f"{_base(ctx)}/reservations/{b['reservation_id']}"
    assert client.get(url, headers={"X-Booking-Key": keys[-1]}).status_code == 200
    assert client.get(url, headers={"X-Booking-Key": keys[0]}).status_code == 404  # oldest gone
    assert client.get(url, headers={"X-Booking-Key": b["access_key"]}).status_code == 200


def test_lookup_guard_keeps_no_entry_without_a_miss(client, enabled) -> None:
    public_outlet._misses.clear()
    b = _booked(client, enabled, _tomorrow_at(14, 30), party=2, phone="0819-6000-0001")
    res = client.post(
        f"{_base(enabled)}/reservations/lookup",
        json={"booking_code": b["booking_code"], "phone": "081960000001"},
    )
    assert res.status_code == 200 and public_outlet._misses == {}
