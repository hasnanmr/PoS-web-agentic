"""Owner tables and reservation rules — wireframe O8 "Meja & Aturan Reservasi" (T-057).

Contract: docs/architecture/screen-endpoint-map.md → O8. Table QR (T-136, #44): each QR encodes
the table web page `{ADMIN_APP_URL}/t/{qr_token}`; the owner downloads one (PNG) or all (PDF),
replaces a table's token, and picks where the QR leads ("Tujuan QR meja").
"""

from __future__ import annotations

from datetime import time
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from app import db
from app.api.errors import ApiError
from app.auth.deps import OwnerOnly
from app.core import outlets, table_qr
from app.core import tables as core

router = APIRouter(prefix="/api/v1/owner", tags=["owner: tables & reservation rules"])


class TableOut(BaseModel):
    id: UUID
    name: str
    capacity: int
    area: str | None
    is_bookable: bool


class TableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    capacity: int = Field(ge=1, le=100)
    area: str | None = Field(default=None, max_length=60)
    is_bookable: bool = True


class TablePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=30)
    capacity: int | None = Field(default=None, ge=1, le=100)
    area: str | None = Field(default=None, max_length=60)
    is_bookable: bool | None = None


class ReservationSettingsIn(BaseModel):
    is_enabled: bool = Field(description='"Reservasi WhatsApp" toggle; staff bookings always work')
    bookable_from: time
    bookable_until: time = Field(description="Last booking start time (outlet-local)")
    default_duration_minutes: int = Field(ge=15, le=600)
    booking_window_days: int = Field(ge=0, le=365)
    max_party_size: int = Field(ge=1, le=100)
    reminder_offset_minutes: int = Field(ge=0, le=2880)
    cancellation_cutoff_minutes: int = Field(ge=0, le=2880)


class ReservationSettingsOut(ReservationSettingsIn):
    hold_minutes: int = Field(description="No-show hold, fixed at 15 (read-only)")


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


@router.get("/outlets/{outlet_id}/tables")
async def list_tables(outlet_id: UUID, request: Request, user: OwnerOnly) -> list[TableOut]:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        rows = await core.list_tables(conn, outlet_id)
    return [TableOut(**r) for r in rows]


@router.post("/outlets/{outlet_id}/tables", status_code=status.HTTP_201_CREATED)
async def create_table(
    outlet_id: UUID, body: TableCreate, request: Request, user: OwnerOnly
) -> TableOut:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        row = await core.create_table(conn, ctx, outlet_id, **body.model_dump())
    return TableOut(**row)


@router.patch("/tables/{table_id}")
async def update_table(
    table_id: UUID, body: TablePatch, request: Request, user: OwnerOnly
) -> TableOut:
    ctx = user.actor()
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "capacity", "is_bookable"):
        if field in changes and changes[field] is None:
            changes.pop(field)
    async with db.transaction(_pool(request), ctx) as conn:
        row = await core.update_table(conn, ctx, table_id, changes)
    return TableOut(**row)


@router.delete("/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table(table_id: UUID, request: Request, user: OwnerOnly) -> Response:
    """Deactivate the table. `table_in_use` while it has an open bill or an upcoming booking."""
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await core.delete_table(conn, ctx, table_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/outlets/{outlet_id}/reservation-settings")
async def get_settings(
    outlet_id: UUID, request: Request, user: OwnerOnly
) -> ReservationSettingsOut:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        row = await core.get_settings(conn, outlet_id)
    return ReservationSettingsOut(**row)


@router.put("/outlets/{outlet_id}/reservation-settings")
async def put_settings(
    outlet_id: UUID, body: ReservationSettingsIn, request: Request, user: OwnerOnly
) -> ReservationSettingsOut:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        row = await core.put_settings(conn, ctx, outlet_id, body.model_dump())
    return ReservationSettingsOut(**row)


# Table QR (T-136) -----------------------------------------------------------------------------


class QrSettingsIn(BaseModel):
    target: Literal["web_whatsapp", "web", "whatsapp"]


class QrSettingsOut(QrSettingsIn):
    whatsapp_connected: bool = Field(
        description="Without WhatsApp the QR always leads to the web page (options disabled)"
    )


class QrTokenOut(BaseModel):
    qr_token: str
    url: str


def _app_url(request: Request) -> str:
    url = request.app.state.settings.admin_app_url
    if not url:
        raise ApiError(503, "admin_app_url_not_configured", "ADMIN_APP_URL is not set")
    return str(url)


def _filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in name) or "meja"


@router.get("/tables/{table_id}/qr.png")
async def table_qr_png(table_id: UUID, request: Request, user: OwnerOnly) -> Response:
    """ "⭳ Unduh": the QR of one table (PNG)."""
    app_url = _app_url(request)
    async with db.transaction(_pool(request), user.actor()) as conn:
        table = await table_qr.table_token(conn, table_id)
    png = table_qr.qr_png(table_qr.table_url(app_url, table["qr_token"]))
    name = _filename(f"qr-meja-{table['name']}")
    return Response(
        content=png,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{name}.png"'},
    )


@router.get("/outlets/{outlet_id}/tables/qr.pdf")
async def outlet_qr_pdf(outlet_id: UUID, request: Request, user: OwnerOnly) -> Response:
    """ "⭳ Unduh semua QR (PDF)": one page per active table (QR, table name, outlet name)."""
    app_url = _app_url(request)
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        rows = await table_qr.outlet_tokens(conn, outlet_id)
    if not rows:
        raise ApiError(404, "not_found", "this outlet has no tables")
    pdf = table_qr.qr_pdf(
        [
            {
                "url": table_qr.table_url(app_url, r["qr_token"]),
                "title": f"Meja {r['name']}",
                "subtitle": r["outlet_name"],
            }
            for r in rows
        ]
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="qr-meja.pdf"'},
    )


@router.post("/tables/{table_id}/qr-token")
async def replace_qr_token(table_id: UUID, request: Request, user: OwnerOnly) -> QrTokenOut:
    """ "↻ Ganti": a new token; the old printed QR shows Q0 "QR tidak berlaku" at once."""
    app_url = _app_url(request)
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        token = await table_qr.replace_token(conn, ctx, table_id)
    return QrTokenOut(qr_token=token, url=table_qr.table_url(app_url, token))


@router.get("/outlets/{outlet_id}/table-qr-settings")
async def get_qr_settings(outlet_id: UUID, request: Request, user: OwnerOnly) -> QrSettingsOut:
    async with db.transaction(_pool(request), user.actor()) as conn:
        await outlets.require_outlet(conn, outlet_id)
        row = await table_qr.qr_settings(conn, outlet_id)
    return QrSettingsOut(**row)


@router.put("/outlets/{outlet_id}/table-qr-settings")
async def put_qr_settings(
    outlet_id: UUID, body: QrSettingsIn, request: Request, user: OwnerOnly
) -> QrSettingsOut:
    ctx = user.actor()
    async with db.transaction(_pool(request), ctx) as conn:
        await outlets.require_outlet(conn, outlet_id)
        row = await table_qr.put_qr_settings(conn, ctx, outlet_id, body.target)
    return QrSettingsOut(**row)
