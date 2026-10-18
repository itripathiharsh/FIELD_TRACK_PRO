"""
Collections Overview router — /api/v1/collections/overview

Admin-only, mirroring PaymentReviewPage/ReportsPage/ImportWizardPage: this is
a management view across every outlet, not a per-visit employee workflow.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps.auth import CurrentUser, require_role
from app.database import get_async_session
from app.models.user import Role
from app.schemas.collections import CollectionsOverviewResponse
from app.services import report_tables as rt
from app.services.aging_service import AgingStatus
from app.services.collections_service import get_collections_overview
from app.services.report_exports import (
    PDF_MIME, XLSX_MIME, content_disposition, report_filename, to_pdf, to_xlsx,
)

router = APIRouter(prefix="/collections", tags=["collections"], dependencies=[Depends(require_role(Role.ADMIN))])

_DATE_DOC = "Inclusive IST calendar date (YYYY-MM-DD)"


def overview_params(
    search: str | None = Query(default=None, description="Match against outlet name or outlet code"),
    territory_id: uuid.UUID | None = Query(default=None, description="Zone"),
    area_id: uuid.UUID | None = Query(default=None),
    employee_id: uuid.UUID | None = Query(default=None),
    collection_status: AgingStatus | None = Query(default=None),
    start_date: date | None = Query(
        default=None,
        description=_DATE_DOC + ". Adds the 'invoiced in period' / 'collected in period' columns; "
        "outstanding, overdue and ageing remain as of today.",
    ),
    end_date: date | None = Query(default=None, description=_DATE_DOC),
) -> dict:
    return dict(
        search=search, territory_id=territory_id, area_id=area_id, employee_id=employee_id,
        collection_status=collection_status, start_date=start_date, end_date=end_date,
    )


@router.get("/overview", response_model=CollectionsOverviewResponse)
async def collections_overview(
    current_user: CurrentUser,
    f: dict = Depends(overview_params),
    session: AsyncSession = Depends(get_async_session),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> CollectionsOverviewResponse:
    """
    Outlet-list financial overview: outstanding, ageing bucket, last
    payment/visit, per outlet - the client's Excel-screenshot replacement.
    Every ageing number is computed by the same aging_service function the
    per-outlet Account Summary already uses.
    """
    return await get_collections_overview(session, skip=skip, limit=limit, **f)


@router.get("/overview/export")
async def export_collections_overview(
    current_user: CurrentUser,
    f: dict = Depends(overview_params),
    format: Literal["xlsx", "pdf"] = Query(default="xlsx"),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    """
    Excel / PDF export of the Collections Overview: the SAME filter + date params as
    ``/collections/overview`` and ALL matching outlets (no pagination).
    """
    resp = await get_collections_overview(session, skip=0, limit=None, **f)
    status = f["collection_status"].value if f["collection_status"] else None
    filters, filtered = await rt.describe_filters(
        session,
        ["date", "zone", "area", "employee", "status", "search"],
        start_date=f["start_date"], end_date=f["end_date"], zone_id=f["territory_id"],
        area_id=f["area_id"], employee_id=f["employee_id"], status=status, query=f["search"],
    )
    has_period = f["start_date"] is not None or f["end_date"] is not None
    table = rt.build_collections_overview_table(resp, filters, has_period, resp.as_of_date)
    from app.services.report_exports import fmt_inr
    t = resp.totals
    table.kpis = [
        ("Outlets", str(t.total_outlets)),
        ("Invoiced", f"₹{fmt_inr(t.total_invoiced)}"),
        ("Paid in Tally", f"₹{fmt_inr(t.paid_in_tally if t.paid_in_tally is not None else t.total_paid)}"),
        ("Outstanding", f"₹{fmt_inr(t.total_outstanding)}"),
        ("Overdue", f"₹{fmt_inr(t.overdue_amount)}"),
    ]
    if format == "pdf":
        data, mime, ext = await run_in_threadpool(to_pdf, [table]), PDF_MIME, "pdf"
    else:
        data, mime, ext = await run_in_threadpool(to_xlsx, [table]), XLSX_MIME, "xlsx"
    name = report_filename("Collections_Overview", ext, filtered)
    return Response(content=data, media_type=mime, headers={"Content-Disposition": content_disposition(name)})
