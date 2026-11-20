"""Owner attendance — wireframes O3 "Tablet absensi" (T-121) and O14 "Kehadiran Staf" (T-119).

Contract: docs/architecture/screen-endpoint-map.md → O3 "Tablet absensi" and O14. The grace period
("Tenggang lupa clock out") is `attendance_grace_minutes` on `PATCH /owner/outlets/{id}`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status
from pydantic import BaseModel, Field

from app import db
from app.auth.deps import OwnerOnly
from app.core import attendance as core
from app.core import attendance_reports as reports
from app.core import outlets
from app.core.errors import ValidationFailedError
from app.core.localtime import local_date

LATEST_TIMEZONE = "Asia/Jayapura"  # WIT: the first zone to reach a new day

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
    """O3 "+ Pairing tablet baru → kode 6 digit"; the tablet enters it on K0.
    `tablet_already_paired` (409) while the outlet has an active tablet: forget it first."""
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        row = await core.create_pairing_code(conn, ctx, outlet_id)
    return PairingCodeOut(**row)


@router.post("/attendance-devices/{device_id}/revoke")
async def revoke_device(device_id: UUID, request: Request, owner: OwnerOnly) -> DeviceOut:
    """O3 "Lupakan perangkat": the tablet is refused on its next request and goes back to K0;
    the outlet can then pair a new tablet (one active tablet per outlet)."""
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        row = await core.revoke_device(conn, ctx, device_id)
    return DeviceOut(**row)


# O14 · Kehadiran Staf, Selfie & Koreksi (T-118, T-119, T-122) ---------------------------------


class Ref(BaseModel):
    id: UUID
    name: str


class RecordOut(BaseModel):
    id: UUID
    date: date  # outlet-local day of the clock-in
    user: Ref
    outlet: Ref
    timezone: str
    clock_in_at: datetime
    clock_out_at: datetime | None
    duration_minutes: int | None = Field(description="Closed or corrected records only")
    has_selfie_in: bool
    has_selfie_out: bool
    status: Literal["open", "closed", "needs_correction", "corrected"]


class StaffTotal(BaseModel):
    user: Ref
    outlets: list[str]
    worked_minutes: int = Field(description="Without flagged or open records")
    days: int


class AttendanceReport(BaseModel):
    from_: date = Field(alias="from")
    to: date
    summary: list[StaffTotal]
    needs_correction_count: int
    records: list[RecordOut]

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class Times(BaseModel):
    clock_in_at: datetime | None
    clock_out_at: datetime | None


class Flag(BaseModel):
    at: datetime = Field(description='"Ditandai otomatis 23:00"')
    closes_at: str | None = Field(description='Outlet closing time, "22:00"')
    grace_minutes: int | None


class Correction(BaseModel):
    at: datetime
    by: str
    from_: Times = Field(alias="from")
    to: Times
    reason: str | None

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class Devices(BaseModel):
    clock_in: str | None
    clock_out: str | None


class RecordDetail(RecordOut):
    devices: Devices
    original: Times
    flag: Flag | None
    corrections: list[Correction]


class CorrectionIn(BaseModel):
    clock_out_at: datetime = Field(
        description='O14 "Jam pulang *" (the only time the panel corrects)'
    )
    reason: str = Field(max_length=500, description="Required (blank → reason_required)")


async def _report_range(
    conn: Any, outlet_id: UUID | None, date_from: date | None, date_to: date | None
) -> tuple[date, date]:
    """Default: the last 7 days up to today in the outlet's zone; for all outlets, up to today in
    the easternmost zone (WIT), so a record dated today at any outlet is included."""
    tz = (await outlets.require_outlet(conn, outlet_id))["timezone"] if outlet_id else None
    today = local_date(datetime.now(UTC), tz or LATEST_TIMEZONE)
    end = date_to or today
    start = date_from or end - timedelta(days=6)
    if start > end:
        raise ValidationFailedError("from must not be after to", {"field": "from"})
    return start, end


@router.get(
    "/attendance",
    response_model=AttendanceReport,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
async def attendance_report(
    request: Request,
    owner: OwnerOnly,
    outlet_id: UUID | None = None,
    user_id: UUID | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    format: Literal["json", "csv"] = "json",
) -> Any:
    """O14 summary cards, "Perlu dikoreksi", and the table. "⭳ Ekspor CSV" = `format=csv`."""
    assert owner.tenant_id is not None  # noqa: S101
    await reports.run_due_checks(_pool(request), owner.tenant_id)
    async with db.transaction(_pool(request), owner.actor()) as conn:
        start, end = await _report_range(conn, outlet_id, date_from, date_to)
        data = await reports.owner_report(
            conn, outlet_id=outlet_id, user_id=user_id, date_from=start, date_to=end
        )
    if format == "csv" or "text/csv" in request.headers.get("accept", ""):
        return Response(
            content=reports.report_csv(data),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="kehadiran-{start}-{end}.csv"'},
        )
    return AttendanceReport(**data)


@router.get("/attendance/{record_id}")
async def attendance_record(record_id: UUID, request: Request, owner: OwnerOnly) -> RecordDetail:
    """O14 "Koreksi catatan": original values, the automatic flag, and the correction history."""
    async with db.transaction(_pool(request), owner.actor()) as conn:
        row = await reports.record_detail(conn, record_id)
    return RecordDetail(**row)


@router.post("/attendance/{record_id}/corrections")
async def correct_attendance(
    record_id: UUID, body: CorrectionIn, request: Request, owner: OwnerOnly
) -> RecordDetail:
    """O14 "Simpan koreksi": the original values stay in the append-only history."""
    ctx = owner.actor().with_reason(body.reason)
    async with db.transaction(_pool(request), ctx) as conn:
        row = await reports.correct_record(conn, ctx, record_id, clock_out_at=body.clock_out_at)
    return RecordDetail(**row)


@router.get(
    "/attendance/{record_id}/selfies/{which}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/webp": {}}}},
)
async def attendance_selfie(
    record_id: UUID, which: Literal["in", "out"], request: Request, owner: OwnerOnly
) -> Response:
    """O14 "Selfie masuk / pulang". PoC: the photo bytes (no Storage bucket yet), never cached."""
    async with db.transaction(_pool(request), owner.actor()) as conn:
        kind, data = await reports.selfie_image(conn, record_id, which)
    return Response(content=data, media_type=kind, headers={"Cache-Control": "private, no-store"})


@router.delete("/attendance/{record_id}/selfies/{which}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attendance_selfie(
    record_id: UUID, which: Literal["in", "out"], request: Request, owner: OwnerOnly
) -> Response:
    """Owner deletes a selfie before the 45-day purge; the record and its hours stay. Audited.
    No screen yet (product owner, 2026-11-20). Staff cannot delete selfies, not even their own."""
    ctx = owner.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await reports.delete_selfie(conn, ctx, record_id, which)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
