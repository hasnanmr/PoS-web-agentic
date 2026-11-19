"""Owner attendance settings — wireframe O3 "Cash drawer & absensi" → "Tablet absensi" (T-121).

Contract: docs/architecture/screen-endpoint-map.md → O3 "Tablet absensi". The grace period
("Tenggang lupa clock out") is `attendance_grace_minutes` on `PATCH /owner/outlets/{id}`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from app import db
from app.auth.deps import OwnerOnly
from app.core import attendance as core
from app.core import outlets

router = APIRouter(prefix="/api/v1/owner", tags=["owner: attendance"])


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


class DeviceOut(BaseModel):
    id: UUID
    name: str
    paired_at: datetime
    last_seen_at: datetime | None = Field(description='"aktif 2 menit lalu"')
    revoked_at: datetime | None


class PairingCodeOut(BaseModel):
    code: str = Field(description="6 digits, shown once, one-time")
    expires_at: datetime = Field(description="10 minutes after it was created")


@router.get("/outlets/{outlet_id}/attendance-devices")
async def list_devices(outlet_id: UUID, request: Request, owner: OwnerOnly) -> list[DeviceOut]:
    """Paired tablets of the outlet, active ones first (revoked ones keep `revoked_at`)."""
    async with db.transaction(_pool(request), owner.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        rows = await core.list_devices(conn, outlet_id)
    return [DeviceOut(**r) for r in rows]


@router.post("/outlets/{outlet_id}/attendance-pairing-codes", status_code=status.HTTP_201_CREATED)
async def create_pairing_code(
    outlet_id: UUID, request: Request, owner: OwnerOnly
) -> PairingCodeOut:
    """O3 "+ Pairing tablet baru → kode 6 digit"; the tablet enters it on K0."""
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        row = await core.create_pairing_code(conn, ctx, outlet_id)
    return PairingCodeOut(**row)


@router.post("/attendance-devices/{device_id}/revoke")
async def revoke_device(device_id: UUID, request: Request, owner: OwnerOnly) -> DeviceOut:
    """O3 "Cabut": the tablet is refused on its next request and goes back to K0."""
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        row = await core.revoke_device(conn, ctx, device_id)
    return DeviceOut(**row)
