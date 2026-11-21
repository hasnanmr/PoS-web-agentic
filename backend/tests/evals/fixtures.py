"""Outlets for the agent evaluation set, built through the real API against the test database.

* `o`: outlet link, Asia/Jakarta (WIB), PB1 10 %, delivery fee Rp 10.000, one 4-seat table,
  reservations on, Croissant Butter sold out, and the day after tomorrow at 19:00 already
  booked (the full-slot case);
* `o_wita`: a second business, outlet link, Asia/Makassar (WITA), one 2-seat table;
* `t`: the table QR of outlet `o`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.core.web_chat import PRIVACY_NOTICE_VERSION
from tests.auth.keys import make_token
from tests.evals.harness import World
from tests.integration._db import admin_sql, cleanup_domain, invite_owner, plain

DOMAIN = "agent-eval.test"
OWNERS = {
    "o": UUID("74000000-0000-0000-0000-0000000000a0"),
    "o_wita": UUID("74000000-0000-0000-0000-0000000000b0"),
}
RESERVATIONS = {
    "is_enabled": True,
    "bookable_from": "10:00",
    "bookable_until": "21:00",
    "default_duration_minutes": 90,
    "booking_window_days": 14,
    "max_party_size": 6,
    "reminder_offset_minutes": 120,
    "cancellation_cutoff_minutes": 180,
}


def _bearer(sub: UUID, tenant: str | None, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=str(sub), tenant_id=tenant, app_role=role)}"}


def cleanup() -> None:
    cleanup_domain(DOMAIN)


def _outlet(
    client: TestClient, key: str, name: str, timezone: str, capacity: int
) -> dict[str, Any]:
    owner_id = OWNERS[key]
    invite_owner(owner_id, f"{key.replace('_', '-')}@{DOMAIN}")
    res = client.post(
        "/api/v1/owner/onboarding",
        headers=_bearer(owner_id, None, "owner_pending"),
        json={
            "business": {"name": f"Eval {name}", "type": "cafe"},
            "outlet": {"name": name, "timezone": timezone},
        },
    )
    assert res.status_code == 201, res.text
    tenant, outlet = res.json()["tenant_id"], res.json()["outlet_id"]
    owner = _bearer(owner_id, tenant, "owner")
    for path, method, body in (
        (
            f"/api/v1/owner/outlets/{outlet}",
            "patch",
            {"pb1_enabled": True, "pb1_rate_bps": 1000, "delivery_fee": 10000},
        ),
        (f"/api/v1/owner/outlets/{outlet}/tables", "post", {"name": "M01", "capacity": capacity}),
        (f"/api/v1/owner/outlets/{outlet}/reservation-settings", "put", RESERVATIONS),
    ):
        res = getattr(client, method)(path, headers=owner, json=body)
        assert res.status_code < 300, res.text
    slug = f"eval-{key.replace('_', '-')}-{uuid4().hex[:6]}"
    admin_sql("update app.outlets set public_slug = %s where id = %s", (slug, outlet))
    return {"tenant": tenant, "outlet": outlet, "slug": slug, "timezone": timezone}


def _counter(outlet: str) -> Any:
    def count() -> tuple[int, int]:
        rows = admin_sql(
            "select (select count(*) from app.orders where outlet_id = %s),"
            " (select count(*) from app.reservations where outlet_id = %s)",
            (outlet, outlet),
        )
        return int(rows[0][0]), int(rows[0][1])

    return count


def _menu(client: TestClient, base: str) -> dict[str, dict[str, Any]]:
    res = client.get(f"{base}/menu")
    assert res.status_code == 200, res.text
    return {m["name"]: m for m in res.json()}


def build(client: TestClient) -> dict[str, World]:
    cleanup()
    wib = _outlet(client, "o", "Senja Eval", "Asia/Jakarta", 4)
    wita = _outlet(client, "o_wita", "Losari Eval", "Asia/Makassar", 2)

    # Croissant Butter sold out: its only ingredient goes to zero at outlet `o`.
    admin_sql(
        "insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity,"
        " note, actor_type) select %s, %s, s.id, 'adjustment', -20, 'eval: sold out', 'system'"
        " from app.stock_items s where s.tenant_id = %s and s.name = 'Croissant (frozen)'",
        (wib["tenant"], wib["outlet"], wib["tenant"]),
    )
    # The day after tomorrow at 19:00 is taken (the only table seats 4).
    zone = ZoneInfo(wib["timezone"])
    day = datetime.now(zone).date() + timedelta(days=2)
    start = datetime(day.year, day.month, day.day, 19, 0, tzinfo=zone)
    res = client.post(
        f"/api/v1/public/o/{wib['slug']}/reservations",
        headers={
            "X-Chat-Session": "s-" + "e" * 30,
            "Idempotency-Key": uuid4().hex,
            "X-Booking-Key": "k-" + uuid4().hex + uuid4().hex,
        },
        json={
            "party_size": 4,
            "start_at": start.isoformat(),
            "customer": {"name": "Tamu Lain", "phone": "081200000001"},
            "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        },
    )
    assert res.status_code == 201, res.text

    token = plain(
        admin_sql("select qr_token from app.tables where outlet_id = %s", (wib["outlet"],))[0][0],
        "tables.qr_token",
    )
    worlds = {}
    for key, outlet, base in (
        ("o", wib, f"/api/v1/public/o/{wib['slug']}"),
        ("o_wita", wita, f"/api/v1/public/o/{wita['slug']}"),
        ("t", wib, f"/api/v1/public/t/{token}"),
    ):
        worlds[key] = World(
            client=client,
            base=base,
            menu=_menu(client, base),
            timezone=outlet["timezone"],
            count_writes=_counter(outlet["outlet"]),
        )
    return worlds
