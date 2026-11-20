"""Outlet attendance tablet — wireframes K0-K4 (T-116, T-117, T-121, T-122).

Contract: docs/architecture/screen-endpoint-map.md → "Attendance tablet (K0-K4)". The tablet
authenticates with the device token from `POST /device/pair` (`Authorization: Bearer dev_…`),
never with a Supabase token, and these are the only endpoints it can use. Errors the tablet
handles: `pairing_code_invalid` and `tablet_already_paired` (K0), `device_revoked` /
`device_unpaired` (→ back to K0), `selfie_required`, `not_assigned`, `open_elsewhere` (K4).
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
from app.core import attendance_reports
from app.core.actor import ActorContext
from app.core.errors import ConflictError, ValidationFailedError

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

# Pairing attempts: at most 10 unconfirmed or wrong codes per client address per 10 minutes (per
# API process). An attempt is counted BEFORE the database call, so a burst of concurrent
# requests cannot slip past the check, and released when the code was right. There is no
# global cap, so one client cannot block pairing for everyone else.
_ATTEMPT_WINDOW_SECONDS = 600
_ATTEMPT_LIMIT = 10
_attempts: dict[str, deque[float]] = {}


def _client_key(request: Request) -> str:
    # The platform proxy appends the address it saw as the LAST X-Forwarded-For entry; earlier
    # entries are supplied by the client and can be spoofed, so they are ignored.
    forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
    if forwarded[-1]:
        return forwarded[-1]
    return request.client.host if request.client else "?"


def _prune(now: float) -> None:
    for key in list(_attempts):
        hits = _attempts[key]
        while hits and hits[0] < now - _ATTEMPT_WINDOW_SECONDS:
            hits.popleft()
        if not hits:
            del _attempts[key]


def _reserve_attempt(client: str) -> float:
    now = time.monotonic()
    _prune(now)
    hits = _attempts.setdefault(client, deque())
    if len(hits) >= _ATTEMPT_LIMIT:
        raise ApiError(429, "too_many_attempts", "too many wrong codes; wait a few minutes")
    hits.append(now)
    return now


def _release_attempt(client: str, at: float) -> None:
    hits = _attempts.get(client)
    if hits is not None:
        try:
            hits.remove(at)
        except ValueError:
            pass
        if not hits:
            _attempts.pop(client, None)


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
    """K0 "Hubungkan tablet". `pairing_code_invalid` (400) for a wrong, used, or expired code;
    `tablet_already_paired` (409) while the outlet still has an active tablet (one per outlet)."""
    client = _client_key(request)
    attempt = _reserve_attempt(client)
    try:
        async with _pool(request).connection() as conn, conn.transaction():
            token, device = await core.pair_device(conn, body.code)
    except ConflictError:
        _release_attempt(client, attempt)  # the code was right; the outlet is just occupied
        raise
    _release_attempt(client, attempt)  # a right code does not count against the client
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
    staff: list[StaffOut]


@router.get("/staff")
async def staff(request: Request, device: CurrentDevice) -> StaffList:
    """K1 "Tap nama kamu untuk clock in / clock out": only staff assigned to this outlet."""
    await attendance_reports.run_due_checks(_pool(request), device.tenant_id)
    async with db.transaction(_pool(request), device.actor()) as conn:
        rows = await core.outlet_staff(conn)
    return StaffList(
        outlet=OutletInfo(name=device.outlet_name, timezone=device.timezone),
        device_name=device.device_name,
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
    # Read at most 2 MB, whatever the headers say (chunked bodies have no Content-Length).
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > core.SELFIE_MAX_BYTES:
            raise ValidationFailedError("the photo is larger than 2 MB", {"field": "selfie"})
        chunks.append(chunk)
    data = b"".join(chunks)
    ctx = device.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        selfie_id = await core.save_selfie(
            conn, ctx, content_type=request.headers.get("content-type", ""), data=data
        )
    return SelfieOut(selfie_id=selfie_id)


# K3 → K4 · clock in / clock out ---------------------------------------------------------------


class AttendanceIn(BaseModel):
    user_id: UUID
    selfie_id: UUID = Field(
        description="Reuse the same selfie when retrying: the save is idempotent"
    )
    action: Literal["clock_in", "clock_out"] = Field(
        description="What K2/K3 showed; `state_changed` (409) when the record says otherwise"
    )


class AttendanceOut(BaseModel):
    action: Literal["clock_in", "clock_out"]
    display_name: str
    at: datetime
    duration_minutes: int | None = Field(description='Clock out: "8 j 32 mnt"')
    timezone: str


@router.post("/attendance", status_code=status.HTTP_201_CREATED)
async def record(body: AttendanceIn, request: Request, device: CurrentDevice) -> AttendanceOut:
    """K3 "Simpan clock in" / "Simpan clock out". The server decides which (working → out)."""
    # A record left open past closing + grace is flagged first, so this tap starts a new day.
    await attendance_reports.run_due_checks(_pool(request), device.tenant_id)
    ctx: ActorContext = device.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        row = await core.record_attendance(
            conn, ctx, user_id=body.user_id, selfie_id=body.selfie_id, action=body.action
        )
    return AttendanceOut(**row, timezone=device.timezone)
