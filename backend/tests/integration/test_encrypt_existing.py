"""`app.tools.encrypt_existing`: plaintext written before field encryption is re-written
encrypted, stays readable through the API, and printed table QR codes keep working."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tools import encrypt_existing

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner, plain

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "encrypt.test"
OWNER = UUID("73000000-0000-0000-0000-0000000000a0")


def _bearer(sub: UUID, tenant: str | None, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=str(sub), tenant_id=tenant, app_role=role)}"}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    cleanup_domain(DOMAIN)
    invite_owner(OWNER, f"owner@{DOMAIN}")
    with TestClient(
        create_app(
            Settings(database_url=APP_URL, admin_app_url="https://admin.test"),
            token_verifier=make_verifier(),
        )
    ) as c:
        yield c
    cleanup_domain(DOMAIN)


@pytest.fixture(scope="module")
def ctx(client: TestClient) -> dict[str, Any]:
    res = client.post(
        "/api/v1/owner/onboarding",
        headers=_bearer(OWNER, None, "owner_pending"),
        json={"business": {"name": "Kopi Lama", "type": "cafe"}, "outlet": {"name": "Lama"}},
    )
    assert res.status_code == 201, res.text
    tenant, outlet = res.json()["tenant_id"], res.json()["outlet_id"]
    return {"tenant": tenant, "outlet": outlet, "owner": _bearer(OWNER, tenant, "owner")}


def test_legacy_rows_are_encrypted_and_stay_readable(client, ctx) -> None:
    # Rows as written before field encryption: plaintext, the table token from the default.
    table_id, token = admin_sql(
        "insert into app.tables (tenant_id, outlet_id, name, capacity)"
        " values (%s, %s, 'L01', 4) returning id, qr_token",
        (ctx["tenant"], ctx["outlet"]),
    )[0]
    assert (
        not token.startswith("enc:") and client.get(f"/api/v1/public/t/{token}").status_code == 200
    )
    res_id = admin_sql(
        "insert into app.reservations (tenant_id, outlet_id, table_id, guest_name, guest_phone,"
        " party_size, starts_at, ends_at, source, created_by_actor, created_by_id)"
        " values (%s, %s, %s, 'Lina', '081311112222', 2, now() + interval '1 day',"
        " now() + interval '1 day 90 minutes', 'phone', 'user', %s) returning id",
        (ctx["tenant"], ctx["outlet"], table_id, OWNER),
    )[0][0]

    before = encrypt_existing.run(ADMIN_URL, dry_run=True)
    assert before["tables.qr_token"] >= 1 and before["reservations.guest_phone"] >= 1
    encrypt_existing.run(ADMIN_URL)
    after = encrypt_existing.run(ADMIN_URL, dry_run=True)
    assert all(n == 0 for n in after.values())  # a second run has nothing left to do

    stored_token = admin_sql("select qr_token from app.tables where id = %s", (table_id,))[0][0]
    assert stored_token.startswith("enc:v1:") and plain(stored_token, "tables.qr_token") == token
    # The printed QR keeps working (looked up by the SHA-256 of the same token).
    assert client.get(f"/api/v1/public/t/{token}").status_code == 200
    png = client.get(f"/api/v1/owner/tables/{table_id}/qr.png", headers=ctx["owner"])
    assert png.status_code == 200
    row = admin_sql(
        "select guest_name, guest_phone, guest_phone_index from app.reservations where id = %s",
        (res_id,),
    )[0]
    assert row[0].startswith("enc:v1:") and row[1].startswith("enc:v1:") and row[2]
    detail = client.get(f"/api/v1/ops/reservations/{res_id}", headers=ctx["owner"]).json()
    assert detail["guest_name"] == "Lina" and detail["phone_masked"].endswith("222")
