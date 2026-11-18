"""Integration tests against a migrated Postgres (T-113 session pattern, T-006 /me).

Skipped unless both are set (CI sets them; see .github/workflows/ci.yml):
  TEST_DATABASE_URL      superuser/owner URL, used only to insert fixtures
  TEST_APP_DATABASE_URL  same database as role app_backend (RLS applies)
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.principal import AuthError, PgUserDirectory
from app.auth.tokens import VerifiedToken
from app.config import Settings
from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.main import create_app

from ..auth.keys import make_token, make_verifier

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")
APP_URL = os.environ.get("TEST_APP_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

TA = UUID("10000000-0000-0000-0000-00000000000a")
TB = UUID("10000000-0000-0000-0000-00000000000b")
A1 = UUID("10000000-0000-0000-0000-0000000000a1")
A2 = UUID("10000000-0000-0000-0000-0000000000a2")
B1 = UUID("10000000-0000-0000-0000-0000000000b1")
OWNER = UUID("10000000-0000-0000-0000-0000000000f0")
STAFF = UUID("10000000-0000-0000-0000-0000000000f1")
INACTIVE = UUID("10000000-0000-0000-0000-0000000000f2")
PENDING = UUID("10000000-0000-0000-0000-0000000000e0")

FIXTURES = f"""
insert into auth.users (id, email) values
  ('{OWNER}', 'olga@a.test'), ('{STAFF}', 'rina@a.test'), ('{INACTIVE}', 'dodi@a.test'),
  ('{PENDING}', 'new@c.test');
insert into app.tenants (id, name, type) values
  ('{TA}', 'Kopi Senja', 'cafe'), ('{TB}', 'Lain', 'cafe');
insert into app.outlets (id, tenant_id, name, order_prefix) values
  ('{A1}', '{TA}', 'Bandung - Dago', 'A'), ('{A2}', '{TA}', 'Jakarta - Kemang', 'K'),
  ('{B1}', '{TB}', 'Lain', 'A');
insert into app.users (id, tenant_id, email, display_name, role, is_active) values
  ('{OWNER}', '{TA}', 'olga@a.test', 'Olga', 'owner', true),
  ('{STAFF}', '{TA}', 'rina@a.test', 'Rina', 'staff', true),
  ('{INACTIVE}', '{TA}', 'dodi@a.test', 'Dodi', 'staff', false);
insert into app.staff_outlets (user_id, outlet_id, tenant_id) values ('{STAFF}', '{A1}', '{TA}');
select app.record_owner_invitation('new@c.test', '{PENDING}', 'platform@test', null);
"""

CLEANUP = f"""
delete from app.staff_outlets where tenant_id in ('{TA}', '{TB}');
delete from app.audit_events where tenant_id in ('{TA}', '{TB}') or entity_id in
  (select id::text from app.owner_invitations where auth_user_id = '{PENDING}');
delete from app.owner_invitations where auth_user_id = '{PENDING}';
delete from app.users where tenant_id in ('{TA}', '{TB}');
delete from app.cash_drawers where tenant_id in ('{TA}', '{TB}');
delete from app.reservation_settings where tenant_id in ('{TA}', '{TB}');
delete from app.outlets where tenant_id in ('{TA}', '{TB}');
delete from app.tenants where id in ('{TA}', '{TB}');
delete from auth.users where id in ('{OWNER}', '{STAFF}', '{INACTIVE}', '{PENDING}');
"""


@pytest.fixture(scope="module", autouse=True)
def fixtures() -> Iterator[None]:
    assert ADMIN_URL
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute("set session_replication_role = replica")  # skip append-only triggers
        conn.execute(CLEANUP)
        conn.execute("set session_replication_role = origin")
        conn.execute(FIXTURES)
    yield
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute("set session_replication_role = replica")
        conn.execute(CLEANUP)


@pytest.fixture
async def pool() -> AsyncIterator[db.AsyncConnectionPool]:
    assert APP_URL
    p = db.create_pool(APP_URL, min_size=1, max_size=1)  # one connection: proves no leaks
    await p.open()
    yield p
    await p.close()


def _token(user: UUID, tenant: UUID | None, role: str) -> VerifiedToken:
    return VerifiedToken(user, role, tenant, None, 0, {})  # type: ignore[arg-type]


async def test_alternating_tenants_on_one_connection_do_not_leak(pool) -> None:
    for _ in range(3):
        async with db.transaction(pool, ActorContext.for_user(TA, OWNER)) as conn:
            names = [
                r[0] for r in await (await conn.execute("select name from app.tenants")).fetchall()
            ]
            assert names == ["Kopi Senja"]
        async with db.transaction(pool, ActorContext.for_system(TB)) as conn:
            names = [
                r[0] for r in await (await conn.execute("select name from app.tenants")).fetchall()
            ]
            assert names == ["Lain"]
        async with pool.connection() as conn:
            cur = await conn.execute("select count(*) from app.outlets")
            assert (await cur.fetchone())[0] == 0  # no context → no rows


async def test_directory_uses_live_row(pool) -> None:
    directory = PgUserDirectory(pool)
    staff = await directory.resolve(_token(STAFF, TA, "staff"))
    assert staff.role == "staff" and staff.display_name == "Rina"

    # Claim says owner, database says staff: the database wins.
    escalated = await directory.resolve(_token(STAFF, TA, "owner"))
    assert escalated.role == "staff"

    with pytest.raises(AuthError) as inactive:
        await directory.resolve(_token(INACTIVE, TA, "staff"))
    assert inactive.value.code == "account_inactive"

    with pytest.raises(AuthError) as wrong_tenant:
        await directory.resolve(_token(STAFF, TB, "staff"))
    assert wrong_tenant.value.code == "account_unknown"

    pending = await directory.resolve(_token(PENDING, None, "owner_pending"))
    assert pending.onboarding_required and pending.email == "new@c.test"


async def test_audit_writer_records_actor(pool) -> None:
    ctx = ActorContext.for_user(TA, OWNER).with_reason("tes audit")
    async with db.transaction(pool, ctx) as conn:
        await record_audit(
            conn, ctx, action="outlet.updated", entity_type="outlet", entity_id=A1, outlet_id=A1
        )
        cur = await conn.execute(
            "select actor_type::text, actor_id, reason, data->>'correlation_id' "
            "from app.audit_events where data->>'correlation_id' = %s",
            (ctx.correlation_id,),
        )
        row = await cur.fetchone()
    assert row == ("user", OWNER, "tes audit", ctx.correlation_id)


def test_me_endpoint_returns_role_scoped_outlets() -> None:
    settings = Settings(database_url=APP_URL)
    staff_token = make_token(sub=str(STAFF), tenant_id=str(TA))
    owner_token = make_token(sub=str(OWNER), tenant_id=str(TA), app_role="owner")
    with TestClient(create_app(settings, token_verifier=make_verifier())) as client:
        staff = client.get("/api/v1/me", headers={"Authorization": f"Bearer {staff_token}"}).json()
        owner = client.get("/api/v1/me", headers={"Authorization": f"Bearer {owner_token}"}).json()
    assert staff["role"] == "staff"
    assert [o["name"] for o in staff["outlets"]] == ["Bandung - Dago"]
    assert owner["role"] == "owner"
    assert [o["name"] for o in owner["outlets"]] == ["Bandung - Dago", "Jakarta - Kemang"]
    assert owner["tenant"]["name"] == "Kopi Senja"
