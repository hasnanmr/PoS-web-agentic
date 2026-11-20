"""Owner audit log — wireframe O11 (T-101). Read-only, owner only.

Contract: docs/architecture/screen-endpoint-map.md → O11.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app import db
from app.auth.deps import OwnerOnly
from app.core import audit_log, outlets, reports
from app.core.errors import ValidationFailedError
from app.core.localtime import DEFAULT_TIMEZONE, local_date

router = APIRouter(prefix="/api/v1/owner", tags=["owner: audit log"])


class AuditActor(BaseModel):
    type: Literal["user", "system", "agent", "device"]
    id: UUID | None
    name: str | None
    role: str | None


class AuditRow(BaseModel):
    id: int
    created_at: datetime
    timezone: str
    outlet_id: UUID
    order_id: UUID
    order_no: str
    kind: audit_log.Kind
    change: str
    actor: AuditActor
    reason: str | None


class AuditPage(BaseModel):
    date_from: date
    date_to: date
    items: list[AuditRow]
    next_cursor: str | None


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


def _kinds(raw: str | None) -> list[audit_log.Kind]:
    if not raw:
        return list(audit_log.KINDS)
    kinds = [k.strip() for k in raw.split(",") if k.strip()]
    bad = [k for k in kinds if k not in audit_log.KINDS]
    if bad or not kinds:
        raise ValidationFailedError("kind is reversal, status, or payment", {"field": "kind"})
    return kinds  # type: ignore[return-value]


@router.get("/audit-log")
async def audit_log_list(
    request: Request,
    user: OwnerOnly,
    outlet_id: UUID | None = None,
    actor_id: UUID | None = None,
    kind: str | None = Query(default=None, max_length=40, description="reversal,status,payment"),
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    cursor: str | None = Query(default=None, max_length=200),
) -> AuditPage:
    """O11 rows: reversals, status changes, and payment changes of orders, newest first, 50 per
    page. Default range: month to date in each outlet's own zone; `date_from`/`date_to` in the
    response are the outlet's (WIB for all outlets) and only label the range picker."""
    kinds = _kinds(kind)
    async with db.transaction(_pool(request), user.actor()) as conn:
        tz = DEFAULT_TIMEZONE
        if outlet_id:
            tz = (await outlets.require_outlet(conn, outlet_id))["timezone"]
        page = await audit_log.list_events(
            conn,
            outlet_id=outlet_id,
            actor_id=actor_id,
            kinds=kinds,
            date_from=date_from,
            date_to=date_to,
            cursor=cursor,
        )
    start, end = reports.default_range(local_date(datetime.now(UTC), tz))
    return AuditPage(date_from=date_from or start, date_to=date_to or end, **page)
