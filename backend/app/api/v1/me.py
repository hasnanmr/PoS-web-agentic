"""GET /api/v1/me — current user, role, tenant, and accessible outlets.

Wireframe: sidebar (Sidebar/Owner, Sidebar/Staff) and the outlet switcher
("Outlet: Kopi Senja - Bandung") on every admin screen; O1 onboarding for an
invited owner (`onboarding_required: true`). Contract:
docs/architecture/screen-endpoint-map.md → Shared.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import db
from app.auth.deps import CurrentPrincipal

router = APIRouter(prefix="/api/v1", tags=["session"])


class MeUser(BaseModel):
    id: UUID
    email: str | None
    display_name: str | None


class MeTenant(BaseModel):
    id: UUID
    name: str
    type: Literal["restaurant", "cafe"]


class MeOutlet(BaseModel):
    id: UUID
    name: str
    timezone: str
    order_prefix: str
    payment_mode: Literal["pay_first", "open_bill"]


class MeResponse(BaseModel):
    user: MeUser
    role: Literal["owner", "staff", "owner_pending"]
    onboarding_required: bool
    tenant: MeTenant | None
    outlets: list[MeOutlet]


_TENANT_SQL = "select id, name, type::text from app.tenants"
_OUTLETS_SQL = """
select id, name, timezone, order_prefix, payment_mode::text
from app.outlets where is_active order by name
"""


@router.get("/me", response_model=MeResponse)
async def me(request: Request, principal: CurrentPrincipal) -> MeResponse:
    user = MeUser(id=principal.user_id, email=principal.email, display_name=principal.display_name)
    if principal.onboarding_required:
        return MeResponse(
            user=user, role="owner_pending", onboarding_required=True, tenant=None, outlets=[]
        )

    # RLS returns only the caller's tenant and the outlets they may access.
    async with db.transaction(request.app.state.db_pool, principal.actor()) as conn:
        trow = await (await conn.execute(_TENANT_SQL)).fetchone()
        orows = await (await conn.execute(_OUTLETS_SQL)).fetchall()
    tenant = MeTenant(id=trow[0], name=trow[1], type=trow[2]) if trow else None
    outlets = [
        MeOutlet(id=r[0], name=r[1], timezone=r[2], order_prefix=r[3], payment_mode=r[4])
        for r in orows
    ]
    return MeResponse(
        user=user, role=principal.role, onboarding_required=False, tenant=tenant, outlets=outlets
    )
