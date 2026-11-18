"""Who is calling, resolved from a verified token plus the LIVE database row (T-006).

The token's `tenant_id`/`app_role` claims only identify the caller. Role, active
status, and tenant come from `app.users` on every request, so a deactivated staff
member or a changed role takes effect immediately (Appendix B.7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from psycopg_pool import AsyncConnectionPool

from app import db
from app.auth.tokens import VerifiedToken
from app.core.actor import ActorContext

Role = Literal["owner", "staff", "owner_pending"]


class AuthError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    role: Role
    tenant_id: UUID | None
    email: str | None
    display_name: str | None

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def onboarding_required(self) -> bool:
        return self.role == "owner_pending"

    def actor(self, correlation_id: str | None = None) -> ActorContext:
        if self.tenant_id is None:
            raise AuthError(403, "onboarding_required", "create the business first")
        return ActorContext.for_user(self.tenant_id, self.user_id, correlation_id=correlation_id)


class UserDirectory(Protocol):
    async def resolve(self, token: VerifiedToken) -> Principal: ...


_USER_SQL = """
select id, tenant_id, email, display_name, role::text, is_active,
       invitation_accepted_at is null as first_sign_in
from app.users where id = %s
"""


class PgUserDirectory:
    """Resolves principals with RLS active (role app_backend, tenant from the token)."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def resolve(self, token: VerifiedToken) -> Principal:
        if token.app_role == "owner_pending":
            return await self._pending_owner(token)
        assert token.tenant_id is not None  # noqa: S101 - guaranteed by tokens._claims_to_token
        ctx = ActorContext.for_user(token.tenant_id, token.user_id)
        async with db.transaction(self._pool, ctx) as conn:
            cur = await conn.execute(_USER_SQL, (token.user_id,))
            row = await cur.fetchone()
            if row is not None and row[5] and row[6]:
                # First request after accepting the invitation: O4 shows "Aktif" from now on.
                await conn.execute(
                    "update app.users set invitation_accepted_at = now() where id = %s",
                    (token.user_id,),
                )
        if row is None:
            # Not in this tenant (RLS) or deleted: never trust the claim alone.
            raise AuthError(401, "account_unknown", "account not found for this tenant")
        user_id, tenant_id, email, display_name, role, is_active, _ = row
        if not is_active:
            raise AuthError(403, "account_inactive", "account is deactivated")
        return Principal(user_id, role, tenant_id, email, display_name)

    async def _pending_owner(self, token: VerifiedToken) -> Principal:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "select invitation_id, email from app.pending_owner_invitation(%s)",
                (token.user_id,),
            )
            row = await cur.fetchone()
        if row is None:
            raise AuthError(403, "account_not_invited", "no open owner invitation")
        return Principal(token.user_id, "owner_pending", None, row[1], None)
