"""Staff accounts and outlet assignments (T-012) — screen O4.

Accounts are invite-only: the owner enters name, email, and outlets; Supabase Auth
sends the invitation email and the staff member sets their own password. The
Supabase call happens in the API layer (it is not a DB operation); these functions
write the matching `app.users` / `app.staff_outlets` rows inside the caller's
transaction, so RLS keeps everything inside the owner's tenant.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row

from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError

StaffStatus = Literal["active", "inactive", "invited"]


def staff_status(is_active: bool, invitation_accepted_at: object) -> StaffStatus:
    if not is_active:
        return "inactive"
    return "active" if invitation_accepted_at is not None else "invited"


async def list_staff(conn: AsyncConnection) -> list[dict[str, Any]]:
    """Staff of the tenant (owners are not listed on O4), with their outlets."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        """
        select u.id, u.display_name, u.email, u.is_active, u.invitation_accepted_at,
               coalesce(json_agg(json_build_object('id', o.id, 'name', o.name)
                                 order by o.name) filter (where o.id is not null), '[]') as outlets
        from app.users u
        left join app.staff_outlets so on so.user_id = u.id
        left join app.outlets o on o.id = so.outlet_id
        where u.role = 'staff'
        group by u.id
        order by u.is_active desc, u.display_name
        """
    )
    rows = await cur.fetchall()
    for r in rows:
        r["status"] = staff_status(r.pop("is_active"), r.pop("invitation_accepted_at"))
    return rows


async def get_staff(conn: AsyncConnection, user_id: UUID) -> dict[str, Any]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "select id, display_name, email, is_active, invitation_accepted_at from app.users"
        " where id = %s and role = 'staff'",
        (user_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("staff")
    return row


async def email_in_use(conn: AsyncConnection, email: str) -> bool:
    """True when any account (any tenant) uses this email. Emails are globally unique."""
    cur = await conn.execute("select app.email_registered(%s)", (email,))
    row = await cur.fetchone()
    return bool(row and row[0])


async def _check_outlets(conn: AsyncConnection, outlet_ids: list[UUID]) -> None:
    if not outlet_ids:
        raise ValidationFailedError("assign at least one outlet", {"field": "outlet_ids"})
    cur = await conn.execute(
        "select count(*) from app.outlets where id = any(%s) and is_active", (list(outlet_ids),)
    )
    row = await cur.fetchone()
    if row is None or row[0] != len(set(outlet_ids)):
        raise ValidationFailedError("unknown outlet", {"field": "outlet_ids"})


async def validate_invitation(conn: AsyncConnection, *, email: str, outlet_ids: list[UUID]) -> None:
    """Checks done before calling Supabase, so a bad request sends no email."""
    await _check_outlets(conn, outlet_ids)
    if await email_in_use(conn, email):
        raise ConflictError("email_taken", "this email already has an account")


async def create_invited_staff(
    conn: AsyncConnection,
    ctx: ActorContext,
    *,
    user_id: UUID,
    display_name: str,
    email: str,
    outlet_ids: list[UUID],
) -> None:
    """Write the staff row after Supabase created the auth user (`user_id`)."""
    await _check_outlets(conn, outlet_ids)
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into app.users (id, tenant_id, email, display_name, role, invited_at)"
                " values (%s, %s, %s, %s, 'staff', now())",
                (user_id, ctx.tenant_id, email, display_name.strip()),
            )
    except errors.UniqueViolation:
        raise ConflictError("email_taken", "this email already has an account") from None
    await _write_assignments(conn, ctx, user_id, outlet_ids)
    await record_audit(
        conn,
        ctx,
        action="staff.invited",
        entity_type="user",
        entity_id=user_id,
        data={"email": email, "outlet_ids": [str(o) for o in outlet_ids]},
    )


async def _write_assignments(
    conn: AsyncConnection, ctx: ActorContext, user_id: UUID, outlet_ids: list[UUID]
) -> None:
    await conn.execute("delete from app.staff_outlets where user_id = %s", (user_id,))
    for outlet_id in dict.fromkeys(outlet_ids):
        await conn.execute(
            "insert into app.staff_outlets (user_id, outlet_id, tenant_id) values (%s, %s, %s)",
            (user_id, outlet_id, ctx.tenant_id),
        )


async def set_outlets(
    conn: AsyncConnection, ctx: ActorContext, user_id: UUID, outlet_ids: list[UUID]
) -> None:
    await get_staff(conn, user_id)
    await _check_outlets(conn, outlet_ids)
    await _write_assignments(conn, ctx, user_id, outlet_ids)
    await record_audit(
        conn,
        ctx,
        action="staff.outlets_set",
        entity_type="user",
        entity_id=user_id,
        data={"outlet_ids": [str(o) for o in outlet_ids]},
    )


async def mark_resent(conn: AsyncConnection, ctx: ActorContext, user_id: UUID) -> str:
    """Validate a resend and record it. Returns the email to re-invite."""
    staff = await get_staff(conn, user_id)
    if not staff["is_active"]:
        raise ConflictError("account_inactive", "this account is deactivated")
    if staff["invitation_accepted_at"] is not None:
        raise ConflictError("invitation_accepted", "this staff member already signed in")
    await conn.execute("update app.users set invited_at = now() where id = %s", (user_id,))
    await record_audit(
        conn, ctx, action="staff.invitation_resent", entity_type="user", entity_id=user_id
    )
    return str(staff["email"])


async def deactivate(conn: AsyncConnection, ctx: ActorContext, user_id: UUID) -> bool:
    """Deactivate a staff account. Returns False when it was already inactive.

    The API refuses the account from the next request on (live check in
    `PgUserDirectory`), and the token hook refuses new tokens; the caller also bans
    the auth user so refresh tokens stop working (US-003).
    """
    staff = await get_staff(conn, user_id)
    if not staff["is_active"]:
        return False
    await conn.execute(
        "update app.users set is_active = false, deactivated_at = now() where id = %s",
        (user_id,),
    )
    await record_audit(conn, ctx, action="staff.deactivated", entity_type="user", entity_id=user_id)
    return True
