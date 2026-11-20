"""Own attendance — wireframes S9 "Absensi Saya" and M6 (T-116, T-117, T-122).

Contract: docs/architecture/screen-endpoint-map.md → S9 / M6. Read-only: there is no clock-in
endpoint for staff tokens; clock in and out happen only on the outlet tablet (K0-K4). RLS keeps
every row and selfie to the signed-in staff member.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field

from app import db
from app.api.v1.owner.attendance import RecordOut
from app.auth.deps import TenantUser
from app.core import attendance_reports as reports
from app.core.errors import ValidationFailedError
from app.core.localtime import local_date

LATEST_TIMEZONE = "Asia/Jayapura"  # WIT: the first zone to reach a new day

router = APIRouter(prefix="/api/v1/ops/me/attendance", tags=["ops: my attendance"])


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


class OutletRef(BaseModel):
    name: str
    timezone: str | None = None


class Flagged(BaseModel):
    id: UUID
    date: date
    outlet: OutletRef


class Today(BaseModel):
    status: Literal["working", "not_clocked_in"]
    clock_in_at: datetime | None
    device_name: str | None = Field(description='tablet "Kasir Dago"')
    outlet: OutletRef | None
    flagged_records: list[Flagged] = Field(description='Banner "Kamu lupa clock out 16 Nov"')


class History(BaseModel):
    from_: date = Field(alias="from")
    to: date
    records: list[RecordOut]
    total_minutes: int = Field(description="Without flagged or open records")

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


@router.get("/today")
async def today(request: Request, user: TenantUser) -> Today:
    """S9 "Status hari ini" and the forgotten clock-out banner."""
    assert user.tenant_id is not None  # noqa: S101
    await reports.run_due_checks(_pool(request), user.tenant_id)
    async with db.transaction(_pool(request), user.actor()) as conn:
        row = await reports.my_today(conn, user.user_id)
    return Today(**row)


@router.get("")
async def history(
    request: Request,
    user: TenantUser,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> History:
    """S9 "Riwayat saya · minggu ini" (default: Monday of this week to today, counted in WIT, the
    easternmost zone, so today's record at a WITA/WIT outlet is never cut off)."""
    assert user.tenant_id is not None  # noqa: S101
    end = date_to or local_date(datetime.now(UTC), LATEST_TIMEZONE)
    start = date_from or end - timedelta(days=end.isoweekday() - 1)
    if start > end or (end - start).days > 92:
        raise ValidationFailedError("choose a range of at most 3 months", {"field": "from"})
    await reports.run_due_checks(_pool(request), user.tenant_id)
    async with db.transaction(_pool(request), user.actor()) as conn:
        data = await reports.my_history(conn, user.user_id, start, end)
    return History(**data)


@router.get(
    "/{record_id}/selfies/{which}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/webp": {}}}},
)
async def my_selfie(
    record_id: UUID, which: Literal["in", "out"], request: Request, user: TenantUser
) -> Response:
    """S9 "lihat selfie masuk & pulang milik sendiri" (404 for anyone else's)."""
    async with db.transaction(_pool(request), user.actor()) as conn:
        kind, data = await reports.selfie_image(conn, record_id, which)
    return Response(content=data, media_type=kind, headers={"Cache-Control": "private, no-store"})
