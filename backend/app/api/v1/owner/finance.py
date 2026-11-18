"""Owner finance — O9 Laporan Cashflow & Pengeluaran (T-041 to T-043) and O10 Laporan Cash
Count (T-040, T-102). The sidebar item "Pengeluaran" opens O9 until its own wireframe exists.

Contract: docs/architecture/screen-endpoint-map.md → O9, O10.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Header, Query, Request, Response, status
from pydantic import BaseModel, Field

from app import db
from app.api.errors import ApiError
from app.auth.deps import OwnerOnly
from app.core import idempotency, ledger, outlets, reports
from app.core.localtime import DEFAULT_TIMEZONE, local_date, to_local, zone_label

router = APIRouter(prefix="/api/v1/owner", tags=["owner: finance"])


# Schemas -------------------------------------------------------------------------------


class OutletRef(BaseModel):
    id: UUID
    name: str


class Expense(BaseModel):
    id: int
    business_date: date
    outlet: OutletRef
    description: str
    amount: int = Field(description="Positive amount spent")
    recorded_by: str | None
    created_at: datetime
    reversed: bool
    reversal_reason: str | None


class ExpensePage(BaseModel):
    items: list[Expense]
    next_cursor: str | None


class ExpenseIn(BaseModel):
    outlet_id: UUID
    amount: int = Field(gt=0, le=ledger.EXPENSE_MAX)
    business_date: date
    description: str = Field(min_length=1, max_length=ledger.DESCRIPTION_MAX)


class ReversalIn(BaseModel):
    reason: str = Field(max_length=300)


class ReversalOut(BaseModel):
    reversal_id: int
    expense: Expense


class Tile(BaseModel):
    amount: int
    change_pct: int | None


class Period(BaseModel):
    from_: date = Field(alias="from")
    to: date

    model_config = {"populate_by_name": True}


class CashflowTotals(BaseModel):
    cash_in: Tile
    cash_out: Tile
    net: Tile
    pb1_collected: Tile


class SeriesPoint(BaseModel):
    date: date
    cash_in: int
    cash_out: int


class Breakdown(BaseModel):
    revenue_excl_pb1: int
    pb1: int
    delivery_fee: int
    cash: int
    qris: int
    refunds: int
    expenses: int
    cash_difference: int


class OutletExpense(BaseModel):
    outlet_id: UUID
    outlet: str
    amount: int
    count: int


class Cashflow(BaseModel):
    from_: date = Field(alias="from")
    to: date
    granularity: Literal["daily", "weekly", "monthly"]
    previous: Period
    totals: CashflowTotals
    series: list[SeriesPoint]
    breakdown: Breakdown
    expenses_by_outlet: list[OutletExpense]
    expenses_total: int
    expenses_count: int

    model_config = {"populate_by_name": True}


class DrawerRef(BaseModel):
    id: UUID
    name: str
    number: int


class CashCountRow(BaseModel):
    shift_id: UUID
    opened_at: datetime
    closed_at: datetime
    timezone: str
    outlet: OutletRef
    drawer: DrawerRef
    starting_cash: int
    expected_cash: int
    counted_cash: int
    difference: int
    kind: Literal["shortage", "surplus", "none"]
    counted_by: str | None


class CashCountSummary(BaseModel):
    shifts: int
    shifts_with_difference: int
    total_shortage: int = Field(description="Sum of negative differences (zero or less)")
    total_surplus: int


class CashCount(BaseModel):
    from_: date = Field(alias="from")
    to: date
    summary: CashCountSummary
    rows: list[CashCountRow]

    model_config = {"populate_by_name": True}


def _pool(request: Request) -> Any:
    return request.app.state.db_pool


async def _range(
    conn: psycopg.AsyncConnection,
    outlet_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> tuple[date, date]:
    """Month to date in the outlet's zone (WIB for all outlets) unless given."""
    tz = (await outlets.require_outlet(conn, outlet_id))["timezone"] if outlet_id else None
    today = local_date(datetime.now(UTC), tz or DEFAULT_TIMEZONE)
    start, end = reports.default_range(today)
    return date_from or start, date_to or end


# Expenses -----------------------------------------------------------------------------------


@router.get("/expenses")
async def list_expenses(
    request: Request,
    user: OwnerOnly,
    outlet_id: UUID | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> ExpensePage:
    async with db.transaction(_pool(request), user.actor()) as conn:
        if outlet_id:
            await outlets.require_outlet(conn, outlet_id)
        page = await ledger.list_expenses(
            conn,
            outlet_id=outlet_id,
            date_from=date_from,
            date_to=date_to,
            cursor=cursor,
            limit=limit,
        )
    return ExpensePage(**page)


@router.post("/expenses", status_code=status.HTTP_201_CREATED)
async def create_expense(
    body: ExpenseIn,
    request: Request,
    response: Response,
    user: OwnerOnly,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Expense:
    """O9 "Simpan pengeluaran". Append-only; a mistake is corrected with a reversal."""
    key = idempotency.check_key(idempotency_key)
    fp = idempotency.fingerprint("expense", body.model_dump(mode="json"))
    ctx = user.actor()
    try:
        async with db.transaction(_pool(request), ctx) as conn:
            cached = await idempotency.lookup(conn, ctx, "expense.create", key, fp)
            if cached is not None:
                response.status_code = status.HTTP_200_OK
                response.headers["Idempotent-Replay"] = "true"
                return Expense(**cached)
            await outlets.require_outlet(conn, body.outlet_id)
            created = Expense(
                **await ledger.record_expense(
                    conn,
                    ctx,
                    body.outlet_id,
                    amount=body.amount,
                    business_date=body.business_date,
                    description=body.description,
                )
            )
            await idempotency.store(
                conn, ctx, "expense.create", key, fp, created.model_dump(mode="json")
            )
    except psycopg.errors.UniqueViolation as exc:
        if "idempotency_keys" in str(exc):
            raise ApiError(409, "conflict", "the same request is already being processed") from None
        raise
    return created


@router.post("/ledger-entries/{entry_id}/reversal", status_code=status.HTTP_201_CREATED)
async def reverse_entry(
    entry_id: int, body: ReversalIn, request: Request, user: OwnerOnly
) -> ReversalOut:
    """O9 "Salah input? Buat entry reversal, bukan edit." (expenses only)."""
    if not body.reason.strip():
        raise ApiError(422, "reason_required", "a reason is required for a reversal")
    ctx = user.actor().with_reason(body.reason)
    async with db.transaction(_pool(request), ctx) as conn:
        result = await ledger.reverse_entry(conn, ctx, entry_id)
    return ReversalOut(**result)


# Reports ------------------------------------------------------------------------------------


@router.get("/reports/cashflow")
async def cashflow_report(
    request: Request,
    user: OwnerOnly,
    outlet_id: UUID | None = None,
    granularity: Literal["daily", "weekly", "monthly"] = "daily",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> Cashflow:
    async with db.transaction(_pool(request), user.actor()) as conn:
        start, end = await _range(conn, outlet_id, date_from, date_to)
        data = await reports.cashflow(
            conn, outlet_id=outlet_id, date_from=start, date_to=end, granularity=granularity
        )
    return Cashflow(**data)


CSV_COLUMNS = (
    "tanggal",
    "buka",
    "tutup",
    "zona",
    "outlet",
    "drawer",
    "kas_awal",
    "ekspektasi",
    "dihitung",
    "selisih",
    "jenis",
    "dihitung_oleh",
)


def _csv(report: dict[str, Any]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for r in report["rows"]:
        opened = to_local(r["opened_at"], r["timezone"])
        closed = to_local(r["closed_at"], r["timezone"])
        writer.writerow(
            [
                opened.date().isoformat(),
                opened.strftime("%H:%M"),
                closed.strftime("%H:%M"),
                zone_label(r["timezone"]),
                r["outlet"]["name"],
                f"Drawer {r['drawer']['number']} · {r['drawer']['name']}",
                r["starting_cash"],
                r["expected_cash"],
                r["counted_cash"],
                r["difference"],
                r["kind"],
                r["counted_by"] or "",
            ]
        )
    return out.getvalue()


@router.get(
    "/reports/cash-count",
    response_model=CashCount,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
async def cash_count_report(
    request: Request,
    user: OwnerOnly,
    outlet_id: UUID | None = None,
    drawer_id: UUID | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    format: Literal["json", "csv"] = "json",
) -> Any:
    async with db.transaction(_pool(request), user.actor()) as conn:
        start, end = await _range(conn, outlet_id, date_from, date_to)
        data = await reports.cash_count(
            conn, outlet_id=outlet_id, drawer_id=drawer_id, date_from=start, date_to=end
        )
    wants_csv = format == "csv" or "text/csv" in request.headers.get("accept", "")
    if wants_csv:
        return Response(
            content=_csv(data),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="cash-count-{start}-{end}.csv"'},
        )
    return CashCount(**data)
