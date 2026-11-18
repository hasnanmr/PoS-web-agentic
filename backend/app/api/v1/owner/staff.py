"""Owner staff management — wireframe O4 "Staf & Akses" (T-012, T-013).

Invite-only accounts: Supabase Auth sends the invitation email (service role key,
auth admin API only), then the staff row is written under RLS. Deactivation takes
effect on the next request (live check) and bans the auth user so refresh tokens
stop working too. The access matrix on O4 is static UI (no endpoint).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from app import db
from app.api.errors import ApiError
from app.auth.deps import OwnerOnly
from app.auth.supabase_admin import AuthAdmin, SupabaseAdminError
from app.core import staff as core

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/owner", tags=["owner: staff"])


class StaffOutlet(BaseModel):
    id: UUID
    name: str


class StaffMember(BaseModel):
    id: UUID
    display_name: str
    email: str
    outlets: list[StaffOutlet]
    status: Literal["active", "inactive", "invited"]


class InviteRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    outlet_ids: list[UUID] = Field(min_length=1)


class OutletIds(BaseModel):
    outlet_ids: list[UUID] = Field(min_length=1)


def _auth_admin(request: Request) -> AuthAdmin:
    admin: AuthAdmin | None = getattr(request.app.state, "auth_admin", None)
    if admin is None:
        raise ApiError(
            503, "auth_admin_not_configured", "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set"
        )
    return admin


def _redirect(request: Request) -> str | None:
    url = request.app.state.settings.admin_app_url
    return str(url) if url else None


async def _staff_list(request: Request, owner: OwnerOnly) -> list[StaffMember]:
    async with db.transaction(request.app.state.db_pool, owner.actor()) as conn:
        rows = await core.list_staff(conn)
    return [StaffMember(**r) for r in rows]


@router.get("/staff")
async def list_staff(request: Request, owner: OwnerOnly) -> list[StaffMember]:
    return await _staff_list(request, owner)


@router.post("/staff/invitations", status_code=status.HTTP_201_CREATED)
async def invite_staff(body: InviteRequest, request: Request, owner: OwnerOnly) -> StaffMember:
    admin = _auth_admin(request)
    email = body.email.strip().lower()
    async with db.transaction(request.app.state.db_pool, owner.actor()) as conn:
        await core.validate_invitation(conn, email=email, outlet_ids=body.outlet_ids)

    try:
        invited = await asyncio.to_thread(
            admin.invite_user,
            email,
            data={"display_name": body.display_name},
            redirect_to=_redirect(request),
        )
    except SupabaseAdminError as exc:
        logger.warning("staff invite failed", extra={"status": exc.status})
        if exc.status == 422:
            raise ApiError(409, "email_taken", "this email already has an account") from None
        raise ApiError(502, "invite_failed", "invitation email could not be sent") from None

    ctx = owner.actor()
    async with db.transaction(request.app.state.db_pool, ctx) as conn:
        await core.create_invited_staff(
            conn,
            ctx,
            user_id=invited.user_id,
            display_name=body.display_name,
            email=email,
            outlet_ids=body.outlet_ids,
        )
        row = next(r for r in await core.list_staff(conn) if r["id"] == invited.user_id)
    return StaffMember(**row)


@router.put("/staff/{user_id}/outlets")
async def set_staff_outlets(
    user_id: UUID, body: OutletIds, request: Request, owner: OwnerOnly
) -> StaffMember:
    ctx = owner.actor()
    async with db.transaction(request.app.state.db_pool, ctx) as conn:
        await core.set_outlets(conn, ctx, user_id, body.outlet_ids)
        row = next(r for r in await core.list_staff(conn) if r["id"] == user_id)
    return StaffMember(**row)


@router.post("/staff/{user_id}/invitations/resend", status_code=status.HTTP_204_NO_CONTENT)
async def resend_invitation(user_id: UUID, request: Request, owner: OwnerOnly) -> Response:
    admin = _auth_admin(request)
    ctx = owner.actor()
    async with db.transaction(request.app.state.db_pool, ctx) as conn:
        email = await core.mark_resent(conn, ctx, user_id)
        try:
            await asyncio.to_thread(admin.invite_user, email, redirect_to=_redirect(request))
        except SupabaseAdminError as exc:
            logger.warning("staff invite resend failed", extra={"status": exc.status})
            raise ApiError(502, "invite_failed", "invitation email could not be sent") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/staff/{user_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_staff(user_id: UUID, request: Request, owner: OwnerOnly) -> Response:
    ctx = owner.actor()
    async with db.transaction(request.app.state.db_pool, ctx) as conn:
        changed = await core.deactivate(conn, ctx, user_id)
    admin: AuthAdmin | None = getattr(request.app.state, "auth_admin", None)
    if changed and admin is not None:
        # The DB change already blocks the API and new tokens; the ban also stops refresh.
        try:
            await asyncio.to_thread(admin.ban_user, user_id)
        except SupabaseAdminError as exc:
            logger.error("ban after deactivation failed", extra={"status": exc.status})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
