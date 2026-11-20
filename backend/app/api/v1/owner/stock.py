"""Owner stock export — S7 / M5 "Riwayat movement" → "⭳ Unduh CSV" (issue #37).

Not drawn on the wireframe; added on the product owner's request. Staff see the history panel
but not the button, and this endpoint refuses them with 403.

Contract: docs/architecture/screen-endpoint-map.md → S7 / M5.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app import db
from app.auth.deps import OwnerOnly
from app.core import outlets, stock
from app.core.errors import ValidationFailedError
from app.core.localtime import to_local, zone_label

router = APIRouter(prefix="/api/v1/owner", tags=["owner: stock"])

CSV_COLUMNS = ("at", "zone", "type", "quantity", "unit", "stock_item", "order_no", "note", "actor")


def _text(value: str | None) -> str:
    """Free text cell; a leading = + - @ is escaped so Excel does not run it as a formula."""
    if not value:
        return ""
    return f"'{value}" if value[0] in "=+-@\t\r" else value


def _csv(rows: list[dict[str, Any]], tz: str) -> str:
    out = io.StringIO()
    out.write("﻿")  # UTF-8 BOM so Excel reads names like "Gula aren cair" correctly
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    label = zone_label(tz)
    for r in rows:
        writer.writerow(
            [
                to_local(r["at"], tz).strftime("%Y-%m-%d %H:%M:%S"),
                label,
                r["type"],
                r["quantity"],
                r["unit"],
                _text(r["stock_item"]),
                r["order_no"] or "",
                _text(r["note"]),
                _text(r["actor"]),
            ]
        )
    return out.getvalue()


@router.get(
    "/outlets/{outlet_id}/stock-movements/export",
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
async def export_movements(
    outlet_id: UUID,
    request: Request,
    user: OwnerOnly,
    stock_item_id: UUID | None = None,
    type: stock.HistoryType | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    format: Literal["csv"] = "csv",
) -> Response:
    async with db.transaction(request.app.state.db_pool, user.actor()) as conn:
        outlet = await outlets.require_outlet(conn, outlet_id)
        tz = outlet["timezone"]
        since, until = stock.history_bounds(date_from, date_to, tz)
        rows, more = await stock.movement_history(
            conn,
            outlet_id,
            stock_item_id=stock_item_id,
            type=type,
            since=since,
            until=until,
            limit=stock.EXPORT_MAX_ROWS,
        )
    if more is not None:
        raise ValidationFailedError(
            "too many movements for one file; narrow the date range",
            {"field": "range", "max_rows": stock.EXPORT_MAX_ROWS},
        )
    name = f"stok-movement-{date_from or 'awal'}-{date_to or 'sekarang'}.{format}"
    return Response(
        content=_csv(rows, tz),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
