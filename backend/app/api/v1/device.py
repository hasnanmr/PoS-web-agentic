"""Outlet attendance tablet — wireframes K0-K4 (T-116, T-117, T-121, T-122).

Contract: docs/architecture/screen-endpoint-map.md → "Attendance tablet (K0-K4)". The tablet
authenticates with the device token from `POST /device/pair` (`Authorization: Bearer dev_…`),
never with a Supabase token, and these are the only endpoints it can use. Errors the tablet
handles: `pairing_code_invalid` (K0), `device_revoked` / `device_unpaired` (→ back to K0),
`selfie_required`, `not_assigned`, `open_elsewhere` (K4).
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app import db
from app.api.errors import ApiError
from app.core import attendance as core
from app.core.actor import ActorContext
from app.core.errors import DomainError, ValidationFailedError

router = APIRouter(prefix="/api/v1/device", tags=["attendance tablet (K0-K4)"])

_WWW = {"WWW-Authenticate": "Bearer"}


def _pool(request: Request) -> Any:
    pool = request.app.state.db_pool
    if pool is None:
        raise ApiError(503, "database_not_configured", "database is not configured")
    return pool


async def current_device(request: Request) -> core.Device:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token.startswith(core.TOKEN_PREFIX):
        raise ApiError(401, "device_unpaired", "pair this tablet first", headers=_WWW)
    async with _pool(request).connection() as conn, conn.transaction():
        device = await core.resolve_device(conn, token)
    if device is None:
        raise ApiError(401, "device_unpaired", "pair this tablet first", headers=_WWW)
    if device.revoked:
        raise ApiError(401, "device_revoked", "this tablet was revoked by the owner", headers=_WWW)
    return device


CurrentDevice = Annotated[core.Device, Depends(current_device)]


# K0 · pairing -------------------------------------------------------------------------------

# Wrong codes: at most 10 per client address and 100 in total per 10 minutes (per API process),
# so a 6-digit code that lives 10 minutes cannot be guessed.
_FAILED_WINDOW_SECONDS = 600
_FAILED_LIMITS = {"client": 10, "all": 100}
_failed: dict[str, deque[float]] = {}


def _client_key(request: Request) -> str:
    # The platform proxy appends the real peer address last; earlier entries are client-supplied.
    forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
    peer = forwarded[-1] if forwarded[-1] else (request.client.host if request.client else "?")
    return f"client:{peer}"


def _hits(key: str, now: float) -> deque[float]:
    hits = _failed.setdefault(key, deque())
    while hits and hits[0] < now - _FAILED_WINDOW_SECONDS:
        hits.popleft()
    return hits


def _check_rate(client: str) -> None:
    now = time.monotonic()
    if len(_hits(client, now)) >= _FAILED_LIMITS["client"] or (
        len(_hits("all", now)) >= _FAILED_LIMITS["all"]
    ):
        raise ApiError(429, "too_many_attempts", "too many wrong codes; wait a few minutes")


def _note_failure(client: str) -> None:
    now = time.monotonic()
    _hits(client, now).append(now)
    _hits("all", now).append(now)


class PairIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$", description="6-digit one-time code from O3")


class OutletInfo(BaseModel):
    name: str
    timezone: str


class PairOut(BaseModel):
    device_token: str = Field(description="Keep on the tablet; send as `Authorization: Bearer`")
    device_name: str
    outlet: OutletInfo


@router.post("/pair", status_code=status.HTTP_201_CREATED)
async def pair(body: PairIn, request: Request) -> PairOut:
    """K0 "Hubungkan tablet". `pairing_code_invalid` (400) for a wrong, used, or expired code."""
    client = _client_key(request)
    _check_rate(client)
    try:
        async with _pool(request).connection() as conn, conn.transaction():
            token, device = await core.pair_device(conn, body.code)
    except DomainError:
        _note_failure(client)
        raise
    return PairOut(
        device_token=token,
        device_name=device.device_name,
        outlet=OutletInfo(name=device.outlet_name, timezone=device.timezone),
    )


# K1 · staff list ----------------------------------------------------------------------------


class StaffOut(BaseModel):
    user_id: UUID
    display_name: str
    status: Literal["not_clocked_in", "working"]
    since: datetime | None = Field(description='"Bekerja sejak 07:30" (open record here)')
    first_time: bool = Field(description="Never clocked in before: K3 shows the privacy notice")


class StaffList(BaseModel):
    outlet: OutletInfo
    device_name: str
    server_time: datetime
    staff: list[StaffOut]


@router.get("/staff")
async def staff(request: Request, device: CurrentDevice) -> StaffList:
    """K1 "Tap nama kamu untuk clock in / clock out": only staff assigned to this outlet."""
    async with db.transaction(_pool(request), device.actor()) as conn:
        rows = await core.outlet_staff(conn)
        now = await core.server_time(conn)
    return StaffList(
        outlet=OutletInfo(name=device.outlet_name, timezone=device.timezone),
        device_name=device.device_name,
        server_time=now,
        staff=[StaffOut(**r) for r in rows],
    )


# K2/K3 · selfie -----------------------------------------------------------------------------


class SelfieOut(BaseModel):
    selfie_id: UUID


@router.post(
    "/selfies",
    status_code=status.HTTP_201_CREATED,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                "image/webp": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
async def upload_selfie(request: Request, device: CurrentDevice) -> SelfieOut:
    """K3 "Simpan": the raw JPEG/WebP photo as the body (max 2 MB). PoC: stored in the database."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > core.SELFIE_MAX_BYTES:
        raise ValidationFailedError("the photo is larger than 2 MB", {"field": "selfie"})
    data = await request.body()
    ctx = device.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        selfie_id = await core.save_selfie(
            conn, ctx, content_type=request.headers.get("content-type", ""), data=data
        )
    return SelfieOut(selfie_id=selfie_id)


# K3 → K4 · clock in / clock out ---------------------------------------------------------------


class AttendanceIn(BaseModel):
    user_id: UUID
    selfie_id: UUID


class AttendanceOut(BaseModel):
    action: Literal["clock_in", "clock_out"]
    record_id: UUID
    display_name: str
    at: datetime
    clock_in_at: datetime
    duration_minutes: int | None = Field(description='Clock out: "8 j 32 mnt"')
    first_time_notice: bool
    timezone: str


@router.post("/attendance", status_code=status.HTTP_201_CREATED)
async def record(body: AttendanceIn, request: Request, device: CurrentDevice) -> AttendanceOut:
    """K3 "Simpan clock in" / "Simpan clock out". The server decides which (working → out)."""
    ctx: ActorContext = device.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        row = await core.record_attendance(
            conn, ctx, user_id=body.user_id, selfie_id=body.selfie_id
        )
    return AttendanceOut(**row, timezone=device.timezone)
