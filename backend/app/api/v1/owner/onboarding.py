"""POST /api/v1/owner/onboarding — wireframe O1 "Buat profil bisnis" (T-010, T-011).

Only an invited owner without a business (`owner_pending`) may call it. Creates the
tenant, the owner account, and the first outlet in one transaction. After this the
client refreshes the Supabase session so the token carries `tenant_id`.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from app.api.errors import ApiError
from app.auth.deps import PendingOwner

router = APIRouter(prefix="/api/v1/owner", tags=["owner: onboarding"])

Timezone = Literal["Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura"]


class OnboardingBusiness(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # Dropshipper is shown disabled on O1 ("Segera, Phase 3"), so it is not accepted.
    type: Literal["cafe", "restaurant"]


class OnboardingOutlet(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    timezone: Timezone = "Asia/Jakarta"
    address: str | None = Field(default=None, max_length=300)
    whatsapp_phone: str | None = Field(default=None, pattern=r"^\+?[0-9]{8,15}$")


class OnboardingRequest(BaseModel):
    business: OnboardingBusiness
    outlet: OnboardingOutlet


class OnboardingResponse(BaseModel):
    tenant_id: UUID
    outlet_id: UUID


@router.post("/onboarding", status_code=status.HTTP_201_CREATED)
async def create_business(
    body: OnboardingRequest, request: Request, principal: PendingOwner
) -> OnboardingResponse:
    pool = request.app.state.db_pool
    if pool is None:
        raise ApiError(503, "database_not_configured", "database is not configured")
    try:
        async with pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "select tenant_id, outlet_id from app.complete_owner_onboarding"
                "(%s, %s, %s, %s, %s, %s, %s)",
                (
                    principal.user_id,
                    body.business.name,
                    body.business.type,
                    body.outlet.name,
                    body.outlet.timezone,
                    body.outlet.address,
                    body.outlet.whatsapp_phone,
                ),
            )
            row = await cur.fetchone()
    except psycopg.errors.NoDataFound:
        raise ApiError(403, "account_not_invited", "no open owner invitation") from None
    except psycopg.errors.UniqueViolation as exc:
        constraint = getattr(exc.diag, "constraint_name", "") or ""
        if "whatsapp_phone" in constraint:
            raise ApiError(
                409, "whatsapp_phone_taken", "WhatsApp number is used by another outlet"
            ) from None
        raise ApiError(409, "conflict", "business could not be created") from None
    assert row is not None  # noqa: S101
    return OnboardingResponse(tenant_id=row[0], outlet_id=row[1])
